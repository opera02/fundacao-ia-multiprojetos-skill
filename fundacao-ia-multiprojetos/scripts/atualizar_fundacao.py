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
     depois, as instruções da raiz (AGENTS.md e CLAUDE.md, `instrucoes_raiz.py gerar`), sem bloquear;
  5. backup DEPOIS (código novo, com âncora) + `backup verificar`;
  6. registro em <raiz>/evidence/atualizacoes/ e resumo em linguagem simples.
`desfazer` devolve os arquivos substituídos (registry/kit_backup/...) e apaga os criados pela atualização (as
instruções da raiz também, salvo se editadas depois), só se o
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
import stat
import subprocess
import sys
import tempfile
from datetime import datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent
KIT = AQUI.parent / "assets" / "fundacao-kit"
INSTALAR_KIT = AQUI / "instalar_kit.py"
INVENTARIAR_HOST = AQUI / "inventariar_host.py"
INVENTARIO_HOST = Path("registry") / "inventario-host.json"  # R54: skills, plugins, MCP e hooks do host
INSTRUCOES_RAIZ = AQUI / "instrucoes_raiz.py"  # AGENTS.md e CLAUDE.md gerados na raiz (proposta 1)
CONFIGURACAO = "registry"
IGNORAR = {"__pycache__", ".pytest_cache"}
VARIAVEL_IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
TEMPO = 3600
AREAS_DE_CODIGO = ("fundacao", "templates", "tests")
RETIRADAS = "tests/testes_retirados.json"  # no kit novo: ID do teste retirado de propósito -> versão e motivo
RUNNER = r"""
import json, os, sys, unittest
suite = unittest.defaultTestLoader.discover("tests", pattern=sys.argv[1])
ids = []
def coletar(s):
    for t in s:
        coletar(t) if isinstance(t, unittest.TestSuite) else ids.append(t.id())
coletar(suite)
with open(os.devnull, "w", encoding="utf-8") as nada:
    r = unittest.TextTestRunner(stream=nada, verbosity=0).run(suite)
falhas = r.failures + r.errors
print(json.dumps({"total": r.testsRun, "ids": sorted(ids), "falhas": sorted(t.id() for t, _ in falhas),
                  "detalhes": {t.id(): tb[-1200:] for t, tb in falhas}, "pulados": len(r.skipped),
                  "pulados_ids": {t.id(): str(m)[:200] for t, m in r.skipped}}))
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
        if not isinstance(reg, dict):
            continue
        for chave, campo in (("copiados", "sha256"), ("identicos_registrados", "sha256"),
                             ("substituidos", "sha256_novo")):
            for item in reg.get(chave) or []:
                if isinstance(item, dict) and item.get("path") and item.get(campo):
                    conhecidos[item["path"]] = item[campo]
        for item in reg.get("orfaos_retirados") or []:  # já guardados no backup por uma atualização
            if isinstance(item, dict):
                conhecidos.pop(item.get("path"), None)
    return conhecidos


def retiradas_declaradas(kit: Path = KIT) -> dict:
    """Testes que o kit novo retirou de propósito (`tests/testes_retirados.json`): ID -> versão e motivo."""
    arq = Path(kit) / RETIRADAS
    try:
        dados = json.loads(arq.read_text(encoding="utf-8"))
    except FileNotFoundError:
        return {}
    except (OSError, ValueError) as exc:
        raise Parada("checar", "a declaração de testes retirados do kit não é JSON válido", erro=str(exc))
    if not isinstance(dados, dict) or not all(isinstance(v, dict) and str(v.get("motivo", "")).strip()
                                              for v in dados.values()):
        raise Parada("checar", "a declaração de testes retirados precisa de ID -> {versao, motivo}")
    return dados


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


def caminho_do_registro_valido(rel) -> bool:
    """Como no instalar_kit.py: relativo, barras normais, sem `..`, `.`, raiz, unidade ou `:` (VCT170-01/02)."""
    if not isinstance(rel, str) or not rel or chr(92) in rel or ":" in rel or rel.startswith("/"):
        return False
    return all(parte not in ("", ".", "..") for parte in rel.split("/"))


def com_ligacao(raiz: Path, rel: str) -> bool:
    """Algum componente do caminho, abaixo da raiz, é ligação simbólica ou junção? Conferido sem seguir (como o
    guarda_caminho.py e o backup do kit): `dentro()` resolve a ligação e aceitaria `tests/elo -> .claude`
    (revisão de segurança da 1.7.0, VCT170-04)."""
    atual = Path(raiz)
    for parte in rel.split("/"):
        atual = atual / parte
        try:
            st = os.lstat(atual)
        except OSError:
            return False  # o resto do caminho ainda não existe
        if stat.S_ISLNK(st.st_mode) or getattr(st, "st_reparse_tag", 0) & 0x20000000:  # substituto de nome
            return True
    return False


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
    mudancas = {"copiar": [], "atualizar": [], "identicos": 0, "alterados_localmente": [], "retirar": []}
    do_kit = arquivos_do_kit()
    mudancas["por_ligacao"] = []
    for rel, novo in do_kit.items():
        alvo = raiz / rel
        if com_ligacao(raiz, rel):
            mudancas["por_ligacao"].append(rel)
            continue
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
    # Órfãos: o kit anterior instalou, o novo não tem mais (o instalar_kit.py os guarda no backup).
    mudancas["entradas_invalidas"] = sorted(rel for rel in conhecidos if not caminho_do_registro_valido(rel))
    candidatos = [rel for rel in conhecidos if rel not in do_kit and caminho_do_registro_valido(rel)
                  and rel.split("/", 1)[0] in AREAS_DE_CODIGO and (raiz / rel).is_file()]
    mudancas["por_ligacao"] += sorted(rel for rel in candidatos if com_ligacao(raiz, rel))
    mudancas["retirar"] = sorted(rel for rel in candidatos if not com_ligacao(raiz, rel))
    res["mudancas"] = mudancas
    if mudancas["por_ligacao"]:
        res["motivos"].append("caminho do kit passa por ligação ou junção dentro da raiz ("
                              + ", ".join(mudancas["por_ligacao"][:5]) + "): a atualização escreveria ou retiraria "
                              "o arquivo do outro lado; investigue antes de atualizar")
    if mudancas["entradas_invalidas"]:
        res["motivos"].append("registry/kit_install.json tem caminho que o instalador nunca grava (com `..`, absoluto "
                              "ou com barra invertida): o registro pode ter sido adulterado; investigue antes de "
                              "atualizar")
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
    res["instrucoes_raiz"] = _plano_instrucoes(raiz)
    res["nada_a_fazer"] = not (mudancas["copiar"] or mudancas["atualizar"] or mudancas["alterados_localmente"]
                               or mudancas["retirar"])
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
    Regressão = teste que falha na cópia atualizada e não falhava na raiz antes, ou que passava e na cópia
    sumiu ou passou a ser pulado sem a retirada declarada pelo kit novo (catraca, proposta 5). A cópia tem os
    dados da fundação: é apagada no fim, também na falha (o registro guarda o motivo de cada teste), salvo
    com `manter`."""
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
    declaradas = retiradas_declaradas()
    passavam = set(base.get("ids", [])) - set(base["falhas"]) - set(base.get("pulados_ids", {}))
    sumidos = sorted(set(base.get("ids", [])) - set(depois.get("ids", [])) - set(declaradas))
    pulados_novos = sorted((passavam & set(depois.get("pulados_ids", {}))) - set(declaradas))
    ensaio = {"suite_antes_na_raiz": base, "suite_na_copia_atualizada": depois, "regressoes": regressoes,
              "testes_sumidos": sumidos, "pulados_novos": pulados_novos,
              "retiradas_declaradas": sorted(set(declaradas) & set(base.get("ids", []))),
              "falhas_que_ja_existiam": sorted(set(depois["falhas"]) & set(base["falhas"])),
              "kit": {"substituidos": len(kit.get("substituidos", [])), "copiados": len(kit.get("copiados", [])),
                      "orfaos_retirados": len(kit.get("orfaos_retirados", []))},
              "user_version_na_copia": (conferencia["init"] or {}).get("user_version")}
    if regressoes or sumidos or pulados_novos:
        raise Parada("ensaio", "a atualização quebra, apaga ou passa a pular testes que passavam antes (sem a "
                     "retirada declarada em " + RETIRADAS + " do kit novo); a raiz NÃO foi alterada",
                     regressoes=regressoes, testes_sumidos=sumidos, pulados_novos=pulados_novos,
                     ensaio=ensaio, copia_de_ensaio=str(copia))
    return ensaio


