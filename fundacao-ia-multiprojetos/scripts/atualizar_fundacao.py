#!/usr/bin/env python3
"""Atualiza uma fundação para o kit desta skill num só comando, com ensaio antes e registro depois (fluxo C6).

  checar   --raiz R                    só lê: versões, o que muda arquivo a arquivo, identidade e cadeia de eventos
  aplicar  --raiz R --backups PASTA    ensaia numa cópia e só então atualiza a raiz
  desfazer --registro ARQ.json         devolve o código anterior, se o banco não mudou de esquema

`aplicar`, em sequência, parando no primeiro problema (nada é escrito na raiz antes do passo 4):
  1. `checar`: recusa se algum arquivo de código foi ALTERADO LOCALMENTE desde a instalação (difere do kit
     novo e do hash registrado em registry/kit_install.json) — isso é decisão C6 à parte — ou se faltar a
     identidade da administração ou a cadeia de eventos não conferir;
  2. backup ANTES (código atual da raiz): `backup criar` + `backup verificar`, em PASTA/antes-kit-<versão>-<data>;
  3. ensaio: restaura essa cópia numa pasta temporária, aplica o kit novo (`instalar_kit.py --atualizar`), roda
     `init`, `eventos verificar` e a suíte de conformidade NELA. Falha de teste que já acontecia na raiz antes da
     atualização é relatada, mas não bloqueia; falha nova (regressão) bloqueia;
  4. promoção na raiz: `instalar_kit.py --atualizar` (guarda os arquivos substituídos), `init` e `eventos verificar`;
  5. backup DEPOIS (código novo, com âncora) + `backup verificar`;
  6. registro em <raiz>/evidence/atualizacoes/ e resumo em linguagem simples.
`desfazer` devolve os arquivos substituídos (registry/kit_backup/...) e apaga os criados pela atualização, só se o
`user_version` do banco não mudou; se mudou, a volta é restaurar a cópia ANTES numa pasta nova (C9).

Identidade: FUNDACAO_PRINCIPAL vem do lançador (administração da fundação); este script não a define.
Saída em JSON; códigos: 0 ok · 1 recusado ou falhou (com `etapa` e `motivo`) · 2 uso incorreto.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import sqlite3
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
KIT = AQUI.parent / "assets" / "fundacao-kit"
INSTALAR_KIT = AQUI / "instalar_kit.py"
CONFIGURACAO = "registry"
IGNORAR = {"__pycache__", ".pytest_cache"}
VARIAVEL_IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
TEMPO = 3600
RUNNER = r"""
import json, os, sys, unittest
suite = unittest.defaultTestLoader.discover("tests", pattern=sys.argv[1])
with open(os.devnull, "w", encoding="utf-8") as nada:
    r = unittest.TextTestRunner(stream=nada, verbosity=0).run(suite)
falhas = r.failures + r.errors
print(json.dumps({"total": r.testsRun, "falhas": sorted(t.id() for t, _ in falhas),
                  "detalhes": {t.id(): tb[-1200:] for t, tb in falhas}, "pulados": len(r.skipped)}))
