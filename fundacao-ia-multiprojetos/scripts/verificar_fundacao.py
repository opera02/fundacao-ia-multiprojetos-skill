#!/usr/bin/env python3
"""Sete conferências de operação, sem executar o código da fundação nem corrigir seus arquivos.

  python -I -B <skill>/scripts/verificar_fundacao.py --raiz <fundacao> [--perfil <usuario>]
  ... --completo [--backup <ultima-copia-indicada> --sha256-manifesto <hash-externo>]
  ... [--timeout 60] [--saida <arquivo-novo.json>]

O modo rápido confere RETOMADA, matriz, instruções da raiz e inventário do host. Kit, cadeia e backup ficam
explicitamente não rodados: `atualizar_fundacao.py checar` também consulta o banco. O completo usa os scripts e o
kit desta skill, em Python isolado; nunca importa a raiz ou chama `python -m fundacao` nela. Não migra, restaura,
inicia a fundação, ativa rotas nem chama provedores. Não oferece --com-suite: falta o suporte à suíte em cópia
conferida e isolada neste comando. A validação estrutural da RETOMADA não autentica seu conteúdo.

Ausência, recusa, tempo esgotado e passo não rodado impedem `pronto_para_seguir`. Cadeia exige `cadeia_integra`
verdadeiro, além do código zero. Backup: a política administrativa da fundação viva autoriza a leitura, e o hash
externo autentica o manifesto; o livro não assinado de state/ não é usado. --backup indica a cópia que o operador
declara ser a última: não há descoberta automática nem comprovação de que inexiste outra mais recente.

Só leitura, inclusive SQLite: banco WAL fica não rodado, pois até `mode=ro` pode criar -wal/-shm. Use uma cópia
estável, fora de WAL, para estas conferências; o comando não cria essa cópia. Os erros são resumos fixos, sem
repassar stdout/stderr, conteúdo ou identidade. O timeout é por subprocesso (1 a 600 segundos).

--saida é a única gravação: arquivo novo .json em evidence/ da raiz, ou outputs/ e evidence/ do projeto autenticado
(FUNDACAO_PROJECT do lançador). Nomes protegidos, ligação/junção no caminho, vínculo físico e sobrescrita recusam.
Usa as mesmas primitivas de gravacao_segura.py; não troque pastas concorrentemente durante a gravação.
Saída JSON; código 0 só quando os sete passos conferem, 1 se falta conferência ou há recusa, 2 para uso incorreto.

O pre-flight percorre apenas metadados de fontes fixas. Recusa elos e vinculos fisicos tambem nas leituras
transitivas; scripts de hook fora das areas do host e codigo que exigiria ler decisoes de projeto ficam recusados.
O inventario anterior sem a impressao de statusLine fica pendente; regrave-o somente apos revisar as diferencas.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
KIT = AQUI.parent / "assets" / "fundacao-kit"
ESQUEMA = "fundacao.verificacao/1"
IDS = ("kit", "retomada", "matriz", "instrucoes", "host", "cadeia", "backup")
TETO_ENTRADA, TETO_SAIDA = 5_000_000, 2_000_000


def _vizinho(nome: str):
    spec = importlib.util.spec_from_file_location(nome, AQUI / (nome + ".py"))
    mod = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(mod)
    return mod


CONFERIDO = _vizinho("codigo_conferido")
GRAVACAO = _vizinho("gravacao_segura")
RETOMADA = _vizinho("retomada")

# Só a política viva: sem ela, autorizar() recorreria a um preparo privado gravado em disco. Esta rotina não faz
# esse preparo nem usa a ACL de uma cópia como se fosse a da fundação viva (R177-KIT-02).
BACKUP = """import json
from pathlib import Path
from fundacao.core.ancora_copia import _fundacao_viva
from fundacao.core.backup import verify_backup
autorizacao, _ = _fundacao_viva(Path(sys.argv[1]), Path(sys.argv[2]))
if autorizacao is None:
    print(json.dumps({"ok": False, "autorizado": False}))