def _inventario_host(raiz: Path) -> dict | None:
    """Confere o inventário do ecossistema do host (proposta 15), se a fundação tiver um. Não bloqueia: mudança
    no host é informação para o titular conferir e regravar, não falha da atualização do kit."""
    arq = raiz / INVENTARIO_HOST
    if not arq.is_file():
        return None
    _code, dados, erro = rodar([sys.executable, "-B", str(INVENTARIAR_HOST), "verificar", "--inventario", str(arq),
                                "--raiz", str(raiz)], cwd=AQUI)
    if not isinstance(dados, dict) or "diferencas" not in dados:
        return {"conferido": False, "erro": (erro or "")[-300:]}
    mudancas = {cat: {k: len(v) for k, v in d.items() if v} for cat, d in dados["diferencas"].items()}
    return {"conferido": True, "sem_mudancas": bool(dados.get("ok")),
            "mudancas": {cat: m for cat, m in mudancas.items() if m}}


def _plano_instrucoes(raiz: Path) -> dict:
    """Só lê (`instrucoes_raiz.py gerar --simular`): o que mudaria no AGENTS.md e no CLAUDE.md da raiz."""
    _code, dados, erro = rodar([sys.executable, "-B", str(INSTRUCOES_RAIZ), "gerar", "--raiz", str(raiz), "--simular"],
                               cwd=AQUI)
    if not isinstance(dados, dict):
        return {"erro": (erro or "")[-300:]}
    if not dados.get("ok"):
        return {"conflito": dados.get("conflito")}
    return {"AGENTS.md": dados["agents"]["acao"], "CLAUDE.md": dados["claude"]["acao"]}


