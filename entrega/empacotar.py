#!/usr/bin/env python3
"""Gera os pacotes da entrega a partir da pasta da skill, sem arriscar a distribuição anterior.

  dist/fundacao-ia-multiprojetos.skill          formato Agent Skills (zip com a pasta na raiz),
                                                gerado pelo package_skill.py do skill-creator
                                                (exclui evals/, __pycache__ e *.pyc)
  dist/fundacao-ia-multiprojetos-completo.zip   mesma skill + evals/ (cenários, fixtures, avaliações)
  dist/SHA256SUMS.txt                           hashes dos dois pacotes
  dist/EMPACOTAMENTO.json                       versão empacotada e ferramenta usada (caminho e hashes)
  dist/anteriores/<versão>/                     conjunto anterior, arquivado (nunca apagado)

Ordem (auditoria F18): (1) confere a ferramenta — o skill-creator precisa ter
`scripts/package_skill.py`, e ele e o que ele importa da mesma pasta precisam ter os SHA-256 registrados em
FERRAMENTA_ESPERADA; divergência recusa com código 2, sem alterar nada, e a ferramenta roda de uma cópia desses
mesmos bytes numa pasta temporária só com eles (auditoria Codex Security da 1.7.6, #6); os hashes vão para
EMPACOTAMENTO.json; (2) gera os dois pacotes numa área de preparação dentro de `dist/`; (3) confere estrutura
(SKILL.md na raiz da pasta, sem caminho absoluto ou `..`, sem evals/ nem bytecode no .skill), integridade dos zips
e, com o `verificar_pacote.py` ao lado (a mesma regra da CI pública), que cada pacote é exatamente a árvore — os
mesmos membros, byte a byte, nenhum a mais ou a menos — ANTES de gravar o SHA256SUMS.txt (#6); (4) só então
arquiva o conjunto anterior em `dist/anteriores/` e promove o novo. Falha em qualquer passo antes da promoção deixa
a distribuição anterior intacta; falha durante a promoção devolve o conjunto anterior ao lugar.
Lista dos pacotes (revisão de segurança da 1.7.7, R177-ATU-04): `entrega/HISTORICO-PACOTES-SHA256.txt`, ao lado de
`dist/`, só cresce. Antes da promoção, versão que já tem ali pacote com outro conteúdo recusa (suba a versão); depois
dela, os dois pacotes novos são acrescentados (`<sha256>  <versão>/<arquivo>`) — a liberação faz o commit da lista com
o `dist/`. O `verificar_pacote.py` recusa pacote de `dist/anteriores/` fora da lista.

Antes de tudo, a árvore da skill é percorrida SEM seguir ligações: um link simbólico ou uma junção em
qualquer ponto (a própria pasta da skill inclusive) recusa o empacotamento, porque o zip seguiria a
ligação e publicaria o conteúdo do alvo, por exemplo um arquivo do computador que gera a entrega
(varredura da 1.4.5, #1). O zip completo leva só os arquivos comuns dessa listagem.

Uso: python empacotar.py --skill-creator <pasta do skill-creator> [--dist <pasta>]
Códigos: 0 promovido · 1 falha (anterior preservado) · 2 ferramenta ausente, divergente da registrada ou uso incorreto.
"""
from __future__ import annotations

import argparse
import hashlib
import importlib.util
import json
import os
import re
import shutil
import stat
import subprocess
import sys
import tempfile
import zipfile
from datetime import datetime, timezone
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SKILL = RAIZ / "fundacao-ia-multiprojetos"
DIST = RAIZ / "entrega" / "dist"
NOME = "fundacao-ia-multiprojetos"
CONJUNTO = (f"{NOME}.skill", f"{NOME}-completo.zip", "SHA256SUMS.txt", "EMPACOTAMENTO.json")
# Ferramenta registrada (auditoria Codex Security da 1.7.6, #6): o package_skill.py do skill-creator e o que ele
# importa da mesma pasta, os mesmos desde a 1.5.0 em todas as cópias do plugin oficial. Mudou? Confira a diferença e,
# se for legítima, registre os hashes novos aqui e reveja a regra de membros do .skill no verificar_pacote.py (o
# titular decide).
FERRAMENTA_ESPERADA = {
    "scripts/__init__.py": "e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
    "scripts/package_skill.py": "1a33059b0db1ef73375d46d513e5ea81369d2e8838c970597b0d52ddef8d1c0f",
    "scripts/quick_validate.py": "67cf5703402013936c8fb75ad6a1afecd8841d45cc5e606b634eb05825fde365",
}