else:
    res = verify_backup(Path(sys.argv[2]), sha256_manifesto=sys.argv[3])
    print(json.dumps({"ok": res.get("ok") is True, "autorizado": True,
                      "ancora_conferida": res.get("ancora", {}).get("situacao") == "conferida"}))
"""


def estado_caminho(caminho: Path, *, pasta: bool = False, teto: int | None = None) -> str:
    """Examina cada componente com lstat; não segue ligação nem abre arquivo de mais de um nome."""
    if ".." in Path(caminho).parts:
        return "recusado"
    caminho = Path(os.path.abspath(caminho))
    atual = Path(caminho.anchor)
    for i, parte in enumerate(caminho.parts[1:]):
        atual /= parte
        try:
            st = os.lstat(atual)
        except FileNotFoundError:
            return "ausente"
        except (OSError, ValueError):
            return "recusado"
        ultimo = i == len(caminho.parts) - 2
        if GRAVACAO.e_ligacao(st):
            return "recusado"
        if not ultimo or pasta:
            if not stat.S_ISDIR(st.st_mode):
                return "recusado"
        elif not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or (teto is not None and st.st_size > teto):
            return "recusado"
    return "presente"


def arvore_segura(base: Path) -> bool:
    """Pre-flight de metadados, sem seguir elos nem entrar em projetos, estado ou segredos."""
    estado = estado_caminho(base, pasta=True)
    if estado == "ausente":
        return True
    if estado != "presente":
        return False
    pilha, entradas = [(base, 0)], 0
    try:
        while pilha:
            pasta, nivel = pilha.pop()
            if nivel > 32:
                return False
            for nome in os.listdir(pasta):
                entradas += 1
                if entradas > 20000:
                    return False
                alvo = pasta / nome
                partes = alvo.relative_to(base).parts
                if (any(p.casefold() in ("projects", "state") for p in partes) or
                        RETOMADA.protegido(base, partes)):
                    return False
                st = os.lstat(alvo)
                if GRAVACAO.e_ligacao(st):
                    return False
                if stat.S_ISDIR(st.st_mode):
                    pilha.append((alvo, nivel + 1))
                elif (not stat.S_ISREG(st.st_mode) or st.st_nlink != 1 or st.st_size > TETO_ENTRADA):
                    return False
    except (OSError, ValueError):
        return False
    return True


def codigo_seguro(raiz: Path) -> bool:
    """Todas as leituras do checar: modelos, codigo, pacotes e arquivos instalados conhecidos."""
    if not all(arvore_segura(raiz / area) for area in CONFERIDO.AREAS_DE_CODIGO + CONFERIDO.IMPORTADOS_DE_FORA):
        return False
    arquivos, ligacoes = CONFERIDO.primeiro_nivel(raiz)
    if ligacoes or any(estado_caminho(p, teto=TETO_ENTRADA) != "presente" for p in arquivos.values()):
        return False
    for origem in KIT.rglob("*"):
        rel = origem.relative_to(KIT)
        if origem.is_file() and rel.parts[0] != "registry" and origem.suffix not in (".pyc", ".sqlite"):
            if estado_caminho(raiz / rel, teto=TETO_ENTRADA) == "recusado":
                return False
    # checar consulta decisoes de projeto e assinatura somente quando existe desvio sigiloso.
    politica = raiz / "registry/route_policy.json"
    if estado_caminho(politica) == "presente":
        try:
            local = json.loads(RETOMADA.ler_contido(politica, politica.parent, TETO_ENTRADA))
            distribuida = json.loads((KIT / "registry/route_policy.json").read_text(encoding="utf-8"))
            if local["task_routes"]["sigiloso"] != distribuida["task_routes"]["sigiloso"]:
                return False
        except (OSError, ValueError, KeyError, TypeError, RecursionError):
            return False
    return True


def host_seguro(raiz: Path, perfil: Path) -> bool:
    """Fontes fixas do inventario; nenhum caminho de config autoriza ler dados de projeto."""
    fontes = [(perfil, ".claude.json"), (perfil, ".codex/config.toml"), (raiz, ".mcp.json")]
    configs = [(perfil, ".claude/settings.json")] + [(raiz, ".claude/" + n) for n in
               ("settings.json", "settings.local.json", "settings.wsl.json")]
    arvores = [perfil / p for p in (".claude/skills", ".agents/skills", ".codex/skills", ".claude/plugins")]
    arvores.append(raiz / ".claude/skills")
    if not all(arvore_segura(p) for p in arvores):
        return False
    if any(estado_caminho(base / rel, teto=TETO_ENTRADA) == "recusado" for base, rel in fontes + configs):
        return False
    # So depois de validar os arquivos fixos, veja os nomes de scripts que o inventario abriria.
    permitidas = [perfil / n for n in (".claude", ".agents", ".codex")] + [raiz / ".claude"]
    for base, rel in configs:
        arquivo = base / rel
        if estado_caminho(arquivo) == "ausente":
            continue
        try:
            bruto = RETOMADA.ler_contido(arquivo, arquivo.parent, TETO_ENTRADA)
            dados = json.loads(bruto)
        except (OSError, ValueError, RecursionError):
            return False
        if not isinstance(dados, dict):
            continue  # o inventario devolvera a recusa de forma, sem procurar scripts
        hooks = dados.get("hooks")
        for grupos in hooks.values() if isinstance(hooks, dict) else ():
            for grupo in grupos if isinstance(grupos, list) else ():
                hs = grupo.get("hooks") if isinstance(grupo, dict) else None
                for h in hs if isinstance(hs, list) else ():
                    if not isinstance(h, dict):
                        continue
                    comando, args = h.get("command"), h.get("args")
                    if not isinstance(comando, str):
                        continue
                    partes = [comando, *args] if isinstance(args, list) and args else comando.split()
                    for parte in partes:
                        if not isinstance(parte, str):
                            continue
                        alvo = Path(parte.strip('"').replace(chr(92), "/"))
                        if ".." in alvo.parts:
                            return False
                        alvo = Path(os.path.abspath(alvo if alvo.is_absolute() else base / alvo))
                        if alvo.suffix.lower() not in (".py", ".ps1", ".sh", ".mjs", ".js", ".cmd", ".bat"):
                            continue
                        escopo = next((p for p in permitidas if alvo.is_relative_to(p)), None)
                        if escopo is None or RETOMADA.protegido(escopo, alvo.relative_to(escopo).parts):
                            return False
                        if estado_caminho(alvo, teto=TETO_ENTRADA) == "recusado":
                            return False
    return True


def executar(comando: list, timeout: int) -> tuple[int | None, dict | None, str]:
    """Fronteira de processos: argumentos separados, pasta confiável, limite e nenhum erro bruto na resposta."""
    env = {k: v for k, v in os.environ.items() if k not in
           {"PYTHONPATH", "PYTHONHOME", "PYTHONSTARTUP", "PYTHONINSPECT"}}
    env.update({"PYTHONDONTWRITEBYTECODE": "1", "PYTHONUTF8": "1"})
    try:
        p = subprocess.run(list(map(str, comando)), cwd=AQUI, env=env, capture_output=True, text=True,
                           encoding="utf-8", errors="replace", timeout=timeout)
    except subprocess.TimeoutExpired:
        return None, None, "tempo esgotado"
    except (OSError, ValueError):
        return None, None, "verificador indisponível"
    try:
        if len(p.stdout) > TETO_SAIDA:
            raise ValueError
        dados = json.loads(p.stdout)
        if not isinstance(dados, dict):
            raise ValueError
    except (ValueError, RecursionError):
        return p.returncode, None, "verificador sem resultado JSON válido"
    return p.returncode, dados, ""


def script(nome: str, *args) -> list:
    return [sys.executable, "-I", "-B", "-X", "utf8", AQUI / nome, *args]


def passo(nome: str, estado: str, motivo: str, acao: str) -> dict:
    return {"id": nome, "estado": estado, "motivo": motivo, "acao": "nenhuma" if estado == "ok" else acao}


def conferir(nome: str, comando: list, entradas: list, timeout: int, acao: str, criterio=None) -> dict:
    for p in entradas:
        estado = estado_caminho(p, teto=TETO_ENTRADA)
        if estado != "presente":
            return passo(nome, "nao_rodado" if estado == "ausente" else "falhou",
                         "pré-requisito indisponível" if estado == "ausente" else "caminho de entrada recusado", acao)
    codigo, dados, erro = executar(comando, timeout)
    if erro:
        return passo(nome, "erro", erro, acao)
    if nome == "host" and dados.get("conferencia_pendente") is True:
        return passo(nome, "nao_rodado", "inventario anterior sem conferencia de statusLine", acao)
    ok = codigo == 0 and (criterio(dados) if criterio else dados.get("ok") is True)
    return passo(nome, "ok" if ok else "falhou", "conferido" if ok else "a conferência não foi aprovada", acao)


def banco_estavel(raiz: Path) -> bool:
    """Só aceita SQLite fora de WAL; nunca o abre por SQLite para decidir se pode abri-lo sem gravação."""
    db = raiz / "state" / "state.sqlite"
    if estado_caminho(db) != "presente":
        return False
    # Mesmo com o cabeçalho fora de WAL, uma transação concorrente ou journal pendente exige snapshot estável.
    if any(os.path.lexists(str(db) + sufixo) for sufixo in ("-wal", "-shm", "-journal")):
        return False
    try:
        fd = os.open(db, os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0))
        try:
            st, depois = os.fstat(fd), os.lstat(db)
            if (st.st_nlink != 1 or GRAVACAO.e_ligacao(depois) or
                    (st.st_dev, st.st_ino) != (depois.st_dev, depois.st_ino)):
                return False
            cabecalho = os.read(fd, 20)
        finally:
            os.close(fd)
    except OSError:
        return False
    return cabecalho[:16] == b"SQLite format 3\x00" and cabecalho[18:20] == b"\x01\x01"


def verificar(raiz: Path, *, completo: bool = False, perfil: Path | None = None,
              backup: Path | None = None, sha256_manifesto: str | None = None, timeout: int = 60) -> dict:
    if ".." in Path(raiz).parts:
        return {"schema_version": ESQUEMA, "pronto_para_seguir": False, "passos": [],
                "erro": "raiz com travessia recusada; nada foi executado"}
    raiz = Path(os.path.abspath(raiz))
    if estado_caminho(raiz, pasta=True) != "presente" or RETOMADA.pasta_recusada(raiz / "rotina.json"):
        return {"schema_version": ESQUEMA, "pronto_para_seguir": False, "passos": [],
                "erro": "raiz indisponível ou caminho recusado; nada foi executado"}
    acao_banco = "Use --completo sobre uma cópia estável fora de WAL; não rode init para suprir ausências."
    pode_ler_banco = completo and banco_estavel(raiz)
    nao_banco = "modo rápido: leitura de banco não rodada" if not completo else "pré-requisitos de leitura estável indisponíveis"
    # O checar lê estes registros antes de montar seu próprio inventário; recuse nomes desviados antes de chamá-lo.
    registros = ("registry/kit_install.json", "registry/route_policy.json", "registry/configuracao-decidida.json",
                 "AGENTS.md", "CLAUDE.md")
    registro_recusado = completo and any(estado_caminho(raiz / rel, teto=TETO_ENTRADA) == "recusado" for rel in registros)
    if registro_recusado:
        kit = passo("kit", "falhou", "caminho de configuração recusado",
                    "Investigue ligação, vínculo físico ou arquivo incomum antes de conferir o kit.")
    elif pode_ler_banco and not codigo_seguro(raiz):
        kit = passo("kit", "falhou", "leitura transitiva de codigo recusada",
                    "Investigue caminhos protegidos, elos e vinculos fisicos antes de conferir o kit.")
    elif pode_ler_banco:
        kit = conferir("kit", script("atualizar_fundacao.py", "checar", "--raiz", raiz),
                       [raiz / "fundacao/__init__.py"], timeout,
                       "Revise atualizar_fundacao.py checar; atualização e conflitos seguem o fluxo C6.",
                       lambda d: d.get("pode_aplicar") is True and d.get("nada_a_fazer") is True
                       and isinstance(d.get("cadeia_de_eventos"), dict)
                       and d["cadeia_de_eventos"].get("cadeia_integra") is True)
    else:
        kit = passo("kit", "nao_rodado", nao_banco, acao_banco)
    passos = [kit,
              conferir("retomada", script("retomada.py", "validar", "--arquivo", raiz / "RETOMADA.md"),
                       [raiz / "RETOMADA.md"], timeout, "Confira e atualize a RETOMADA com as evidências atuais."),
              conferir("matriz", script("matriz.py", "validar", "--matriz", raiz / "registry/requisitos.csv"),
                       [raiz / "registry/requisitos.csv"], timeout, "Confira matriz.py validar e as evidências indicadas."),
              conferir("instrucoes", script("instrucoes_raiz.py", "conferir", "--raiz", raiz),
                       [raiz / "AGENTS.md", raiz / "CLAUDE.md"], timeout,
                       "Confira instrucoes_raiz.py conferir; gere as instruções pelo fluxo autorizado.")]
    perfil = Path(perfil) if perfil is not None else Path.home()  # inventário gravável não escolhe outro perfil
    perfil_args = ["--perfil", perfil]
    if estado_caminho(perfil, pasta=True) != "presente" or RETOMADA.pasta_recusada(perfil / "rotina.json"):
        host = passo("host", "nao_rodado", "perfil indisponível ou recusado", "Informe o perfil correto com --perfil.")
    elif not host_seguro(raiz, perfil):
        host = passo("host", "falhou", "leitura transitiva do inventario recusada",
                     "Confira as fontes fixas do host e os caminhos dos scripts antes de refazer o inventario.")
    else:
        host = conferir("host", script("inventariar_host.py", "verificar", "--inventario",
                                      raiz / "registry/inventario-host.json", "--raiz", raiz, *perfil_args),
                        [raiz / "registry/inventario-host.json"], timeout,
                        "Confira inventariar_host.py verificar; regrave o inventário só depois de revisar as diferenças.")
    passos.append(host)
    if pode_ler_banco:
        cadeia = conferir("cadeia", CONFERIDO.python_isolado(KIT, CONFERIDO.CADEIA, raiz), [], timeout,
                          "Investigue a cadeia de eventos antes de operar; não a reinicie.",
                          lambda d: d.get("cadeia_integra") is True)
    else:
        cadeia = passo("cadeia", "nao_rodado", nao_banco, acao_banco)
    passos.append(cadeia)
    acao_backup = "Informe --completo --backup com a última cópia e --sha256-manifesto guardado fora dela."
    if not pode_ler_banco or backup is None or not re.fullmatch(r"[0-9a-fA-F]{64}", sha256_manifesto or ""):
        copia = passo("backup", "nao_rodado", "leitura estável, cópia ou âncora externa indisponível", acao_backup)
    elif estado_caminho(backup, pasta=True) != "presente":
        copia = passo("backup", "nao_rodado", "caminho da cópia indisponível ou recusado", acao_backup)
    else:
        copia = conferir("backup", CONFERIDO.python_isolado(KIT, BACKUP, raiz, backup, sha256_manifesto),
                         [], timeout, "Confira a cópia, a âncora externa e a administração autenticada no lançador.",
                         lambda d: d.get("ok") is True and d.get("autorizado") is True and d.get("ancora_conferida") is True)
    passos.append(copia)
    return {"schema_version": ESQUEMA, "modo": "completo" if completo else "rapido",
            "pronto_para_seguir": all(p["estado"] == "ok" for p in passos), "passos": passos,
            "limites": ["Validações estruturais não aprovam conteúdo ou evidências.",
                        "Backup indicado pelo operador; não descobre automaticamente o mais recente.",
                        "Suíte não oferecida; banco WAL exige cópia estável fora de WAL."]}


def conferir_saida(raiz: Path, saida: Path) -> tuple[Path, str]:
    if ".." in Path(raiz).parts or ".." in Path(saida).parts:
        raise ValueError("saida recusada")
    raiz, saida = Path(os.path.abspath(raiz)), Path(os.path.abspath(saida))
    try:
        partes = saida.relative_to(raiz).parts
    except ValueError:
        raise ValueError("saída recusada") from None
    projeto = os.environ.get("FUNDACAO_PROJECT", "")
    projeto_valido = bool(re.fullmatch(r"[a-z0-9][a-z0-9_-]{0,63}", projeto))
    permitido = (len(partes) >= 2 and partes[0] == "evidence" or
                 len(partes) >= 4 and projeto_valido and partes[:2] == ("projects", projeto)
                 and partes[2] in ("outputs", "evidence"))
    if (not permitido or saida.suffix.lower() != ".json" or RETOMADA.protegido(raiz, partes)
            or RETOMADA.pasta_recusada(raiz / "rotina.json")
            or estado_caminho(raiz, pasta=True) != "presente" or estado_caminho(saida) != "ausente"):
        raise ValueError("saída recusada")
    return saida, "/".join(partes[:-1])


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__, formatter_class=argparse.RawDescriptionHelpFormatter)
    ap.add_argument("--raiz", type=Path, required=True)
    ap.add_argument("--completo", action="store_true")
    ap.add_argument("--perfil", type=Path)
    ap.add_argument("--backup", type=Path, help="última cópia indicada pelo operador, sem descoberta automática")
    ap.add_argument("--sha256-manifesto", help="hash externo devolvido ao criar a cópia")
    ap.add_argument("--timeout", type=int, default=60, help="segundos por subprocesso (1 a 600)")
    ap.add_argument("--saida", type=Path, help="novo .json em evidence/ ou no projeto autenticado; nunca sobrescreve")
    args = ap.parse_args(argv)
    if not 1 <= args.timeout <= 600:
        ap.error("--timeout deve estar entre 1 e 600")
    try:
        if args.saida:
            conferir_saida(args.raiz, args.saida)  # antes das conferências: recusa destino desviado sem outros efeitos
        res = verificar(args.raiz, completo=args.completo, perfil=args.perfil, backup=args.backup,
                        sha256_manifesto=args.sha256_manifesto, timeout=args.timeout)
        if args.saida:
            destino, rel = conferir_saida(args.raiz, args.saida)
            GRAVACAO.pasta_sem_ligacao(args.raiz, rel)
            conferir_saida(args.raiz, args.saida)
            GRAVACAO.criar(destino, (json.dumps(res, ensure_ascii=False, indent=2) + "\n").encode("utf-8"))
    except (OSError, ValueError, RuntimeError):
        res = {"schema_version": ESQUEMA, "pronto_para_seguir": False, "passos": [],
               "erro": "caminho ou saída recusado; relatório não gravado; nenhum arquivo foi sobrescrito"}
    print(json.dumps(res, ensure_ascii=False, indent=2))
    return 0 if res["pronto_para_seguir"] else 1


if __name__ == "__main__":
    for stream in (sys.stdout, sys.stderr):
        try:
            stream.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