def _instrucoes_raiz(raiz: Path, carimbo: str) -> dict:
    """Regenera o AGENTS.md e o CLAUDE.md da raiz (proposta 1), guardando antes os que já existiam, para o
    `desfazer`. Não bloqueia: AGENTS.md escrito à mão fica como está e o resumo pede a decisão do titular."""
    plano = _plano_instrucoes(raiz)
    if "erro" in plano or "conflito" in plano:
        return {"gerado": False, **plano}
    guarda = raiz / "registry" / "kit_backup" / ("instrucoes-" + carimbo)
    guardados = []
    try:
        for nome, acao in plano.items():
            if acao == "atualizar":
                guarda.mkdir(parents=True, exist_ok=True)
                shutil.copy2(raiz / nome, guarda / nome)
                guardados.append({"path": nome, "sha256_anterior": sha(guarda / nome)})
    except OSError as exc:
        return {"gerado": False, "erro": "a versão anterior não foi guardada: " + str(exc)}
    code, dados, erro = rodar([sys.executable, "-B", str(INSTRUCOES_RAIZ), "gerar", "--raiz", str(raiz)], cwd=AQUI)
    res = {"gerado": code == 0 and isinstance(dados, dict) and bool(dados.get("ok")), "acoes": plano,
           "copia": str(guarda) if guardados else None, "guardados": guardados}
    if res["gerado"]:
        res["sha256"] = {"AGENTS.md": dados["agents"]["sha256"], "CLAUDE.md": dados["claude"]["sha256"]}
    else:
        res["erro"] = (erro or "")[-300:]
    return res