def carregar_verificador():
    """O `verificar_pacote.py` ao lado (a regra de membros da CI pública), carregado pelo caminho: vale como script, em
    teste e de qualquer pasta de trabalho."""
    spec = importlib.util.spec_from_file_location("verificar_pacote", Path(__file__).resolve().with_name(
        "verificar_pacote.py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


VERIFICADOR = carregar_verificador()


def sha256(p: Path) -> str:
    return hashlib.sha256(p.read_bytes()).hexdigest()


def ler_ferramenta(creator: Path) -> tuple[dict[str, bytes], list[dict]]:
    """Bytes dos arquivos registrados em FERRAMENTA_ESPERADA, lidos uma vez, e as divergências (ausente ou outro hash).
    O que roda é uma cópia destes mesmos bytes: trocar o arquivo depois da conferência não muda o que roda."""
    lidos, divergentes = {}, []
    for rel, esperado in sorted(FERRAMENTA_ESPERADA.items()):
        try:
            dados = (creator / rel).read_bytes()
        except OSError as e:
            divergentes.append({"arquivo": rel, "esperado": esperado, "encontrado": f"ausente ({type(e).__name__})"})
            continue
        if hashlib.sha256(dados).hexdigest() != esperado:
            divergentes.append({"arquivo": rel, "esperado": esperado, "encontrado": hashlib.sha256(dados).hexdigest()})
        lidos[rel] = dados
    return lidos, divergentes


def e_ligacao(p: Path) -> bool:
    """Link simbólico ou junção do Windows (a regra do `instalar_skill.py`; `os.path.isjunction` só existe a
    partir do 3.12, e no 3.10/3.11 a junção é reconhecida pela marca de ponto de montagem do `lstat`)."""
    if p.is_symlink():
        return True
    is_junction = getattr(os.path, "isjunction", None)
    if is_junction is not None:
        return bool(is_junction(p))
    if os.name != "nt":
        return False
    try:
        st = os.lstat(p)
    except OSError:
        return False
    return bool(getattr(st, "st_file_attributes", 0) & stat.FILE_ATTRIBUTE_REPARSE_POINT) and \
        getattr(st, "st_reparse_tag", None) == stat.IO_REPARSE_TAG_MOUNT_POINT


def arquivos_da_skill(raiz: Path) -> list[Path]:
    """Arquivos comuns da árvore da skill, sem seguir ligações e sem bytecode. Uma ligação em qualquer ponto
    recusa o empacotamento (RuntimeError): seguida, publicaria o conteúdo de fora da árvore (#1)."""
    ligacoes = [raiz.name] if e_ligacao(raiz) else []
    arquivos = []
    for base, pastas, nomes in os.walk(raiz):
        ligacoes += [(Path(base) / n).relative_to(raiz).as_posix() for n in [*pastas, *nomes]
                     if e_ligacao(Path(base) / n)]
        pastas[:] = [d for d in pastas if not e_ligacao(Path(base) / d)]  # não desce por uma ligação
        arquivos += [Path(base) / n for n in nomes if not e_ligacao(Path(base) / n) and (Path(base) / n).is_file()]
    if ligacoes:
        raise RuntimeError("ligação (link simbólico ou junção) na árvore da skill: "
                           f"{', '.join(sorted(ligacoes)[:10])}; o zip publicaria o conteúdo do alvo dela — "
                           "substitua por arquivos comuns")
    return sorted(p for p in arquivos if "__pycache__" not in p.relative_to(raiz).parts and p.suffix != ".pyc")


def versao_da_skill(skill_md: str) -> str:
    m = re.search(r'^\s*version:\s*"?([^"\s]+)"?\s*$', skill_md, re.M)
    return m.group(1) if m else "desconhecida"


def versao_do_pacote(pacote: Path) -> str:
    try:
        with zipfile.ZipFile(pacote) as z:
            return versao_da_skill(z.read(f"{NOME}/SKILL.md").decode("utf-8", "replace"))
    except (OSError, KeyError, zipfile.BadZipFile):
        return "desconhecida"


def conferir_pacote(pacote: Path, *, com_evals: bool) -> list[str]:
    """Problemas de estrutura do pacote (lista vazia = confere)."""
    if not pacote.is_file():
        return [f"{pacote.name} não foi gerado"]
    try:
        with zipfile.ZipFile(pacote) as z:
            nomes = z.namelist()
            ruim = z.testzip()
    except zipfile.BadZipFile:
        return [f"{pacote.name} não é um zip válido"]
    problemas = []
    if ruim:
        problemas.append(f"{pacote.name}: membro corrompido {ruim}")
    if f"{NOME}/SKILL.md" not in nomes:
        problemas.append(f"{pacote.name}: sem {NOME}/SKILL.md na raiz")
    if any(n.startswith("/") or ".." in n.split("/") or ":" in n for n in nomes):
        problemas.append(f"{pacote.name}: membro com caminho absoluto ou '..'")
    if any(n.endswith(".pyc") or "/__pycache__/" in n for n in nomes):
        problemas.append(f"{pacote.name}: contém bytecode")
    tem_evals = any(n.startswith(f"{NOME}/evals/") for n in nomes)
    if tem_evals != com_evals:
        problemas.append(f"{pacote.name}: evals/ {'ausente' if com_evals else 'incluído'}")
    return problemas


def acrescentar_ao_historico(lista: Path, versao: str, hashes: dict[str, str]) -> None:
    """Acrescenta à lista dos pacotes (só cresce) as linhas `<sha256>  <versão>/<arquivo>` que ainda não estão nela."""
    texto = lista.read_text(encoding="utf-8") if lista.is_file() else ""
    novas = [f"{h}  {versao}/{n}" for n, h in hashes.items() if f"{h}  {versao}/{n}" not in
             VERIFICADOR.linhas_do_historico(texto)]
    if novas:
        with open(lista, "a", encoding="utf-8", newline="\n") as f:
            f.write(("\n" if texto and not texto.endswith("\n") else "") + "".join(linha + "\n" for linha in novas))


def promover(dist: Path, preparo: Path, versao_anterior: str) -> Path | None:
    """Arquiva o conjunto anterior e põe o novo no lugar; se algo falhar, devolve o anterior."""
    existentes = [dist / n for n in CONJUNTO if (dist / n).exists()]
    arquivo = None
    if existentes:
        arquivo = dist / "anteriores" / versao_anterior
        if arquivo.exists():
            arquivo = arquivo.with_name(f"{versao_anterior}-{datetime.now(timezone.utc):%Y%m%dT%H%M%SZ}")
        arquivo.mkdir(parents=True)
    movidos: list[tuple[Path, Path]] = []
    try:
        for p in existentes:
            shutil.move(str(p), str(arquivo / p.name))
            movidos.append((arquivo / p.name, p))
        for nome in CONJUNTO:
            if (preparo / nome).exists():
                shutil.move(str(preparo / nome), str(dist / nome))
    except OSError:
        for nome in CONJUNTO:  # volta ao estado anterior
            if (dist / nome).exists() and not any(destino == dist / nome for _, destino in movidos):
                (dist / nome).unlink()
        for de, para in movidos:
            if (dist / para.name).exists():
                (dist / para.name).unlink()
            shutil.move(str(de), str(para))
        raise
    return arquivo


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--skill-creator", type=Path, required=True)
    ap.add_argument("--dist", type=Path, help="pasta de distribuição (padrão: entrega/dist)")
    a = ap.parse_args()
    dist = (a.dist or DIST).resolve()
    creator = a.skill_creator.resolve()
    pkg = creator / "scripts" / "package_skill.py"
    if not pkg.is_file():
        print(json.dumps({"erro": f"skill-creator sem scripts/package_skill.py em {creator}: variante não suportada "
                                  "por este empacotador; nada foi alterado"}, ensure_ascii=False), file=sys.stderr)
        return 2
    lida, divergentes = ler_ferramenta(creator)
    if divergentes:
        print(json.dumps({"erro": "a ferramenta de empacotamento não é a registrada em FERRAMENTA_ESPERADA "
                                  "(empacotar.py); nada foi alterado. Confira a diferença e, se a mudança for "
                                  "legítima, registre os hashes novos (o titular decide)",
                          "skill_creator": str(creator), "divergentes": divergentes},
                         ensure_ascii=False), file=sys.stderr)
        return 2
    ferramenta = {"skill_creator": str(creator),
                  "package_skill_sha256": FERRAMENTA_ESPERADA.get("scripts/package_skill.py"),
                  "quick_validate_sha256": FERRAMENTA_ESPERADA.get("scripts/quick_validate.py"),
                  "arquivos_conferidos": dict(sorted(FERRAMENTA_ESPERADA.items()))}
    dist.mkdir(parents=True, exist_ok=True)
    preparo = dist / f".preparo-{datetime.now(timezone.utc):%Y%m%dT%H%M%S%fZ}"
    preparo.mkdir()
    try:
        arquivos = arquivos_da_skill(SKILL)  # antes do package_skill, que também seguiria as ligações (#1)
        with tempfile.TemporaryDirectory(prefix="empacotar-ferramenta-") as copia:
            for rel, dados in lida.items():  # só os arquivos registrados, com os bytes conferidos (#6)
                (Path(copia) / rel).parent.mkdir(parents=True, exist_ok=True)
                (Path(copia) / rel).write_bytes(dados)
            # A pasta de trabalho é a cópia: o `-m` a põe no começo do sys.path, e lá só há os arquivos conferidos;
            # `-E` ignora PYTHONPATH e afins. UTF-8 no filho (`-X utf8`): o package_skill imprime emojis, e o console
            # cp1252 do Windows quebraria.
            r = subprocess.run([sys.executable, "-E", "-X", "utf8", "-B", "-m", "scripts.package_skill", str(SKILL),
                                str(preparo)], cwd=copia, capture_output=True, text=True, encoding="utf-8",
                               errors="replace")
        print((r.stdout or "").strip()[-800:])
        if r.returncode != 0:
            print((r.stderr or "")[-800:], file=sys.stderr)
            raise RuntimeError("o empacotador do skill-creator falhou")
        skill_pkg, completo = preparo / f"{NOME}.skill", preparo / f"{NOME}-completo.zip"
        problemas = conferir_pacote(skill_pkg, com_evals=False)
        if problemas:
            raise RuntimeError("; ".join(problemas))
        with zipfile.ZipFile(completo, "w", zipfile.ZIP_DEFLATED) as z:
            for p in arquivos:
                z.write(p, (Path(SKILL.name) / p.relative_to(SKILL)).as_posix())
        problemas = conferir_pacote(completo, com_evals=(SKILL / "evals").is_dir())
        if problemas:
            raise RuntimeError("; ".join(problemas))
        for pacote, e_completo in ((skill_pkg, False), (completo, True)):
            # Exatamente a árvore, antes de o SHA256SUMS.txt existir: a mesma regra da CI pública (Codex Security, #6).
            problemas = VERIFICADOR.conferir_contra_a_arvore(pacote, SKILL, completo=e_completo)
            if problemas:
                raise RuntimeError(f"{pacote.name} não é a árvore da skill: " + "; ".join(problemas[:10]))
        hashes = {p.name: sha256(p) for p in (skill_pkg, completo)}
        (preparo / "SHA256SUMS.txt").write_text("".join(f"{h}  {n}\n" for n, h in hashes.items()),
                                                encoding="utf-8", newline="\n")
        for n, h in hashes.items():  # conferência final: o que vai ser promovido é o que foi conferido
            if sha256(preparo / n) != h:
                raise RuntimeError(f"hash de {n} mudou durante a preparação")
        with zipfile.ZipFile(skill_pkg) as z:
            n_skill = len(z.namelist())
        with zipfile.ZipFile(completo) as z:
            n_completo = len(z.namelist())
        versao = versao_da_skill((SKILL / "SKILL.md").read_text(encoding="utf-8"))
        historico, _ausente = VERIFICADOR.ler_historico(dist.parent / VERIFICADOR.HISTORICO)  # ausente: vazia
        outro = [n for n, h in hashes.items() if historico.get(f"{versao}/{n}") not in (None, h)]
        if outro:  # a lista só cresce: o mesmo pacote de uma versão não muda de conteúdo (R177-ATU-04)
            raise RuntimeError(f"a versão {versao} já tem pacote com outro conteúdo em {VERIFICADOR.HISTORICO} ("
                               f"{', '.join(outro)}): suba a versão no SKILL.md antes de empacotar")
        (preparo / "EMPACOTAMENTO.json").write_text(json.dumps({
            "versao": versao, "gerado_em": datetime.now(timezone.utc).isoformat(timespec="seconds"),
            "ferramenta": ferramenta, "arquivos": {skill_pkg.name: n_skill, completo.name: n_completo},
            "sha256": hashes}, ensure_ascii=False, indent=2) + "\n", encoding="utf-8", newline="\n")
    except (RuntimeError, OSError, zipfile.BadZipFile) as exc:
        shutil.rmtree(preparo, ignore_errors=True)
        print(json.dumps({"erro": str(exc), "distribuicao_anterior": "preservada"}, ensure_ascii=False),
              file=sys.stderr)
        return 1
    anterior = dist / f"{NOME}.skill"
    versao_anterior = versao_do_pacote(anterior) if anterior.exists() else "desconhecida"
    try:
        arquivo = promover(dist, preparo, versao_anterior)
    except OSError as exc:
        print(json.dumps({"erro": f"falha ao promover: {exc}", "distribuicao_anterior": "devolvida"},
                         ensure_ascii=False), file=sys.stderr)
        return 1
    finally:
        shutil.rmtree(preparo, ignore_errors=True)
    try:
        acrescentar_ao_historico(dist.parent / VERIFICADOR.HISTORICO, versao, hashes)
    except OSError as exc:
        linhas = [f"{h}  {versao}/{n}" for n, h in hashes.items()]
        print(json.dumps({"erro": f"dist/ promovido, mas {VERIFICADOR.HISTORICO} não foi atualizada ({exc}): "
                                  "acrescente estas linhas a ela", "linhas": linhas}, ensure_ascii=False),
              file=sys.stderr)
        return 1
    for n, h in hashes.items():
        print(f"{h}  {n}")
    print(f"{NOME}.skill: {n_skill} arquivos; {NOME}-completo.zip: {n_completo} arquivos; versão {versao}")
    print(f"conjunto anterior arquivado em: {arquivo}" if arquivo else "não havia conjunto anterior")
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