"""


class Parada(Exception):
    """Interrompe `aplicar` ou `desfazer` na etapa indicada; nada além do já relatado foi feito."""

    def __init__(self, etapa: str, motivo: str, **detalhes):
        super().__init__(motivo)
        self.etapa, self.motivo, self.detalhes = etapa, motivo, detalhes


def sha(p: Path) -> str:
    return hashlib.sha256(Path(p).read_bytes()).hexdigest()


def agora() -> str:
    return datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")


def versao_do_kit(base: Path) -> str | None:
    init = Path(base) / "fundacao" / "__init__.py"
    if not init.is_file():
        return None
    m = re.search(r'^KIT_VERSION\s*=\s*"([^"]+)"', init.read_text(encoding="utf-8"), re.M)
    return m.group(1) if m else None


def tupla(v: str | None) -> tuple:
    return tuple(int(x) if x.isdigit() else x for x in re.split(r"[.\-]", v or "0"))


def arquivos_do_kit(kit: Path = KIT) -> dict[str, str]:
    """Código e modelos do kit (fora de registry/, que é configuração local): caminho -> sha256."""
    out = {}
    for p in sorted(kit.rglob("*")):
        rel = p.relative_to(kit)
        if p.is_file() and not set(rel.parts) & IGNORAR and p.suffix not in (".pyc", ".sqlite") \
                and rel.parts[0] != CONFIGURACAO:
            out[rel.as_posix()] = sha(p)
    return out


def hashes_instalados(raiz: Path) -> dict[str, str]:
    """Último hash que o `instalar_kit.py` registrou para cada arquivo (copiado ou substituído)."""
    arq = Path(raiz) / "registry" / "kit_install.json"
    conhecidos: dict[str, str] = {}
    try:
        historico = json.loads(arq.read_text(encoding="utf-8"))
    except (OSError, ValueError):
        return conhecidos
    for reg in historico if isinstance(historico, list) else []:
        for item in reg.get("copiados") or []:
            if isinstance(item, dict) and item.get("path") and item.get("sha256"):
                conhecidos[item["path"]] = item["sha256"]
        for item in reg.get("substituidos") or []:
            if isinstance(item, dict) and item.get("path") and item.get("sha256_novo"):
                conhecidos[item["path"]] = item["sha256_novo"]
    return conhecidos


def ambiente() -> dict:
    return {**os.environ, "PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"}


def rodar(cmd: list, cwd: Path, timeout: int = TEMPO) -> tuple:
    """(código, JSON da saída ou None, fim do stderr)."""
    r = subprocess.run([str(c) for c in cmd], cwd=str(cwd), env=ambiente(), capture_output=True, text=True,
                       encoding="utf-8", errors="replace", timeout=timeout)
    texto = (r.stdout or "").strip()
    dados = None
    for inicio in (0, texto.rfind("\n{") + 1):
        try:
            dados = json.loads(texto[inicio:])
            break
        except ValueError:
            continue
    return r.returncode, dados, (r.stderr or "")[-2000:]


def fundacao(raiz: Path, *args: str) -> tuple:
    """CLI do kit DA PRÓPRIA RAIZ (o código que ela executa hoje)."""
    return rodar([sys.executable, "-B", "-m", "fundacao", "--raiz", str(raiz), *args], cwd=raiz)


def suite(raiz: Path, padrao: str) -> dict:
    """Suíte de conformidade da raiz: total, ids das falhas e pulados."""
    _code, dados, erro = rodar([sys.executable, "-B", "-c", RUNNER, padrao], cwd=raiz)
    if not isinstance(dados, dict):
        return {"total": 0, "falhas": ["suite-nao-rodou: " + erro[-300:]], "pulados": 0}
    return dados


def user_version(raiz: Path):
    db = Path(raiz) / "state" / "state.sqlite"
    if not db.is_file():
        return None
    con = sqlite3.connect(db.resolve().as_uri() + "?mode=ro", uri=True)
    try:
        return con.execute("PRAGMA user_version").fetchone()[0]
    finally:
        con.close()


def checar(raiz: Path) -> dict:
    """Só lê. `pode_aplicar` e os `motivos` de recusa, com o que muda arquivo a arquivo."""
    raiz = Path(raiz).resolve()
    res = {"raiz": str(raiz), "kit_na_raiz": versao_do_kit(raiz), "kit_da_skill": versao_do_kit(KIT), "motivos": []}
    if res["kit_na_raiz"] is None or not (raiz / "state" / "state.sqlite").is_file():
        res["motivos"].append("a pasta não é uma fundação instalada pelo kit (fundacao/__init__.py e state/state.sqlite)")
        res["pode_aplicar"] = False
        return res
    if tupla(res["kit_da_skill"]) < tupla(res["kit_na_raiz"]):
        res["motivos"].append("o kit desta skill é mais antigo que o da raiz: atualize a skill antes")
    conhecidos = hashes_instalados(raiz)
    mudancas = {"copiar": [], "atualizar": [], "identicos": 0, "alterados_localmente": []}
    for rel, novo in arquivos_do_kit().items():
        alvo = raiz / rel
        if not alvo.exists():
            mudancas["copiar"].append(rel)
        elif not alvo.is_file():
            mudancas["alterados_localmente"].append({"path": rel, "motivo": "no destino não é arquivo"})
        else:
            atual = sha(alvo)
            if atual == novo:
                mudancas["identicos"] += 1
            elif conhecidos.get(rel) == atual:
                mudancas["atualizar"].append(rel)
            else:
                motivo = ("difere do kit novo e do hash registrado na instalação" if rel in conhecidos
                          else "sem hash de instalação registrado")
                mudancas["alterados_localmente"].append({"path": rel, "motivo": motivo})
    res["mudancas"] = mudancas
    if mudancas["alterados_localmente"]:
        res["motivos"].append("há arquivo de código alterado localmente desde a instalação: a atualização o "
                              "substituiria; revise-o antes (fluxo C6)")
    res["identidade"] = os.environ.get(VARIAVEL_IDENTIDADE) or None
    if not res["identidade"]:
        res["motivos"].append("identidade ausente: " + VARIAVEL_IDENTIDADE + " vem do lançador (administração da fundação)")
    code, dados, erro = fundacao(raiz, "eventos", "verificar")
    res["cadeia_de_eventos"] = dados if dados is not None else {"erro": erro[-300:]}
    if code != 0:
        res["motivos"].append("a cadeia de eventos da raiz não confere: investigue antes de atualizar")
    res["user_version"] = user_version(raiz)
    res["nada_a_fazer"] = not (mudancas["copiar"] or mudancas["atualizar"] or mudancas["alterados_localmente"])
    res["pode_aplicar"] = not res["motivos"]
    return res


def _backup(raiz: Path, destino: Path, rotulo: str) -> dict:
    """`backup criar` + `backup verificar` com o código da raiz; a âncora vem do kit ou é calculada aqui."""
    code, dados, erro = fundacao(raiz, "backup", "criar", "--destino", str(destino), "--rotulo", rotulo)
    if code != 0 or not isinstance(dados, dict):
        raise Parada("backup", "`backup criar` falhou (" + rotulo + ")", erro=erro, saida=dados)
    ancora = dados.get("sha256_manifesto") or sha(destino / "manifest.json")
    extra = ["--sha256-manifesto", ancora] if dados.get("sha256_manifesto") else []
    code, ver, erro = fundacao(raiz, "backup", "verificar", "--origem", str(destino), *extra)
    if code != 0 or not (isinstance(ver, dict) and ver.get("ok")):
        raise Parada("backup", "a cópia " + rotulo + " não conferiu", erro=erro, verificacao=ver)
    return {"pasta": str(destino), "rotulo": rotulo, "sha256_manifesto": ancora,
            "ancora_pelo_kit": bool(dados.get("sha256_manifesto")), "arquivos": len(dados.get("files", []))}


def _instalar_kit(destino: Path) -> dict:
    code, dados, erro = rodar([sys.executable, "-B", str(INSTALAR_KIT), "--destino", str(destino), "--atualizar"],
                              cwd=AQUI)
    if code != 0 or not isinstance(dados, dict) or dados.get("composicao") != "verificada":
        raise Parada("instalar_kit", "o kit não ficou verificado em " + str(destino), codigo=code, saida=dados,
                     erro=erro)
    return dados


def _init_e_cadeia(raiz: Path, etapa: str) -> dict:
    code, init, erro = fundacao(raiz, "init")
    if code != 0:
        raise Parada(etapa, "`init` falhou", erro=erro, saida=init)
    code, cadeia, erro = fundacao(raiz, "eventos", "verificar")
    if code != 0:
        raise Parada(etapa, "a cadeia de eventos não conferiu depois do `init`", erro=erro, saida=cadeia)
    return {"init": init, "cadeia_de_eventos": cadeia}


def _ensaio(raiz: Path, antes: dict, padrao: str, manter: bool = False) -> dict:
    """Restaura a cópia ANTES numa pasta temporária e aplica nela o kit novo, com `init`, cadeia e suíte.
    Regressão = teste que falha na cópia atualizada e não falhava na raiz antes. A cópia tem os dados da fundação:
    é apagada no fim, também na falha (o registro guarda o motivo de cada teste), salvo com `manter`."""
    base = suite(raiz, padrao)
    tmp = Path(tempfile.mkdtemp(prefix="ensaio-atualizacao-"))
    try:
        return _ensaio_na_copia(raiz, antes, padrao, base, tmp / "raiz")
    except Parada as p:
        if not manter:
            p.detalhes["copia_de_ensaio"] = None
            p.detalhes["copia_apagada"] = "use --manter-ensaio para examiná-la"
        raise
    finally:
        if not manter:
            shutil.rmtree(tmp, ignore_errors=True)


def _ensaio_na_copia(raiz: Path, antes: dict, padrao: str, base: dict, copia: Path) -> dict:
    extra = ["--sha256-manifesto", antes["sha256_manifesto"]] if antes["ancora_pelo_kit"] else []
    code, rest, erro = fundacao(raiz, "backup", "restaurar", "--origem", antes["pasta"], "--destino", str(copia),
                                "--retiradas", str(raiz / "state" / "retiradas.jsonl"), *extra)
    if code != 0 or not (isinstance(rest, dict) and rest.get("released")):
        raise Parada("ensaio", "a cópia ANTES não restaurou numa pasta de ensaio", erro=erro, saida=rest,
                     copia_de_ensaio=str(copia))
    kit = _instalar_kit(copia)
    conferencia = _init_e_cadeia(copia, "ensaio")
    depois = suite(copia, padrao)
    regressoes = sorted(set(depois["falhas"]) - set(base["falhas"]))
    ensaio = {"suite_antes_na_raiz": base, "suite_na_copia_atualizada": depois, "regressoes": regressoes,
              "falhas_que_ja_existiam": sorted(set(depois["falhas"]) & set(base["falhas"])),
              "kit": {"substituidos": len(kit.get("substituidos", [])), "copiados": len(kit.get("copiados", []))},
              "user_version_na_copia": (conferencia["init"] or {}).get("user_version")}
    if regressoes:
        raise Parada("ensaio", "a atualização quebra testes que passavam antes; a raiz NÃO foi alterada",
                     regressoes=regressoes, ensaio=ensaio, copia_de_ensaio=str(copia))
    return ensaio


def _gravar(raiz: Path, nome: str, dados: dict) -> Path:
    pasta = Path(raiz) / "evidence" / "atualizacoes"
    pasta.mkdir(parents=True, exist_ok=True)
    arq = pasta / nome
    with open(arq, "x", encoding="utf-8", newline="\n") as fh:
        fh.write(json.dumps(dados, ensure_ascii=False, indent=1) + "\n")
    return arq


def aplicar(raiz: Path, backups: Path, padrao: str, manter_ensaio: bool = False) -> dict:
    raiz, backups = Path(raiz).resolve(), Path(backups).resolve()
    carimbo = agora()
    pre = checar(raiz)
    if not pre["pode_aplicar"]:
        raise Parada("checar", "; ".join(pre["motivos"]), checar=pre)
    if pre["nada_a_fazer"]:
        return {"ok": True, "nada_a_fazer": True, "checar": pre,
                "resumo": ["A fundação já está no kit " + str(pre["kit_na_raiz"]) + ": nada a fazer."]}
    nova, antiga = pre["kit_da_skill"], pre["kit_na_raiz"]
    registro = {"schema_version": "fundacao.atualizacao/1", "raiz": str(raiz), "iniciado_em": carimbo,
                "kit_antes": antiga, "kit_da_skill": nova, "identidade": pre["identidade"],
                "mudancas": pre["mudancas"], "user_version_antes": pre["user_version"]}
    try:
        rotulo = "antes-kit-" + nova + "-" + carimbo
        registro["antes"] = _backup(raiz, backups / rotulo, rotulo)
        registro["ensaio"] = _ensaio(raiz, registro["antes"], padrao, manter_ensaio)
        registro["promocao"] = {"instalar_kit": _instalar_kit(raiz)}
        registro["promocao"].update(_init_e_cadeia(raiz, "promocao"))
        registro["user_version_depois"] = user_version(raiz)
        rotulo = "depois-kit-" + nova + "-" + carimbo
        registro["depois"] = _backup(raiz, backups / rotulo, rotulo)
    except Parada as p:
        registro["falha"] = {"etapa": p.etapa, "motivo": p.motivo, **p.detalhes}
        nome = "falha-atualizacao-kit-" + nova + "-" + carimbo + ".json"
        p.detalhes["registro"] = str(_gravar(raiz, nome, registro))
        raise
    registro["kit_depois"] = versao_do_kit(raiz)
    registro["concluido_em"] = agora()
    arq = _gravar(raiz, "atualizacao-kit-" + nova + "-" + carimbo + ".json", registro)
    ensaio = registro["ensaio"]
    resumo = ["Fundação atualizada do kit " + str(antiga) + " para " + str(registro["kit_depois"]) + ".",
              "Cópia de segurança ANTES: " + registro["antes"]["pasta"] + " (âncora "
              + registro["antes"]["sha256_manifesto"][:12] + "...).",
              "Ensaio numa cópia restaurada: " + str(ensaio["suite_na_copia_atualizada"]["total"])
              + " testes, nenhuma regressão.",
              "Cópia de segurança DEPOIS: " + registro["depois"]["pasta"] + " (âncora "
              + registro["depois"]["sha256_manifesto"][:12] + "...).",
              "Registro: " + str(arq) + "."]
    if ensaio["falhas_que_ja_existiam"]:
        resumo.append("Atenção: " + str(len(ensaio["falhas_que_ja_existiam"])) + " teste(s) já falhava(m) antes e "
                      "continua(m) falhando (não é regressão): " + ", ".join(ensaio["falhas_que_ja_existiam"][:3]))
    resumo.append("Para voltar o código: python " + Path(__file__).name + " desfazer --registro " + str(arq))
    return {"ok": True, "registro": str(arq), "resumo": resumo}


def desfazer(registro_arq: Path, aceitar_banco_migrado: bool) -> dict:
    """Devolve o código anterior à atualização registrada, se o esquema do banco não mudou."""
    reg = json.loads(Path(registro_arq).read_text(encoding="utf-8"))
    raiz = Path(reg["raiz"])
    kit = reg["promocao"]["instalar_kit"]
    atual = user_version(raiz)
    if atual != reg.get("user_version_antes") and not aceitar_banco_migrado:
        raise Parada("desfazer", "o banco mudou de esquema desde a atualização (user_version "
                     + str(reg.get("user_version_antes")) + " -> " + str(atual) + "): voltar só o código deixaria "
                     "o kit antigo com um banco novo. Restaure a cópia ANTES numa pasta nova (fluxo C9)",
                     copia_antes=reg["antes"]["pasta"])
    backup = Path(kit["backup_dos_substituidos"]) if kit.get("backup_dos_substituidos") else None
    for item in kit.get("substituidos", []):  # confere tudo antes de alterar qualquer arquivo
        origem = backup / item["path"] if backup else None
        if origem is None or not origem.is_file() or sha(origem) != item["sha256_anterior"]:
            raise Parada("desfazer", "a cópia anterior de " + item["path"] + " está ausente ou diferente em "
                         "registry/kit_backup; nada foi alterado")
    devolvidos, apagados = [], []
    for item in kit.get("substituidos", []):
        shutil.copy2(backup / item["path"], raiz / item["path"])
        devolvidos.append(item["path"])
    for item in kit.get("copiados", []):
        alvo = raiz / item["path"]
        if alvo.is_file() and sha(alvo) == item["sha256"]:
            alvo.unlink()
            apagados.append(item["path"])
    versao = versao_do_kit(raiz)
    res = {"ok": True, "kit_na_raiz": versao, "devolvidos": devolvidos, "apagados": apagados,
           "resumo": ["Código devolvido ao kit " + str(versao) + ": " + str(len(devolvidos))
                      + " arquivo(s) devolvido(s) e " + str(len(apagados)) + " apagado(s). O banco não foi tocado."]}
    nome = "desfeita-" + Path(registro_arq).stem + "-" + agora() + ".json"
    res["registro"] = str(_gravar(raiz, nome, {**res, "atualizacao": str(registro_arq)}))
    return res


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("checar")
    c.add_argument("--raiz", type=Path, required=True)
    a = sub.add_parser("aplicar")
    a.add_argument("--raiz", type=Path, required=True)
    a.add_argument("--backups", type=Path, required=True,
                   help="pasta das cópias ANTES e DEPOIS (de preferência em outro disco)")
    a.add_argument("--padrao-testes", default="test*.py", help="padrão da suíte de conformidade no ensaio")
    a.add_argument("--manter-ensaio", action="store_true",
                   help="não apaga a cópia de ensaio (ela tem os dados da fundação; apague-a depois de examinar)")
    d = sub.add_parser("desfazer")
    d.add_argument("--registro", type=Path, required=True)
    d.add_argument("--aceitar-banco-migrado", action="store_true",
                   help="volta o código mesmo com o banco em esquema novo (decisão da administração)")
    args = ap.parse_args(argv)
    try:
        if args.cmd == "checar":
            res = checar(args.raiz)
            print(json.dumps(res, ensure_ascii=False, indent=1))
            return 0 if res["pode_aplicar"] else 1
        if args.cmd == "aplicar":
            res = aplicar(args.raiz, args.backups, args.padrao_testes, args.manter_ensaio)
        else:
            res = desfazer(args.registro, args.aceitar_banco_migrado)
    except Parada as p:
        print(json.dumps({"ok": False, "etapa": p.etapa, "motivo": p.motivo, **p.detalhes}, ensure_ascii=False,
                         indent=1))
        return 1
    print(json.dumps(res, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    sys.stdout.reconfigure(encoding="utf-8")
    sys.stderr.reconfigure(encoding="utf-8")
    raise SystemExit(main())