def _resumo_instrucoes(raiz: Path, instr: dict) -> list:
    comando = "python " + INSTRUCOES_RAIZ.name + ' gerar --raiz "' + str(raiz) + '"'
    if instr.get("gerado"):
        mudou = [nome for nome, acao in instr["acoes"].items() if acao != "igual"]
        return (["Instruções da raiz geradas pela skill (" + ", ".join(mudou) + "): as sessões abertas nesta pasta "
                 "passam a lê-las ao iniciar."] if mudou else [])
    if instr.get("conflito"):
        return ["O AGENTS.md da raiz foi escrito à mão e não foi alterado. Revise-o e, para a skill passar a "
                "mantê-lo (o seu texto fica no trecho do titular), rode: " + comando + " --adotar"]
    return ["Atenção: as instruções da raiz não foram geradas (" + str(instr.get("erro"))[:200] + "); "
            "rode depois: " + comando]


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
        resumo = ["A fundação já está no kit " + str(pre["kit_na_raiz"]) + ": nada a fazer."]
        instr = pre["instrucoes_raiz"]
        if "AGENTS.md" not in instr or {instr["AGENTS.md"], instr["CLAUDE.md"]} != {"igual"}:
            resumo += _resumo_instrucoes(raiz, {"gerado": False, "erro": "desatualizadas ou ausentes", **instr})
        return {"ok": True, "nada_a_fazer": True, "checar": pre, "resumo": resumo}
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
        registro["instrucoes_raiz"] = _instrucoes_raiz(raiz, carimbo)  # antes da cópia DEPOIS, que as leva
        rotulo = "depois-kit-" + nova + "-" + carimbo
        registro["depois"] = _backup(raiz, backups / rotulo, rotulo)
    except Parada as p:
        registro["falha"] = {"etapa": p.etapa, "motivo": p.motivo, **p.detalhes}
        nome = "falha-atualizacao-kit-" + nova + "-" + carimbo + ".json"
        p.detalhes["registro"] = str(_gravar(raiz, nome, registro))
        raise
    registro["kit_depois"] = versao_do_kit(raiz)
    registro["inventario_host"] = _inventario_host(raiz)
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
    resumo += _resumo_instrucoes(raiz, registro["instrucoes_raiz"])
    host = registro["inventario_host"]
    if host and host.get("conferido"):
        resumo.append("Ecossistema do host (skills, plugins, MCP, hooks): " + (
            "igual ao inventário." if host["sem_mudancas"] else "mudou desde o inventário — confira e regrave com "
            "inventariar_host.py gravar --substituir: " + json.dumps(host["mudancas"], ensure_ascii=False)))
    resumo.append("Para voltar o código: python " + Path(__file__).name + " desfazer --registro " + str(arq))
    return {"ok": True, "registro": str(arq), "resumo": resumo}


INSTRUCOES = ("AGENTS.md", "CLAUDE.md")  # os únicos arquivos que as instruções da raiz tocam


def _dentro(caminho, base: Path) -> bool:
    try:
        Path(caminho).resolve().relative_to(Path(base).resolve())
        return True
    except (ValueError, OSError, RuntimeError):
        return False


def _conferir_registro(registro_arq: Path, reg: dict) -> Path:
    """O registro é dado (fica em evidence/, gravável por shell): só vale o desta raiz, com caminhos relativos sem
    `..`, cópias dentro de registry/kit_backup e instruções só AGENTS.md e CLAUDE.md (revisão de segurança da 1.7.0,
    VCT170-02). Devolve a raiz; qualquer desvio para antes de alterar o que for."""
    raiz = Path(registro_arq).resolve().parents[2]  # <raiz>/evidence/atualizacoes/<registro>.json
    if Path(str(reg.get("raiz") or "")).resolve() != raiz:
        raise Parada("desfazer", "o registro diz que a raiz é " + str(reg.get("raiz")) + ", mas ele está em " + str(raiz)
                     + ": só se desfaz a atualização registrada dentro da própria raiz; nada foi alterado")
    guarda = raiz / "registry" / "kit_backup"
    kit = (reg.get("promocao") or {}).get("instalar_kit") or {}
    instr = reg.get("instrucoes_raiz") or {}
    problemas = [campo + " fora de registry/kit_backup" for campo, pasta in
                 (("backup_dos_substituidos", kit.get("backup_dos_substituidos")), ("copia", instr.get("copia")))
                 if pasta and not _dentro(pasta, guarda)]
    for chave in ("substituidos", "copiados", "orfaos_retirados"):
        for item in kit.get(chave) or []:
            rel = item.get("path") if isinstance(item, dict) else None
            if not caminho_do_registro_valido(rel) or com_ligacao(raiz, rel) or not _dentro(raiz / rel, raiz):
                problemas.append(chave + ": caminho inválido ou atrás de ligação " + repr(rel)[:80])
            elif chave == "orfaos_retirados" and rel.split("/", 1)[0] not in AREAS_DE_CODIGO:
                problemas.append("orfaos_retirados: fora das áreas de código: " + rel)
    nomes = set(instr.get("acoes") or {}) | {i.get("path") for i in instr.get("guardados") or [] if isinstance(i, dict)}
    if not nomes <= set(INSTRUCOES):
        problemas.append("instrucoes_raiz: só AGENTS.md e CLAUDE.md")
    if problemas:
        raise Parada("desfazer", "o registro tem caminho fora do que a atualização grava (" + "; ".join(problemas[:5])
                     + "): pode ter sido adulterado; nada foi alterado")
    return raiz


def desfazer(registro_arq: Path, aceitar_banco_migrado: bool) -> dict:
    """Devolve o código anterior à atualização registrada, se o esquema do banco não mudou."""
    reg = json.loads(Path(registro_arq).read_text(encoding="utf-8"))
    raiz = _conferir_registro(Path(registro_arq), reg)
    kit = reg["promocao"]["instalar_kit"]
    atual = user_version(raiz)
    if atual != reg.get("user_version_antes") and not aceitar_banco_migrado:
        raise Parada("desfazer", "o banco mudou de esquema desde a atualização (user_version "
                     + str(reg.get("user_version_antes")) + " -> " + str(atual) + "): voltar só o código deixaria "
                     "o kit antigo com um banco novo. Restaure a cópia ANTES numa pasta nova (fluxo C9)",
                     copia_antes=(reg.get("antes") or {}).get("pasta"))
    backup = Path(kit["backup_dos_substituidos"]) if kit.get("backup_dos_substituidos") else None
    guardados = ([(i["path"], i["sha256_anterior"]) for i in kit.get("substituidos", [])]
                 + [(i["path"], i["sha256"]) for i in kit.get("orfaos_retirados", [])])
    for rel, esperado in guardados:  # confere tudo antes de alterar qualquer arquivo
        origem = backup / rel if backup else None
        if origem is None or not origem.is_file() or sha(origem) != esperado:
            raise Parada("desfazer", "a cópia anterior de " + rel + " está ausente ou diferente em "
                         "registry/kit_backup; nada foi alterado")
    instr = reg.get("instrucoes_raiz") or {}
    for item in instr.get("guardados", []):
        origem = Path(instr["copia"]) / item["path"]
        if not origem.is_file() or sha(origem) != item["sha256_anterior"]:
            raise Parada("desfazer", "a cópia anterior de " + item["path"] + " está ausente ou diferente em "
                         + instr["copia"] + "; nada foi alterado")
    devolvidos, apagados, orfaos = [], [], []
    for item in kit.get("substituidos", []):
        shutil.copy2(backup / item["path"], raiz / item["path"])
        devolvidos.append(item["path"])
    for item in kit.get("orfaos_retirados", []):  # o que o kit novo tinha retirado volta ao lugar
        (raiz / item["path"]).parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(backup / item["path"], raiz / item["path"])
        orfaos.append(item["path"])
    for item in kit.get("copiados", []):
        alvo = raiz / item["path"]
        if alvo.is_file() and sha(alvo) == item["sha256"]:
            alvo.unlink()
            apagados.append(item["path"])
    instrucoes = {"devolvidas": [], "apagadas": [], "mantidas": []}
    com_copia = {item["path"] for item in instr.get("guardados", [])}
    for nome, acao in (instr.get("acoes") or {}).items() if instr.get("gerado") else ():
        alvo = raiz / nome
        if acao == "igual" or not alvo.is_file():
            continue
        if sha(alvo) != instr["sha256"][nome]:  # editado depois da atualização: fica como está
            instrucoes["mantidas"].append(nome)
        elif nome in com_copia:
            shutil.copy2(Path(instr["copia"]) / nome, alvo)
            instrucoes["devolvidas"].append(nome)
        elif acao == "criar":
            alvo.unlink()
            instrucoes["apagadas"].append(nome)
    versao = versao_do_kit(raiz)
    res = {"ok": True, "kit_na_raiz": versao, "devolvidos": devolvidos, "apagados": apagados,
           "orfaos_devolvidos": orfaos, "instrucoes": instrucoes,
           "resumo": ["Código devolvido ao kit " + str(versao) + ": " + str(len(devolvidos))
                      + " arquivo(s) devolvido(s), " + str(len(orfaos)) + " retirado(s) recolocado(s) e "
                      + str(len(apagados)) + " apagado(s). O banco não foi tocado."]}
    if instrucoes["mantidas"]:
        res["resumo"].append("Instruções da raiz editadas depois da atualização ficaram como estão: "
                             + ", ".join(instrucoes["mantidas"]) + ".")
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
