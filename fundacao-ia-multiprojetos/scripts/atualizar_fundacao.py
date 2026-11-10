#!/usr/bin/env python3
"""Atualiza uma fundação para o kit desta skill num só comando, com ensaio antes e registro depois (fluxo C6).

  checar   --raiz R                    só lê: versões, o que muda arquivo a arquivo, identidade e cadeia de eventos
  aplicar  --raiz R --backups PASTA    ensaia numa cópia e só então atualiza a raiz
  desfazer --registro ARQ.json         devolve o código anterior, se o banco não mudou de esquema

`aplicar`, em sequência, parando no primeiro problema (nada é escrito na raiz antes do passo 4):
  1. `checar`: recusa se algum arquivo de código foi ALTERADO LOCALMENTE desde a instalação (difere do kit
     novo e do hash registrado em registry/kit_install.json) — isso é decisão C6 à parte —, se houver nas áreas de
     código, ou no primeiro nível da raiz (módulo, pacote ou `.pth` que o uso normal importaria; segunda passada da
     revisão de segurança da 1.7.7, R177B-B-06; e a pasta `mcp/` mesmo sem `__init__`, que sem o SDK do MCP vira
     pacote de namespace; terceira passada, R177C-B-03), executável que nenhum dos dois conhece ou ligação, ou se
     faltar a identidade da administração ou a cadeia de eventos não conferir. O `checar` não executa nada da raiz: a
     cadeia é conferida pelo kit da skill, com o banco aberto somente leitura (auditoria Codex Security da 1.7.6, #8).
     Também recusa ligação ou vínculo físico onde a atualização grava (GRAVADOS; revisão de segurança da 1.7.7,
     R177-ATU-03);
  2. backup ANTES (código atual da raiz, rodado de uma cópia conferida por hash): `backup criar` + `backup
     verificar`, em PASTA/antes-kit-<versão>-<data>;
  3. ensaio: restaura essa cópia numa pasta temporária, aplica o kit novo (`instalar_kit.py --atualizar`), roda
     `init`, `eventos verificar` e a suíte de conformidade NELA. A suíte roda de cópias conferidas por hash (a do
     código da raiz antes, a da cópia atualizada depois), com os módulos enumerados da lista, nunca da árvore viva.
     Falha de teste que já acontecia antes da atualização é relatada, mas não bloqueia; falha nova (regressão)
     bloqueia;
  4. promoção na raiz: onde a atualização grava, conferido de novo (ligação ou vínculo físico criado durante o ensaio
     recusa; revisão de segurança da 1.7.7, segunda passada, R177B-B-05); `instalar_kit.py --atualizar` (guarda os
     arquivos substituídos), o `__pycache__` das áreas de código e do primeiro nível apagado sem seguir ligação
     (bytecode não conferido; R177-ATU-02, R177B-B-06), `init` e `eventos verificar`; depois, as instruções da raiz
     (AGENTS.md e CLAUDE.md, `instrucoes_raiz.py gerar`), sem bloquear. O instalador que para depois de gravar (saída
     sem `nada_escrito`) deixa a promoção interrompida: o `__pycache__` sai do mesmo jeito, e o registro é gravado e
     ancorado antes de parar, para o `desfazer` (terceira passada, R177C-B-04); a promoção que falhou e o próprio
     instalador desfez (código 5, `desfeito`, composição `nao_alterada`) conta como `nada_escrito`: para sem tocar a
     raiz (quarta passada, R177D-5);
  5. backup DEPOIS (código novo, com âncora) + `backup verificar`;
  6. registro em <raiz>/evidence/atualizacoes/, com a âncora, e resumo em linguagem simples; só então, sem bloquear
     e com tempo limite, o inventário do host (R177-VAL-04).
Do passo 4 em diante, o código que roda é o do kit da skill (o mesmo que acabou de ser conferido na raiz).
Com o kit da raiz já igual ao da skill, o `aplicar` só regenera as instruções da raiz se o texto que a skill geraria
for outro (skill nova com o mesmo kit), guardando as anteriores e com registro; sem diferença, não escreve nada.
`desfazer` devolve os arquivos substituídos (registry/kit_backup/...) e apaga os criados pela atualização (as
instruções da raiz também, salvo se editadas depois), só se o
`user_version` do banco não mudou; se mudou, a volta é restaurar a cópia ANTES numa pasta nova (C9). O registro só
vale com o SHA-256 que o `aplicar` anotou em registry/atualizacoes.jsonl, e cada caminho dele fica nas áreas de
código do kit (auditoria Codex Security da 1.7.6, #10). E só devolve se o código ainda é o que a atualização deixou
(`sha256_novo`): repetido, ou depois de outra atualização, recusa (revisão de segurança da 1.7.7). O registro, a
âncora e o `desfazer` moram em `registro_atualizacao.py`; a gravação sem seguir ligação, em `gravacao_segura.py`.
Os comandos que a saída sugere ao titular (voltar o código ou as instruções, conferir o host, gerar as instruções)
trazem o caminho completo do script e os caminhos entre aspas duplas: colados no PowerShell ou no bash, de qualquer
pasta, rodam como estão; caminho que não pode ir entre aspas com segurança não vira comando (`comando`).

Identidade: FUNDACAO_PRINCIPAL vem do lançador (administração da fundação); este script não a define.
Saída em JSON; códigos: 0 ok · 1 recusado ou falhou (com `etapa` e `motivo`) · 2 uso incorreto.

Aplicar na fundação viva com dados reais (1.7.10; a raiz passou a ter cerca de 130 mil arquivos e 6,2 GB):
- antes de começar e antes da restauração do ensaio, nenhuma distribuição do WSL pode estar rodando (o banco não é
  aberto pelos dois lados); raiz de ensaio na pasta temporária do sistema (os testes) só registra;
- durante o `aplicar`, a trava de manutenção `state/manutencao.json` ({"motivo", "pid", "host", "desde"}, o formato do
  `core/manutencao.py` do kit novo, gravado direto porque o kit da raiz pode ser o anterior) faz o lançador do Ubuntu
  não abrir; ela sai no fim, também na falha; trava que já existe recusa;
- o ensaio nasce numa pasta nova dentro de `--pasta-ensaio` (padrão: a pasta das cópias, `--backups`), no disco das
  cópias, e não na pasta temporária do C:; dentro da raiz, recusa — e a pasta das cópias também, com ou sem
  `--pasta-ensaio` (revisão de segurança da 1.7.10, KIT-F7); a política de backup que o kit novo recusaria (KIT-F2)
  recusa no `checar`, antes de qualquer cópia;
- a limpeza do ensaio e do código conferido é contada (arquivos, pastas, ligações e bytes que sobraram, com os erros) e
  vai para o registro; no Windows, a marca somente leitura sai só dentro da pasta criada pelo próprio atualizador; a
  ligação sai como ligação, sem tocar o destino; antes, `shutil.rmtree(..., ignore_errors=True)` escondia a sobra;
- cópia cifrada (1.7.11, lote 5 do desenho DESENHO-COPIA-CIFRADA-1.7.11): com a chave pública da cópia instalada e protegida
  na âncora (core/politica_cifra.py, decidida pelo kit da skill), as cópias ANTES e DEPOIS saem CIFRADAS no disco das
  cópias. A ANTES nasce em claro num preparo local (disco interno, fora da raiz e do disco das cópias) pelo código da
  raiz, é verificada, e o kit da skill a cifra para `--backups`; o ensaio restaura DESSE preparo local, que é apagado
  (limpeza contada) logo depois; a DEPOIS é o `criar` cifrado do kit novo (core/copia_cifrada.py). O padrão de
  `--pasta-ensaio` passa a ser local: com a chave instalada, um ensaio no disco das cópias deixaria uma raiz restaurada em
  claro lá, e recusa. `--sem-cifra "<motivo>"` mantém as cópias em claro, com o motivo no registro. Chave instalada e
  não protegida recusa no `checar`, antes de qualquer cópia. Raiz na pasta temporária (os testes) fica em claro;
- se a cópia ANTES falha na promoção (código 2 com E_ARQUIVO ou E_PROMOCAO, ou WinError 5 — o kit da raiz pode não
  tentar de novo), a sobra do preparo é contada (sem apagar: ela tem os dados da fundação), o destino é conferido
  ausente e a cópia é tentada de novo UMA vez, com rótulo novo; as duas tentativas vão para o registro;
- o tempo é estimado pelo número de arquivos do que a cópia leva (medido em 31/10/2026: cerca de 17 min para criar e
  12 para verificar uma cópia de 130 mil arquivos, 27 para restaurar) e mostrado no início (stderr); `--prazo` (por
  subprocesso longo) tem padrão derivado da estimativa.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import re
import shutil
import socket
import stat
import subprocess
import sys
import tempfile
from pathlib import Path

AQUI = Path(__file__).resolve().parent
if str(AQUI) not in sys.path:  # carregado por caminho (testes): o módulo vizinho também tem de ser achado
    sys.path.append(str(AQUI))
import codigo_conferido as conferido  # noqa: E402  (inventário, cópia conferida e execução isolada; #8)
import gravacao_segura as gravacao  # noqa: E402  (gravação sem seguir ligação nem vínculo físico; R177-ATU-03)
from registro_atualizacao import (GRAVADOS, Parada, agora, caminho_do_registro_valido, com_ligacao,  # noqa: E402
                                  desfazer, desvio, gravar, sha, user_version, versao_do_kit)  # registro e volta

KIT = AQUI.parent / "assets" / "fundacao-kit"
INSTALAR_KIT = AQUI / "instalar_kit.py"
INVENTARIAR_HOST = AQUI / "inventariar_host.py"
INVENTARIO_HOST = Path("registry") / "inventario-host.json"  # R54: skills, plugins, MCP e hooks do host
INSTRUCOES_RAIZ = AQUI / "instrucoes_raiz.py"  # AGENTS.md e CLAUDE.md gerados na raiz (proposta 1)
CONFIGURACAO = "registry"
IGNORAR = {"__pycache__", ".pytest_cache"}
VARIAVEL_IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"
TEMPO = 3600
TEMPO_INVENTARIO = 120  # inventário do host: informativo, roda depois do registro (R177-VAL-04)
MOTIVO_CLARO_LOCAL = "atualizador: cópia em claro no preparo local, cifrada logo em seguida"
# Programas do kit da skill (python_isolado; sem banco): a decisão de cifrar e a cópia cifrada (core/politica_cifra.py,
# core/backup_cifrado.py e core/copia_cifrada.py). Os argumentos vêm só deste script.
DECIDIR = """import json
from fundacao.core import politica_cifra
from fundacao.core.contracts import FundacaoError
try:
    d = politica_cifra.decidir(sys.argv[1] or None)
except FundacaoError as exc:
    print(json.dumps({"recusa": str(exc)}))
    sys.exit(1)
print(json.dumps({"modo": d["modo"], "chave": str(d["chave"]) if d.get("chave") else None, "sem_cifra": d.get("sem_cifra"),
                  "preparo_base": str(politica_cifra.pasta_de_dados() / "FundacaoIA" / "preparo-copias")}))
"""
CIFRAR = """import json
from pathlib import Path
from fundacao.core import backup_cifrado, copia_cifrada, manutencao
from fundacao.core.contracts import FundacaoError
modo, raiz, destino, rotulo, chave, extra = (sys.argv[1], Path(sys.argv[2]), Path(sys.argv[3]), sys.argv[4],
                                             Path(sys.argv[5]), Path(sys.argv[6]))
try:
    if modo == "converter":
        res = backup_cifrado.cifrar_copia(extra, destino, chave, label=rotulo, livro=raiz / "state" / "copias.jsonl")
    else:
        res = copia_cifrada.criar_cifrada(raiz, destino, rotulo, chave, preparo_local=extra)
    ver = backup_cifrado.verificar_cifrada(destino, sha256_manifesto=res["sha256_manifesto"],
                                           destinatario_esperado=res["destinatario"]["principal"])
    if not ver["ok"]:
        raise FundacaoError("a cópia cifrada não passou na conferência sem senha")
    manutencao.registrar_copia(raiz, rotulo=rotulo, criada_em=res["created_at"], destino=str(destino), cifrada=True)
except Exception as exc:
    print(json.dumps({"erro": {"tipo": type(exc).__name__, "mensagem": str(exc)[:600]}}))
    sys.exit(1)
print(json.dumps({"sha256_manifesto": res["sha256_manifesto"], "sha256_manifesto_interno": res["sha256_manifesto_interno"],
                  "destinatario": res["destinatario"]["principal"], "partes": len(res["partes"]),
                  "arquivos": len(res["files"]) if "files" in res else res["arquivos"], "created_at": res["created_at"]}))
"""
AREAS_DE_CODIGO = conferido.AREAS_DE_CODIGO  # fundacao/, templates/, tests/
RETIRADAS = "tests/testes_retirados.json"  # no kit novo: ID do teste retirado de propósito -> versão e motivo
NAO_LIBERADA = Path("state") / "restauracao-nao-liberada.json"  # marca do kit (backup.MARCA_NAO_LIBERADA)
# Dentro de aspas duplas, o PowerShell interpreta `$`, a crase e as aspas (também as tipográficas); o bash, `$`, a
# crase, as aspas, `!` (histórico) e a barra invertida antes delas ou dobrada (terceira passada).
NAO_CITAVEIS = frozenset('"$`!' + chr(0x201C) + chr(0x201D) + chr(0x201E))  # aspas, $, crase, ! e as tipográficas
TRAVA = Path("state") / "manutencao.json"  # trava de manutenção (contrato da 1.7.10; references/atualizacao-1.7.10.md)
# Medido em 31/10/2026 na raiz com os projetos migrados (cerca de 130 mil arquivos): 17,5 min para criar a cópia, 12
# para verificar e 27 para restaurar. As suítes do ensaio não foram medidas.
MEDIDO = {"arquivos": 130_000, "criar": 17.5 * 60, "verificar": 12 * 60, "restaurar": 27 * 60}
# O que a cópia do kit leva e deixa fora (fundacao/core/backup.py: FILE_DIRS e as exclusões;
# fundacao/core/regras_da_copia.py: REGISTROS_PADRAO).
NA_COPIA = ("fundacao", "registry", "templates", "projects", "AGENTS.md", "CLAUDE.md")
REGISTROS_NA_COPIA = ("docs", "evidence", "ferramentas", "tests", "RETOMADA.md")
FORA_DA_COPIA = {"__pycache__", ".venv", "node_modules", ".git", ".cache"}  # igual ao EXCLUDE_PARTS do kit (há teste)
# Áreas da 1.7.10 que a política de backup da raiz passa a levar (crítica do desenho, §5.1): `em-uso/`, de onde rodam as
# tarefas fora da sessão, e `.claude/projetos/`, a área do titular por projeto; depois do corte, são a única cópia.
POLITICA_1710 = ("em-uso", ".claude/projetos")
FALHA_DE_PROMOCAO = ("E_ARQUIVO", "E_PROMOCAO")  # código 2 do `backup criar` que vale uma nova tentativa
MAX_ERROS_DA_LIMPEZA = 20


def citar(caminho) -> str:
    """O caminho entre aspas duplas, que o PowerShell e o bash leem como um argumento só, com espaços e acentos.
    Recusa (ValueError) o que algum dos dois interpretaria dentro das aspas (NAO_CITAVEIS e caractere de controle), a
    barra invertida dobrada (o bash a reduz a uma) e a final (no bash ela escaparia a aspa de fechamento; no PowerShell
    5.1, a passagem para o programa também)."""
    texto = str(caminho)
    if any(c in NAO_CITAVEIS or c < " " for c in texto) or "\\\\" in texto or texto.endswith("\\"):
        raise ValueError("caminho com caractere que o PowerShell ou o bash interpretaria entre aspas: " + texto[:200])
    return '"' + texto + '"'


def comando(script: Path, *argumentos) -> str:
    """Comando pronto para o titular colar no PowerShell ou no bash, de qualquer pasta: `python`, o caminho completo do
    script e cada caminho (`Path`) entre aspas duplas; texto passa como está. Caminho que não pode ir entre aspas com
    segurança não vira comando: volta o aviso, e o caminho fica na saída para ser citado à mão (terceira passada)."""
    try:
        partes = ["python", citar(Path(script).resolve())]
        return " ".join(partes + [citar(a) if isinstance(a, Path) else str(a) for a in argumentos])
    except ValueError as exc:
        return "(comando não montado: " + str(exc) + "; cite-o à mão)"


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
    except (OSError, ValueError, RecursionError):  # ilegível ou trocado (R177C-B-04): o `checar` recusa o que difere
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


def fundacao(codigo: Path, raiz: Path, *args: str, prazo: int = TEMPO) -> tuple:
    """CLI do kit sobre a `raiz`, rodando o código de `codigo`: o kit da skill ou uma cópia conferida do código da
    raiz, nunca a árvore viva dela (auditoria Codex Security da 1.7.6, #8)."""
    return rodar(conferido.python_isolado(codigo, conferido.CLI, "--raiz", raiz, *args), cwd=raiz, timeout=prazo)


# --------------------------------------------------------------------- fundação viva com dados reais (1.7.10)
def wsl_em_uso(nome_sistema: str = os.name) -> list:
    """Distribuições do WSL em execução (fora o docker-desktop), como no liberar.py: o banco da fundação não pode ser
    aberto pelo Windows e pelo WSL ao mesmo tempo (RETOMADA da fundação). Só no Windows: dentro do Ubuntu, o wsl.exe
    do Windows aparece pela interop e listaria a própria distribuição, derrubando a sessão (1.7.10)."""
    if nome_sistema != "nt" or shutil.which("wsl.exe") is None:
        return []
    try:
        r = subprocess.run(["wsl.exe", "-l", "--running", "-q"], capture_output=True, timeout=60)
    except (OSError, subprocess.TimeoutExpired):
        return ["(não foi possível consultar o WSL)"]
    texto = r.stdout.decode("utf-16-le", "replace") if b"\x00" in r.stdout else r.stdout.decode("utf-8", "replace")
    return [n.strip() for n in texto.replace("\x00", "").splitlines() if n.strip() and "docker" not in n.lower()]


def em_pasta_temporaria(caminho: Path) -> bool:
    """Raiz de ensaio na pasta temporária do sistema (a dos testes): nenhuma sessão do Ubuntu abre o banco dela."""
    try:
        return Path(os.path.realpath(caminho)).is_relative_to(Path(os.path.realpath(tempfile.gettempdir())))
    except (OSError, ValueError):
        return False


def sem_wsl(etapa: str, raiz: Path) -> dict:
    em_uso = wsl_em_uso()
    if em_uso and not em_pasta_temporaria(raiz):
        raise Parada(etapa, "WSL em execução (" + ", ".join(em_uso) + "): feche-o (wsl --shutdown) e repita; o banco "
                     "da fundação não pode ser aberto pelos dois lados, e nada foi alterado nesta etapa",
                     wsl_em_uso=em_uso)
    return {"em_uso": em_uso, "conferido_em": agora(), **({"so_registrado": "raiz de ensaio na pasta temporária"}
                                                           if em_uso else {})}


def travar(raiz: Path, motivo: str) -> dict:
    """Grava a trava de manutenção (arquivo novo, sem seguir ligação). Trava que já existe recusa: outra manutenção em
    andamento ou uma trava esquecida, que o titular confere e apaga."""
    dados = {"motivo": motivo, "pid": os.getpid(), "host": socket.gethostname(), "desde": agora()}
    bruto = (json.dumps(dados, ensure_ascii=False, indent=1) + "\n").encode("utf-8")
    if gravacao.com_ligacao(raiz, TRAVA.as_posix()):
        raise Parada("trava", "state/ ou a trava de manutenção é ligação (link simbólico ou junção): nada foi alterado")
    try:
        gravacao.criar(raiz / TRAVA, bruto)
    except FileExistsError:
        raise Parada("trava", "já há uma trava de manutenção em " + TRAVA.as_posix() + " (outra manutenção em andamento "
                     "ou uma trava esquecida): confira o pid e o host dela e, se não houver manutenção, apague-a e "
                     "repita; nada foi alterado") from None
    except OSError as exc:
        raise Parada("trava", "a trava de manutenção não foi gravada (" + type(exc).__name__ + "): nada foi alterado")
    return {"arquivo": TRAVA.as_posix(), "sha256": hashlib.sha256(bruto).hexdigest(), **dados}


def destravar(raiz: Path, trava: dict) -> dict:
    """Tira a trava que este `aplicar` gravou — a mesma, pelo hash, sem seguir ligação —, também na falha. A trava
    trocada no meio do caminho fica, com o motivo."""
    alvo = raiz / TRAVA
    try:
        st = os.lstat(alvo)
        if gravacao.e_ligacao(st) or not stat.S_ISREG(st.st_mode) or st.st_nlink != 1:
            return {"removida": False, "motivo": "a trava virou ligação, pasta ou vínculo físico: confira"}
        if hashlib.sha256(alvo.read_bytes()).hexdigest() != trava["sha256"]:
            return {"removida": False, "motivo": "a trava foi trocada durante o aplicar: confira antes de apagar"}
        os.unlink(alvo)
    except FileNotFoundError:
        return {"removida": False, "motivo": "a trava já não existia"}
    except OSError as exc:
        return {"removida": False, "motivo": "a trava não saiu (" + type(exc).__name__ + "): apague " + str(alvo)}
    return {"removida": True}


def _rel_incluida_segura(rel, raiz: Path | None = None) -> bool:
    """O mesmo filtro do kit (core/regras_da_copia.py, motivo_da_politica; revisão de segurança da 1.7.10, KIT-F2):
    caminho relativo não vazio, sem unidade, raiz, `:` nem `..`, que não é a própria raiz (`.`); a primeira parte, sem
    caixa e sem ponto ou espaço no fim (`State`, `state.`, `state `), não é `state` nem `.git`; com `raiz`, o caminho
    resolvido fica dentro dela e fora de `<raiz>/state` e `<raiz>/.git` (a ligação do fim a cópia não segue: passa).
    Há teste de igualdade com o kit."""
    if not isinstance(rel, str) or not rel.strip() or ":" in rel or "\0" in rel:
        return False
    p, partes = Path(rel), [x for x in rel.replace("\\", "/").split("/") if x not in ("", ".")]
    if (p.is_absolute() or p.drive or p.root or not partes or any(not x.rstrip(". ") for x in partes)
            or partes[0].rstrip(". ").casefold() in ("state", ".git")):
        return False
    if raiz is None:
        return True
    try:
        if gravacao.e_ligacao(os.lstat(raiz / rel)):
            return True  # a cópia do kit não segue a ligação do fim: nada de lá entra (e contar_arquivos a pula)
    except OSError:
        pass
    real, alvo = Path(os.path.realpath(raiz)), Path(os.path.realpath(raiz / rel))
    protegidas = [Path(os.path.realpath(raiz / nome)) for nome in ("state", ".git")]
    return alvo != real and alvo.is_relative_to(real) and not any(alvo == x or alvo.is_relative_to(x)
                                                                   for x in protegidas)


def _incluidos(raiz: Path) -> list:
    """O que a cópia do kit leva além do kit e do banco: a lista `incluir` de registry/backup_policy.json (com o mesmo
    filtro do kit: `_rel_incluida_segura`) ou o padrão."""
    try:
        incluir = json.loads((raiz / "registry" / "backup_policy.json").read_text(encoding="utf-8")).get("incluir")
    except (OSError, ValueError, AttributeError):
        incluir = None
    return ([x for x in incluir if _rel_incluida_segura(x, raiz)] if isinstance(incluir, list)
            else list(REGISTROS_NA_COPIA))


def _politica_recusada(raiz: Path) -> str | None:
    """O que o kit novo recusaria em registry/backup_policy.json — já com as áreas que `politica_de_backup` acrescenta
    antes da cópia DEPOIS —, como o `registros_incluidos` dele: ilegível, fora do formato ou com caminho que
    `_rel_incluida_segura` recusa. Revisão de segurança da 1.7.10 (KIT-F2, correções da revisão 1): a cópia ANTES e o
    ensaio rodam com o kit da raiz, que pode aceitar `state ` ou `.GIT`; a recusa só viria na cópia DEPOIS, com a raiz
    já promovida. O `checar` a mostra antes de qualquer cópia; None se não há o que recusar."""
    arq = raiz / "registry" / "backup_policy.json"
    try:
        dados = json.loads(arq.read_text(encoding="utf-8")) if arq.is_file() else {"incluir": list(REGISTROS_NA_COPIA)}
    except (OSError, ValueError) as exc:
        return "registry/backup_policy.json ilegível (" + type(exc).__name__ + "): corrija o JSON"
    incluir = dados.get("incluir") if isinstance(dados, dict) else None
    if not isinstance(incluir, list) or not all(isinstance(x, str) and x.strip() for x in incluir):
        return "registry/backup_policy.json fora do formato {\"incluir\": [caminhos relativos]}: corrija a lista"
    ruins = [x for x in dict.fromkeys([*incluir, *POLITICA_1710]) if not _rel_incluida_segura(x, raiz)]
    if not ruins:
        return None
    return ("a política de backup (registry/backup_policy.json) tem caminho que a cópia do kit novo recusa ("
            + ", ".join(repr(x)[:80] for x in ruins[:5]) + "): só caminhos relativos dentro da raiz, fora de state/ e "
            ".git em qualquer grafia (caixa, ponto ou espaço no fim) e sem ligação no meio que leve a eles ou para fora; "
            "tire ou corrija a entrada e repita")


def politica_de_backup(raiz: Path) -> dict:
    """Acrescenta POLITICA_1710 à lista `incluir` de registry/backup_policy.json (a política é da raiz, não vem do kit);
    sem o arquivo, ele nasce com a lista padrão do kit mais essas. Só acrescenta, e o `desfazer` não a volta: a lista
    maior também vale para o kit anterior. Política ilegível, fora do formato ou com ligação no caminho fica como está,
    com o motivo (o resumo avisa)."""
    rel = "registry/backup_policy.json"
    arq = raiz / rel
    try:
        if gravacao.com_ligacao(raiz, rel):
            return {"mudou": False, "erro": "registry/ ou a política é ligação: nada foi gravado"}
        atual = json.loads(arq.read_text(encoding="utf-8")) if arq.exists() else None
    except (OSError, ValueError) as exc:
        return {"mudou": False, "erro": "política ilegível (" + type(exc).__name__ + ")"}
    if atual is not None and not (isinstance(atual, dict) and isinstance(atual.get("incluir"), list)):
        return {"mudou": False, "erro": "política fora do formato {\"incluir\": [...]}"}
    dados = atual or {"schema_version": "fundacao.backup_policy/1", "incluir": list(REGISTROS_NA_COPIA)}
    faltam = [x for x in POLITICA_1710 if x not in dados["incluir"]]
    if not faltam:
        return {"mudou": False}
    texto = (json.dumps({**dados, "incluir": [*dados["incluir"], *faltam]}, ensure_ascii=False, indent=2)
             + "\n").encode("utf-8")
    try:
        gravacao.publicar(arq, texto)
    except OSError as exc:
        return {"mudou": False, "erro": "a política não foi gravada: " + str(exc)[:200]}
    return {"mudou": True, "criada": atual is None, "acrescentados": faltam,
            "sha256": hashlib.sha256(texto).hexdigest()}


def _resumo_politica(politica: dict) -> list:
    if politica.get("mudou"):
        return ["A cópia de segurança passa a levar também " + ", ".join(politica["acrescentados"])
                + " (registry/backup_policy.json" + (", criado" if politica.get("criada") else "") + ")."]
    if politica.get("erro"):
        return ["Atenção: a política de backup não foi ampliada (" + politica["erro"] + "); acrescente à mão em "
                "registry/backup_policy.json, na lista incluir: " + ", ".join(POLITICA_1710) + "."]
    return []


def contar_arquivos(raiz: Path) -> int:
    """Arquivos que a cópia levaria (as pastas do kit e os registros incluídos, sem as pastas e os nomes que ela deixa
    fora), contados sem seguir ligação e sem ler conteúdo."""
    total, pilha = 0, [raiz / rel for rel in (*NA_COPIA, *_incluidos(raiz))]
    while pilha:
        atual = pilha.pop()
        try:
            st = os.lstat(atual)
        except OSError:
            continue
        if gravacao.e_ligacao(st):
            continue
        if stat.S_ISREG(st.st_mode):
            total += atual.name not in (".env", "state.sqlite", "state.sqlite-wal", "state.sqlite-shm")
        elif stat.S_ISDIR(st.st_mode) and atual.name not in FORA_DA_COPIA:
            try:
                pilha += [Path(e.path) for e in os.scandir(atual)]
            except OSError:
                continue
    return total


def estimar(raiz: Path) -> dict:
    """Tempo das duas cópias e da restauração do ensaio pela proporção do número de arquivos com a medida de 31/10."""
    n = contar_arquivos(raiz)
    escala = n / MEDIDO["arquivos"]
    copia = (MEDIDO["criar"] + MEDIDO["verificar"]) * escala
    segundos = {"copia_antes": round(copia), "restauracao_do_ensaio": round(MEDIDO["restaurar"] * escala),
                "copia_depois": round(copia)}
    return {"arquivos": n, "segundos": segundos, "minutos": max(1, round(sum(segundos.values()) / 60)),
            "base": "medido em 31/10/2026: cerca de 17 min para criar e 12 para verificar uma cópia de 130 mil "
                    "arquivos e 27 para restaurar", "fora_da_estimativa": "as suítes de testes do ensaio (não medidas) "
                    "e a nova tentativa da cópia ANTES, se a promoção falhar"}


def _rotulo_do_erro(caminho: str, pasta: Path) -> str:
    """Caminho do item que sobrou na pasta do atualizador, sem expor nome de caso: as 3 primeiras partes e, se houver
    mais, um hash curto do resto. A cópia de ensaio tem a fundação inteira, inclusive projects/<p>/data/<documento>:
    `raiz/projects/<p>` localiza a área sem levar o nome do caso para as saídas."""
    try:
        rel = Path(os.path.relpath(caminho, pasta))
    except ValueError:
        return os.path.basename(caminho)[:200]
    partes = rel.parts
    if len(partes) <= 3:
        return rel.as_posix()[:200]
    resto = hashlib.sha256("/".join(partes[3:]).encode("utf-8", "replace")).hexdigest()[:8]
    return (Path(*partes[:3]).as_posix() + "/<" + resto + ">")[:200]


def limpar(pasta: Path) -> dict:
    """Apaga a pasta que o próprio atualizador criou (o ensaio ou o código conferido), de baixo para cima e sem seguir
    ligação: a ligação sai como ligação, e o destino dela não é tocado. No Windows, o item somente leitura dentro dela
    perde a marca e é tentado de novo — só dentro desta pasta. Conta o que saiu e o que sobrou (arquivos, pastas,
    ligações e bytes), com os primeiros erros; nada é escondido."""
    res = {"pasta": str(pasta), "apagados": 0, "erros": []}
    if not os.path.lexists(pasta):
        return {**res, "limpa": True, "sobra": {"arquivos": 0, "pastas": 0, "ligacoes": 0, "bytes": 0}}

    def remover(caminho: str, st: os.stat_result) -> None:
        eh_pasta = stat.S_ISDIR(st.st_mode) or bool(getattr(st, "st_file_attributes", 0) & 0x10)
        apagar = os.rmdir if eh_pasta and (os.name == "nt" or not stat.S_ISLNK(st.st_mode)) else os.unlink
        for tentativa in (1, 2):
            try:
                apagar(caminho)
                res["apagados"] += 1
                return
            except FileNotFoundError:
                return
            except PermissionError as exc:
                erro = exc
                if tentativa == 1 and os.name == "nt" and not gravacao.e_ligacao(st):
                    try:
                        os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)  # só a marca somente leitura do Windows
                        continue
                    except OSError:
                        pass
                break
            except OSError as exc:
                erro = exc
                break
        if len(res["erros"]) < MAX_ERROS_DA_LIMPEZA:
            res["erros"].append(type(erro).__name__ + ": " + _rotulo_do_erro(caminho, pasta))

    pastas, pilha = [], [str(pasta)]
    while pilha:
        atual = pilha.pop()
        try:
            st = os.lstat(atual)
        except OSError:
            continue
        if stat.S_ISDIR(st.st_mode) and not gravacao.e_ligacao(st):
            pastas.append((atual, st))
            try:
                pilha += [e.path for e in os.scandir(atual)]
            except OSError as exc:
                if len(res["erros"]) < MAX_ERROS_DA_LIMPEZA:
                    res["erros"].append(type(exc).__name__ + ": " + _rotulo_do_erro(atual, pasta))
        else:
            remover(atual, st)
    for atual, st in reversed(pastas):  # as de baixo antes das de cima
        remover(atual, st)
    res["sobra"] = sobra(Path(pasta))
    res["limpa"] = not os.path.lexists(pasta)
    return res


def sobra(pasta: Path) -> dict:
    """O que existe na pasta (arquivos, pastas, ligações e bytes), contado sem seguir ligação e sem ler conteúdo."""
    conta, pilha = {"arquivos": 0, "pastas": 0, "ligacoes": 0, "bytes": 0}, [str(pasta)]
    while pilha:
        atual = pilha.pop()
        try:
            st = os.lstat(atual)
        except OSError:
            continue
        if gravacao.e_ligacao(st):
            conta["ligacoes"] += 1
        elif stat.S_ISDIR(st.st_mode):
            conta["pastas"] += 1
            try:
                pilha += [e.path for e in os.scandir(atual)]
            except OSError:
                continue
        else:
            conta["arquivos"] += 1
            conta["bytes"] += st.st_size
    return conta


def sobra_do_preparo(destino: Path) -> dict:
    """O que sobrou das pastas de preparo do kit ao lado do destino (`.<rótulo>.preparo-<hex>`) depois de uma promoção
    que falhou: contado, não apagado — tem os dados da fundação; apagar é do titular, pela Lixeira."""
    pastas = sorted(destino.parent.glob("." + destino.name + ".preparo-*")) if destino.parent.is_dir() else []
    total = {"pastas_de_preparo": [p.name for p in pastas], "arquivos": 0, "pastas": 0, "ligacoes": 0, "bytes": 0}
    for p in pastas:
        for chave, valor in sobra(p).items():
            total[chave] += valor
    return total


def falha_de_promocao(codigo: int | None, erro: str) -> bool:
    """`backup criar` que falhou na promoção da cópia: código 2 com E_ARQUIVO ou E_PROMOCAO, ou o WinError 5."""
    if codigo != 2:
        return False
    try:
        dados = json.loads(erro.strip().splitlines()[-1]) if erro.strip() else {}
    except ValueError:
        dados = {}
    info = dados.get("error") if isinstance(dados, dict) else None  # `error` pode vir como texto ou lista
    tipo = info.get("code") if isinstance(info, dict) else None
    return tipo in FALHA_DE_PROMOCAO or "WinError 5" in erro


def suite(origem: Path, arquivos: dict, padrao: str, copia: Path, prazo: int = TEMPO) -> dict:
    """Suíte de conformidade numa cópia conferida de `origem` (só os `arquivos`, caminho -> sha256, e registry/, que
    os testes do kit copiam, sem as cópias do código guardadas pela promoção; R177-ATU-01), com os módulos enumerados
    da lista: total, ids das falhas e pulados."""
    try:
        conferido.preparar_copia(origem, arquivos, copia, dados=(CONFIGURACAO,))
    except (ValueError, OSError) as exc:
        raise Parada("ensaio", "a cópia dos testes não conferiu com a lista (" + str(exc)[:300] + "): algo mudou nas "
                     "áreas de código depois do `checar`; a raiz NÃO foi alterada")
    modulos = conferido.modulos_de_teste(arquivos, padrao)
    _code, dados, erro = rodar(conferido.python_isolado(copia, conferido.RUNNER, json.dumps(modulos)), cwd=copia,
                               timeout=prazo)
    if not isinstance(dados, dict):
        return {"total": 0, "falhas": ["suite-nao-rodou: " + erro[-300:]], "pulados": 0}
    return dados


def cadeia_de_eventos(raiz: Path) -> tuple:
    """(íntegra?, detalhes) da cadeia de eventos da raiz, recalculada pelo kit da skill com o banco aberto somente
    leitura: nada da raiz é importado e nada é escrito (#8). `eventos verificar` sai com código 0 mesmo com a cadeia
    quebrada; por isso vale `cadeia_integra`, não o código de saída."""
    code, dados, erro = rodar(conferido.python_isolado(KIT, conferido.CADEIA, raiz), cwd=KIT)
    if code != 0 or not isinstance(dados, dict):
        return False, {"erro": erro[-300:]}
    return dados.get("cadeia_integra") is True, dados


def rota_sigilosa(raiz: Path) -> dict:
    """Desvio da rota sigilosa da raiz julgado pelo kit NOVO (avaliação E11, F-05): sem aceite assinado do titular sobre
    a política exata, o kit o deixa sem efeito ao carregar (vale a rota distribuída). Não bloqueia: vai aos avisos."""
    codigo = ("import json\nfrom fundacao.core.politica_rotas import desvio_sem_decisao\n"
              "print(json.dumps({'desvio_sem_decisao': desvio_sem_decisao(sys.argv[1])}, ensure_ascii=False))")
    code, dados, erro = rodar(conferido.python_isolado(KIT, codigo, raiz), cwd=KIT)
    if code != 0 or not isinstance(dados, dict):
        return {"conferida": False, "erro": erro[-300:]}
    return {"conferida": True, **dados}


def checar(raiz: Path) -> dict:
    """Só lê. `pode_aplicar` e os `motivos` de recusa, com o que muda arquivo a arquivo; `avisos` não bloqueiam."""
    return _inspecionar(raiz)[0]


def _inspecionar(raiz: Path) -> tuple:
    """O `checar` e o inventário conferido das áreas de código (caminho -> sha256), que o `aplicar` usa para montar
    as cópias de onde o código antigo e os testes rodam. Nada da raiz é executado aqui (#8)."""
    raiz = Path(raiz).resolve()
    res = {"raiz": str(raiz), "kit_na_raiz": versao_do_kit(raiz), "kit_da_skill": versao_do_kit(KIT), "motivos": []}
    if res["kit_na_raiz"] is None or not (raiz / "state" / "state.sqlite").is_file():
        res["motivos"].append("a pasta não é uma fundação instalada pelo kit (fundacao/__init__.py e state/state.sqlite)")
        res["pode_aplicar"] = False
        return res, {}
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
    # Inventário exato das áreas de código (#8) e do primeiro nível da raiz (R177B-B-06): todo executável conferido pelo
    # hash do kit novo ou pelo registrado na instalação; o que nenhum dos dois conhece, o que difere do hash conhecido
    # e as ligações recusam.
    vistos = conferido.inventario(raiz, do_kit, conhecidos)
    mudancas["executaveis_a_mais"] = vistos["a_mais"]
    mudancas["bytecode_a_apagar"] = conferido.bytecode(raiz)  # não recusa: a promoção o apaga (R177-ATU-02, B-06)
    # Órfãos: o kit anterior instalou, o novo não tem mais (o instalar_kit.py os guarda no backup).
    mudancas["entradas_invalidas"] = sorted(rel for rel in conhecidos if not caminho_do_registro_valido(rel))
    candidatos = [rel for rel in conhecidos if rel not in do_kit and caminho_do_registro_valido(rel)
                  and rel.split("/", 1)[0] in AREAS_DE_CODIGO and (raiz / rel).is_file()]
    mudancas["alterados_localmente"] += [{"path": rel, "motivo": "o kit novo não tem mais e difere do hash registrado "
                                          "na instalação"} for rel in candidatos if rel in vistos["alterados"]]
    mudancas["por_ligacao"] = sorted(set(mudancas["por_ligacao"]) | set(vistos["ligacoes"])
                                     | {rel for rel in candidatos if com_ligacao(raiz, rel)})
    mudancas["retirar"] = sorted(rel for rel in candidatos if not com_ligacao(raiz, rel)
                                 and rel not in vistos["alterados"])
    res["mudancas"] = mudancas
    if mudancas["por_ligacao"]:
        res["motivos"].append("ligação ou junção nas áreas de código, no primeiro nível da raiz (com nome de módulo, "
                              "de pacote ou __pycache__) ou no caminho de um arquivo do kit ("
                              + ", ".join(mudancas["por_ligacao"][:5]) + "): a atualização escreveria, retiraria ou "
                              "executaria o que está do outro lado; investigue antes de atualizar")
    mudancas["gravacao_desviada"] = gravacao.desviados(raiz, GRAVADOS)
    if mudancas["gravacao_desviada"]:
        res["motivos"].append(desvio(mudancas["gravacao_desviada"], "a atualização"))
    if mudancas["entradas_invalidas"]:
        res["motivos"].append("registry/kit_install.json tem caminho que o instalador nunca grava (com `..`, absoluto "
                              "ou com barra invertida): o registro pode ter sido adulterado; investigue antes de "
                              "atualizar")
    if mudancas["alterados_localmente"]:
        res["motivos"].append("há arquivo de código alterado localmente desde a instalação: a atualização o "
                              "substituiria; revise-o antes (fluxo C6)")
    if mudancas["executaveis_a_mais"]:
        res["motivos"].append("há arquivo executável nas áreas de código (fundacao/, templates/, tests/) ou no "
                              "primeiro nível da raiz que nem o kit novo nem o registro da instalação conhecem ("
                              + ", ".join(mudancas["executaveis_a_mais"][:5]) + "): a atualização o executaria, ou o "
                              "uso normal (`python -m fundacao` na raiz, que a põe no caminho de importação) o "
                              "importaria no lugar do módulo de mesmo nome, também de dentro de uma pasta com o nome "
                              "de um pacote que o kit importa de fora da biblioteca padrão ("
                              + ", ".join(n + "/" for n in conferido.IMPORTADOS_DE_FORA) + ", mesmo sem __init__); "
                              "retire-o ou mova-o para fora dessas pastas (ou para uma subpasta que não seja pacote "
                              "nem tenha um desses nomes) e repita (fluxo C6)")
    if (raiz / NAO_LIBERADA).exists():
        res["motivos"].append("raiz de restauração não liberada (" + NAO_LIBERADA.as_posix() + "): não use; refaça a "
                              "restauração numa pasta nova (fluxo C9)")
    politica = _politica_recusada(raiz)  # KIT-F2: a cópia DEPOIS, com a raiz já promovida, a recusaria
    if politica:
        res["motivos"].append(politica)
    res["identidade"] = os.environ.get(VARIAVEL_IDENTIDADE) or None
    if not res["identidade"]:
        res["motivos"].append("identidade ausente: " + VARIAVEL_IDENTIDADE + " vem do lançador (administração da fundação)")
    integra, res["cadeia_de_eventos"] = cadeia_de_eventos(raiz)
    if not integra:
        res["motivos"].append("a cadeia de eventos da raiz não confere: investigue antes de atualizar")
    res["user_version"] = user_version(raiz)
    res["instrucoes_raiz"] = _plano_instrucoes(raiz)
    res["rota_sigilosa"] = rota_sigilosa(raiz)
    res["avisos"] = (["rota sigilosa: " + res["rota_sigilosa"]["desvio_sem_decisao"]]
                     if res["rota_sigilosa"].get("desvio_sem_decisao") else [])
    res["nada_a_fazer"] = not (mudancas["copiar"] or mudancas["atualizar"] or mudancas["alterados_localmente"]
                               or mudancas["retirar"])
    res["pode_aplicar"] = not res["motivos"]
    return res, vistos["conferidos"]


def _codigo_conferido(raiz: Path, conferidos: dict, destino: Path) -> Path:
    """Cópia conferida do pacote `fundacao/` da raiz (o código ANTES), de onde rodam o backup ANTES e a restauração do
    ensaio: o que roda é exatamente o que o `checar` conferiu, mesmo que a raiz mude depois (#8)."""
    try:
        conferido.preparar_copia(raiz, {rel: h for rel, h in conferidos.items() if rel.startswith("fundacao/")},
                                 destino, areas=("fundacao",))
    except (ValueError, OSError) as exc:
        raise Parada("backup", "o código da raiz mudou depois do `checar` (" + str(exc)[:300] + "): nada foi "
                     "executado nem alterado; confira e repita")
    return destino


def decisao_da_cifra(raiz: Path, sem_cifra: str | None = None) -> dict:
    """Se as cópias saem cifradas: {"modo": "cifrada" | "claro", "chave", "preparo_base", "sem_cifra"}, decidido pelo kit
    da skill (a chave pública na âncora protegida, core/politica_cifra.py). Chave instalada e não protegida recusa (sem
    cópia nenhuma, nem em claro). Raiz na pasta temporária (os testes) fica em claro, como o WSL em `sem_wsl`."""
    if em_pasta_temporaria(raiz):
        return {"modo": "claro", "motivo": "raiz de ensaio na pasta temporária"}
    code, dados, erro = rodar(conferido.python_isolado(KIT, DECIDIR, sem_cifra or ""), cwd=raiz, timeout=300)
    if isinstance(dados, dict) and dados.get("recusa"):
        raise Parada("checar", str(dados["recusa"]) + "; nada foi alterado")
    if code != 0 or not isinstance(dados, dict) or dados.get("modo") not in ("cifrada", "claro"):
        raise Parada("checar", "não foi possível decidir se as cópias saem cifradas; nada foi alterado", erro=erro,
                     saida=dados)
    return dados


def _kit_cifra(raiz: Path, modo: str, destino: Path, rotulo: str, cifra: dict, extra: Path, prazo: int) -> dict:
    """Roda o programa CIFRAR do kit da skill: `converter` (cifra a cópia em claro `extra`) ou `criar` (cópia cifrada da
    raiz com o preparo local `extra`). Devolve o resumo da cópia cifrada, já conferida sem senha."""
    code, dados, erro = rodar(conferido.python_isolado(KIT, CIFRAR, modo, raiz, destino, rotulo, cifra["chave"], extra),
                              cwd=raiz, timeout=prazo)
    if code != 0 or not isinstance(dados, dict) or "erro" in dados:
        raise Parada("backup", "a cópia cifrada " + rotulo + " falhou (nenhuma cópia cifrada foi promovida)",
                     erro=(dados or {}).get("erro") if isinstance(dados, dict) else erro, stderr=erro)
    return {"pasta": str(destino), "rotulo": rotulo, "sha256_manifesto": dados["sha256_manifesto"], "ancora_pelo_kit": True,
            "arquivos": dados["arquivos"], "cifrada": True, "sha256_manifesto_interno": dados["sha256_manifesto_interno"],
            "destinatario": dados["destinatario"], "partes": dados["partes"]}


def _backup(codigo: Path, raiz: Path, destino: Path, rotulo: str, prazo: int = TEMPO,
            tentar_de_novo: bool = False, sem_cifra: str | None = None) -> dict:
    """`backup criar` + `backup verificar` com o código de `codigo` (cópia conferida do código da raiz ANTES; o kit da
    skill DEPOIS); a âncora vem do kit ou é calculada aqui. Com `tentar_de_novo` (a cópia ANTES, feita pelo código da
    raiz, que pode não repetir a renomeação final), a falha na promoção conta a sobra do preparo, confere que o destino
    não existe e tenta UMA vez mais, com rótulo novo; as tentativas vão para o registro (1.7.10)."""
    tentativas = []
    while True:
        code, dados, erro = fundacao(codigo, raiz, "backup", "criar", "--destino", str(destino), "--rotulo", rotulo,
                                     *(["--sem-cifra", sem_cifra] if sem_cifra else []), prazo=prazo)
        tentativas.append({"rotulo": rotulo, "destino": str(destino), "codigo": code})
        if code == 0 and isinstance(dados, dict):
            break
        tentativas[-1]["erro"] = (erro or "")[-600:]
        if not (tentar_de_novo and len(tentativas) == 1 and falha_de_promocao(code, erro or "")):
            raise Parada("backup", "`backup criar` falhou (" + rotulo + ")", erro=erro, saida=dados,
                         tentativas=tentativas)
        tentativas[-1]["sobra_do_preparo"] = sobra_do_preparo(destino)
        if os.path.lexists(destino):
            raise Parada("backup", "a promoção da cópia " + rotulo + " falhou e o destino existe: confira-o à mão antes "
                         "de repetir (nada foi alterado na raiz)", tentativas=tentativas)
        rotulo = rotulo + "-tentativa-2"
        destino = destino.with_name(rotulo)
    ancora = dados.get("sha256_manifesto") or sha(destino / "manifest.json")
    extra = ["--sha256-manifesto", ancora] if dados.get("sha256_manifesto") else []
    code, ver, erro = fundacao(codigo, raiz, "backup", "verificar", "--origem", str(destino), *extra, prazo=prazo)
    if code != 0 or not (isinstance(ver, dict) and ver.get("ok")):
        raise Parada("backup", "a cópia " + rotulo + " não conferiu", erro=erro, verificacao=ver, tentativas=tentativas)
    # O kit 1.7.9 devolve a lista `files`; o 1.7.10 só o resumo, com `arquivos` (a lista fica no manifest.json da cópia).
    arquivos = dados["arquivos"] if isinstance(dados.get("arquivos"), int) else len(dados.get("files", []))
    res = {"pasta": str(destino), "rotulo": rotulo, "sha256_manifesto": ancora,
           "ancora_pelo_kit": bool(dados.get("sha256_manifesto")), "arquivos": arquivos}
    return {**res, "tentativas": tentativas} if len(tentativas) > 1 else res


def _conferir_antes_da_promocao(raiz: Path) -> None:
    """Onde a atualização grava, conferido de novo logo antes da promoção: o `checar` rodou antes do ensaio inteiro, e
    vínculo físico ou ligação criados nesse intervalo levariam o registro da instalação, as cópias ou a âncora para
    fora da raiz (R177B-B-05). Até aqui nada foi escrito na raiz."""
    desviados = gravacao.desviados(raiz, GRAVADOS)
    if desviados:
        raise Parada("promocao", desvio(desviados, "a atualização") + "; apareceu depois do `checar`, durante o "
                     "ensaio: a raiz NÃO foi alterada")


def _instalar_kit(destino: Path) -> dict:
    code, dados, erro = rodar([sys.executable, "-B", str(INSTALAR_KIT), "--destino", str(destino), "--atualizar"],
                              cwd=AQUI)
    if code != 0 or not isinstance(dados, dict) or dados.get("composicao") != "verificada":
        raise Parada("instalar_kit", "o kit não ficou verificado em " + str(destino), codigo=code, saida=dados,
                     erro=erro)
    return dados


def _promover(raiz: Path, registro: dict) -> dict:
    """`instalar_kit.py --atualizar` na raiz e, depois, o `__pycache__` das áreas de código e do primeiro nível
    apagado sem seguir ligação: bytecode não conferido rodaria no uso normal no lugar da fonte (R177-ATU-02,
    R177B-B-06). O instalador que parava depois de gravar (código 3 com o registro da instalação não gravado ou a
    composição divergente; 5 com a promoção que falhou) deixava a raiz no kit novo sem registro ancorado, e o
    `desfazer` recusava. Agora, sem `nada_escrito` na saída dele, a promoção entra no registro marcada como
    interrompida, com a saída (o plano que o `desfazer` devolve), e o bytecode sai do mesmo jeito; o `aplicar` grava e
    ancora o registro antes de parar. Com `nada_escrito`, para como antes; sem saída legível não há plano, e a volta é
    a cópia ANTES (C9) (terceira passada, R177C-B-04). A promoção que falhou e o próprio instalador desfez (código 5,
    `desfeito`, composição `nao_alterada`; no Windows, por exemplo, arquivo preso pelo antivírus) deixa o código da
    raiz como estava: conta como `nada_escrito`, sem âncora nem `__pycache__` apagado, e a mensagem diz que a raiz não
    foi alterada; antes ia para o registro ancorado, e o `desfazer` recusava e mandava à cópia ANTES (quarta passada,
    R177D-5). São as duas únicas saídas do instalador sem nada mudado nas áreas de código."""
    try:
        registro["promocao"] = {"instalar_kit": _instalar_kit(raiz)}
    except Parada as p:
        saida, codigo = p.detalhes.get("saida"), p.detalhes.get("codigo")
        if isinstance(saida, dict) and saida.get("nada_escrito") is True:
            raise  # nada foi gravado na raiz
        if isinstance(saida, dict) and saida.get("desfeito") is True and saida.get("composicao") == "nao_alterada":
            raise Parada("instalar_kit", "a promoção falhou, e o próprio instalador a desfez (código " + str(codigo)
                         + "): o código da raiz continua o de antes e NÃO foi alterado; veja `erros` na saída do "
                         "instalador (por exemplo, arquivo preso pelo antivírus), resolva e repita o `aplicar`",
                         **p.detalhes) from None  # como com `nada_escrito`: sem âncora nem `__pycache__` apagado
        apagado, nao_apagado = conferido.apagar_bytecode(raiz)  # a raiz pode ter ficado com o código novo
        if not isinstance(saida, dict):  # sem a saída do instalador, não há plano para o `desfazer`
            raise Parada("instalar_kit", "o instalador parou sem saída legível (código " + str(codigo) + "): a raiz "
                         "pode ter sido alterada; confira e, para voltar, restaure a cópia ANTES numa pasta nova (C9)",
                         bytecode_apagado=apagado, bytecode_nao_apagado=nao_apagado, **p.detalhes) from None
        motivo = ("o instalador parou depois de gravar na raiz (código " + str(codigo) + ", composição "
                  + str(saida.get("composicao")) + "): a promoção ficou interrompida, e a raiz pode estar no kit "
                  "novo, sem `init`; o `desfazer` com o registro desta atualização devolve o código anterior")
        registro["promocao"] = {"instalar_kit": saida, "interrompida": motivo, "bytecode_apagado": apagado,
                                "bytecode_nao_apagado": nao_apagado}
        raise Parada("instalar_kit", motivo, **p.detalhes) from None
    promo = registro["promocao"]
    promo["bytecode_apagado"], promo["bytecode_nao_apagado"] = conferido.apagar_bytecode(raiz)
    return promo


def _init_e_cadeia(raiz: Path, etapa: str) -> dict:
    """`init` e `eventos verificar` com o kit da skill (o mesmo código que a raiz ou a cópia acabou de receber)."""
    code, init, erro = fundacao(KIT, raiz, "init")
    if code != 0:
        raise Parada(etapa, "`init` falhou", erro=erro, saida=init)
    code, cadeia, erro = fundacao(KIT, raiz, "eventos", "verificar")
    if code != 0 or not (isinstance(cadeia, dict) and cadeia.get("cadeia_integra") is True):
        raise Parada(etapa, "a cadeia de eventos não conferiu depois do `init`", erro=erro, saida=cadeia)
    return {"init": init, "cadeia_de_eventos": cadeia}


def _dentro_da_raiz(caminho: Path, raiz: Path) -> bool:
    """`caminho` é a raiz ou fica dentro dela, pelo caminho resolvido (ligação, caixa) e, onde o sistema dá identidade
    de arquivo, pelo objeto do disco de cada ancestral (nome curto do Windows), como o kit faz com o destino da cópia
    (core/ancora_copia.py, dentro_da_copia; revisão de segurança da 1.7.10, KIT-F7)."""
    alvo, real = Path(os.path.realpath(caminho)), Path(os.path.realpath(raiz))
    if alvo == real or alvo.is_relative_to(real):
        return True
    try:
        st = os.stat(real)
    except OSError:
        return False
    for ancestral in (alvo, *alvo.parents) if st.st_ino else ():
        try:
            atual = os.stat(ancestral)
        except OSError:
            continue
        if (atual.st_dev, atual.st_ino) == (st.st_dev, st.st_ino):
            return True
    return False


def _base_do_ensaio(raiz: Path, backups: Path, pasta: Path | None, cifra: dict | None = None) -> Path:
    """Onde a cópia de ensaio nasce (uma pasta nova dentro dela): `--pasta-ensaio` ou, por padrão, a pasta das cópias
    (`--backups`), no disco das cópias. Dentro da raiz, recusa: a cópia da fundação cairia nela mesma. A pasta das
    cópias também, com ou sem --pasta-ensaio (revisão de segurança da 1.7.10, KIT-F7, correções da revisão 1): a cópia
    ANTES, feita pelo kit da raiz (o anterior aceita destino dentro dela), nasceria ao alcance das sessões dos projetos,
    e a cópia DEPOIS, pelo kit novo, seria recusada só depois da promoção."""
    if _dentro_da_raiz(backups, raiz):
        raise Parada("checar", "a pasta das cópias (--backups: " + str(backups) + ") fica dentro da raiz da fundação: "
                     "use uma pasta fora dela, que só o titular altera (de preferência em outro disco); nada foi "
                     "alterado")
    cifrada = bool(cifra) and cifra.get("modo") == "cifrada"
    if cifrada:  # 1.7.11: o preparo local e o ensaio ficam no disco local, nunca no disco das cópias
        local = Path(os.path.abspath(cifra["preparo_base"]))
        if _dentro_da_raiz(local, raiz) or _dentro_da_raiz(local, backups) or _dentro_da_raiz(backups, local):
            raise Parada("checar", "o preparo local das cópias cifradas (" + str(local) + ") fica dentro da raiz ou "
                         "dentro/sobre a pasta das cópias: ele tem de ser local e separado; nada foi alterado")
    base = Path(os.path.abspath(pasta if pasta is not None else (cifra["preparo_base"] if cifrada else backups)))
    if cifrada and _dentro_da_raiz(base, backups):
        raise Parada("checar", "com a chave da cópia instalada o ensaio não nasce no disco das cópias (" + str(base) + "): "
                     "a raiz restaurada ficaria em claro nele; use o padrão (disco local) ou --sem-cifra \"<motivo>\"; "
                     "nada foi alterado")
    if _dentro_da_raiz(base, raiz):
        raise Parada("checar", "a pasta do ensaio (" + str(base) + ") fica dentro da raiz da fundação: use a pasta das "
                     "cópias (--backups) ou outra fora dela; nada foi alterado")
    return base


def _ensaio(raiz: Path, codigo: Path, conferidos: dict, antes: dict, padrao: str, manter: bool = False,
            pasta_base: Path | None = None, prazo: int = TEMPO, limpeza: dict | None = None) -> dict:
    """Restaura a cópia ANTES numa pasta nova dentro de `pasta_base` (padrão: a temporária do sistema) e aplica nela o
    kit novo, com `init`, cadeia e suíte. Regressão = teste que falha na cópia atualizada e não falhava antes, ou que
    passava e na cópia sumiu ou passou a ser pulado sem a retirada declarada pelo kit novo (catraca, proposta 5). A
    suíte de antes roda de uma cópia conferida do código da raiz e a de depois, de uma cópia conferida da cópia
    atualizada (#8). As cópias têm os dados da fundação: são apagadas no fim, também na falha (o registro guarda o
    motivo de cada teste), salvo com `manter`; a limpeza é contada em `limpeza["ensaio"]` (1.7.10)."""
    limpeza = {} if limpeza is None else limpeza
    if pasta_base is not None:
        pasta_base.mkdir(parents=True, exist_ok=True)
    tmp = Path(tempfile.mkdtemp(prefix="ensaio-atualizacao-", dir=str(pasta_base) if pasta_base else None))
    limpeza["pasta_do_ensaio"] = str(tmp)
    try:
        base = suite(raiz, conferidos, padrao, tmp / "testes-antes", prazo)
        return _ensaio_na_copia(raiz, codigo, antes, padrao, base, tmp, prazo)
    except Parada as p:
        if not manter:
            p.detalhes["copia_de_ensaio"] = None
            p.detalhes["copia_apagada"] = "use --manter-ensaio para examiná-la"
        raise
    finally:
        limpeza["ensaio"] = {"mantida": str(tmp)} if manter else limpar(tmp)


def _ensaio_na_copia(raiz: Path, codigo: Path, antes: dict, padrao: str, base: dict, tmp: Path,
                     prazo: int = TEMPO) -> dict:
    copia = tmp / "raiz"
    extra = ["--sha256-manifesto", antes["sha256_manifesto"]] if antes["ancora_pelo_kit"] else []
    sem_wsl("ensaio", raiz)  # a cópia ANTES levou dezenas de minutos: o Ubuntu pode ter sido aberto nesse meio-tempo
    code, rest, erro = fundacao(codigo, raiz, "backup", "restaurar", "--origem", antes["pasta"], "--destino",
                                str(copia), "--retiradas", str(raiz / "state" / "retiradas.jsonl"), *extra,
                                prazo=prazo)
    if code != 0 or not (isinstance(rest, dict) and rest.get("released")):
        raise Parada("ensaio", "a cópia ANTES não restaurou numa pasta de ensaio", erro=erro, saida=rest,
                     copia_de_ensaio=str(copia))
    kit = _instalar_kit(copia)
    conferencia = _init_e_cadeia(copia, "ensaio")
    depois = suite(copia, arquivos_do_kit(), padrao, tmp / "testes-depois", prazo)
    regressoes = sorted(set(depois["falhas"]) - set(base["falhas"]))
    declaradas = retiradas_declaradas()
    passavam = set(base.get("ids", [])) - set(base["falhas"]) - set(base.get("pulados_ids", {}))
    sumidos = sorted(set(base.get("ids", [])) - set(depois.get("ids", [])) - set(declaradas))
    pulados_novos = sorted((passavam & set(depois.get("pulados_ids", {}))) - set(declaradas))
    ensaio = {"suite_antes_na_raiz": base, "suite_na_copia_atualizada": depois, "regressoes": regressoes,
              "copias_conferidas": True,  # as duas suítes rodaram de cópias conferidas por hash (#8)
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
    no host é informação para o titular conferir e regravar, não falha da atualização do kit. Roda depois do registro,
    com TEMPO_INVENTARIO: travar ou falhar vira `conferido: False` com o motivo, nunca exceção (R177-VAL-04)."""
    arq, erro = raiz / INVENTARIO_HOST, ""
    if not arq.is_file():
        return None
    try:
        _code, dados, erro = rodar([sys.executable, "-B", str(INVENTARIAR_HOST), "verificar", "--inventario",
                                    str(arq), "--raiz", str(raiz)], cwd=AQUI, timeout=TEMPO_INVENTARIO)
        mudancas = {cat: {k: len(v) for k, v in d.items() if v} for cat, d in dados["diferencas"].items()}
    except subprocess.TimeoutExpired:
        return {"conferido": False, "motivo": "tempo esgotado: " + str(TEMPO_INVENTARIO) + " s"}
    except Exception as exc:  # noqa: BLE001 — informativo: nada aqui derruba a atualização já registrada
        return {"conferido": False, "motivo": "saída inesperada (" + type(exc).__name__ + ") " + (erro or "")[-200:]}
    return {"conferido": True, "sem_mudancas": bool(dados.get("ok")),
            "mudancas": {cat: m for cat, m in mudancas.items() if m}}


def _resumo_host(raiz: Path, host: dict | None) -> list:
    if not host:
        return []
    if not host.get("conferido"):
        return ["Inventário do host não conferido (" + str(host.get("motivo"))[:200] + "); a atualização já está "
                "registrada. Confira depois: "
                + comando(INVENTARIAR_HOST, "verificar", "--inventario", raiz / INVENTARIO_HOST, "--raiz", raiz)]
    return ["Ecossistema do host (skills, plugins, MCP, hooks): " + (
        "igual ao inventário." if host["sem_mudancas"] else "mudou desde o inventário: "
        + json.dumps(host["mudancas"], ensure_ascii=False) + " — confira e regrave com: "
        + comando(INVENTARIAR_HOST, "gravar", "--saida", raiz / INVENTARIO_HOST, "--raiz", raiz, "--substituir"))]


def _plano_instrucoes(raiz: Path) -> dict:
    """Só lê (`instrucoes_raiz.py gerar --simular`): o que mudaria no AGENTS.md e no CLAUDE.md da raiz."""
    _code, dados, erro = rodar([sys.executable, "-B", str(INSTRUCOES_RAIZ), "gerar", "--raiz", str(raiz), "--simular"],
                               cwd=AQUI)
    if not isinstance(dados, dict):
        return {"erro": (erro or "")[-300:]}
    if not dados.get("ok"):  # escrito à mão (conflito) ou ligação no lugar do arquivo (erro; R177-ATU-03)
        return {"conflito": dados["conflito"]} if dados.get("conflito") else {"erro": str(dados.get("erro"))[:300]}
    return {"AGENTS.md": dados["agents"]["acao"], "CLAUDE.md": dados["claude"]["acao"]}


def _instrucoes_raiz(raiz: Path, carimbo: str) -> dict:
    """Regenera o AGENTS.md e o CLAUDE.md da raiz (proposta 1), guardando antes os que já existiam, para o
    `desfazer`, numa pasta nova de registry/kit_backup/, sem ligação no caminho e com arquivos criados com
    exclusividade (R177-ATU-03). Não bloqueia: AGENTS.md escrito à mão fica como está e o resumo pede a decisão do
    titular."""
    plano = _plano_instrucoes(raiz)
    if "erro" in plano or "conflito" in plano:
        return {"gerado": False, **plano}
    rel = "registry/kit_backup/instrucoes-" + carimbo
    guarda, guardados = raiz / rel, []
    try:
        for nome, acao in plano.items():
            if acao == "atualizar":
                if not guardados:
                    gravacao.pasta_nova(raiz, rel)
                dados = (raiz / nome).read_bytes()
                gravacao.criar(guarda / nome, dados)
                guardados.append({"path": nome, "sha256_anterior": hashlib.sha256(dados).hexdigest()})
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
    if instr.get("gerado"):
        mudou = [nome for nome, acao in instr["acoes"].items() if acao != "igual"]
        return (["Instruções da raiz geradas pela skill (" + ", ".join(mudou) + "): as sessões abertas nesta pasta "
                 "passam a lê-las ao iniciar."] if mudou else [])
    if instr.get("conflito"):
        return ["O AGENTS.md da raiz foi escrito à mão e não foi alterado. Revise-o e, para a skill passar a "
                "mantê-lo (o seu texto fica no trecho do titular), rode: "
                + comando(INSTRUCOES_RAIZ, "gerar", "--raiz", raiz, "--adotar")]
    return ["Atenção: as instruções da raiz não foram geradas (" + str(instr.get("erro"))[:200] + "); "
            "rode depois: " + comando(INSTRUCOES_RAIZ, "gerar", "--raiz", raiz)]


def _so_instrucoes(raiz: Path, pre: dict, carimbo: str) -> dict:
    """Kit igual: nada a fazer no código. Se o texto que `instrucoes_raiz.py gerar` produziria difere do atual (skill
    nova com o mesmo kit), as instruções da raiz são regeneradas pelas regras dele (AGENTS.md escrito à mão, sem a
    marca da skill, não é tocado), com as anteriores guardadas e registro ancorado, que o `desfazer` aceita.
    Sem diferença, nada é escrito (defeito anotado na liberação da 1.7.6: o AGENTS.md ficava com o texto anterior)."""
    nada = ["A fundação já está no kit " + str(pre["kit_na_raiz"]) + ": nada a fazer."]
    plano = pre["instrucoes_raiz"]
    if "AGENTS.md" in plano and set(plano.values()) == {"igual"}:
        return {"ok": True, "nada_a_fazer": True, "checar": pre, "resumo": nada}
    instr = _instrucoes_raiz(raiz, carimbo) if "AGENTS.md" in plano else {"gerado": False, **plano}
    if not instr.get("gerado") and ("conflito" in instr or "AGENTS.md" not in plano):  # nada foi escrito
        return {"ok": True, "nada_a_fazer": True, "checar": pre, "resumo": nada + _resumo_instrucoes(raiz, instr)}
    registro = {"schema_version": "fundacao.atualizacao/1", "raiz": str(raiz), "iniciado_em": carimbo,
                "kit_antes": pre["kit_na_raiz"], "kit_da_skill": pre["kit_da_skill"], "identidade": pre["identidade"],
                "user_version_antes": pre["user_version"], "so_instrucoes": True, "instrucoes_raiz": instr,
                "concluido_em": agora()}
    arq = gravar(raiz, "instrucoes-raiz-" + carimbo + ".json", registro, ancorar=bool(instr.get("gerado")))
    resumo = ["A fundação já está no kit " + str(pre["kit_na_raiz"]) + ": o código não muda."]
    resumo += _resumo_instrucoes(raiz, instr) + ["Registro: " + str(arq) + "."]
    if instr.get("gerado"):
        if instr.get("copia"):
            resumo.append("As versões anteriores ficaram em " + instr["copia"] + ".")
        resumo.append("Para voltar as instruções: " + comando(Path(__file__), "desfazer", "--registro", arq))
    return {"ok": True, "nada_a_fazer": False, "so_instrucoes": True, "registro": str(arq), "resumo": resumo}


def aplicar(raiz: Path, backups: Path, padrao: str, manter_ensaio: bool = False, pasta_ensaio: Path | None = None,
            prazo: int | None = None, sem_cifra: str | None = None, cifra: dict | None = None) -> dict:
    raiz, backups = Path(raiz).resolve(), Path(backups).resolve()
    wsl = sem_wsl("checar", raiz)  # antes de começar: o `checar` já abre o banco (somente leitura)
    carimbo = agora()
    pre, conferidos = _inspecionar(raiz)
    if not pre["pode_aplicar"]:
        raise Parada("checar", "; ".join(pre["motivos"]), checar=pre)
    cifra = cifra or ({"modo": "claro"} if pre["nada_a_fazer"] else decisao_da_cifra(raiz, sem_cifra))
    base_do_ensaio = _base_do_ensaio(raiz, backups, pasta_ensaio, cifra)
    estimativa = None if pre["nada_a_fazer"] else estimar(raiz)
    if estimativa:
        prazo = prazo or max(TEMPO, 3 * max(estimativa["segundos"].values()))
        sys.stderr.write("Estimativa: cerca de " + str(estimativa["minutos"]) + " min para " + str(estimativa["arquivos"])
                         + " arquivos (duas cópias e a restauração do ensaio; sem as suítes). Não abra o Ubuntu até o "
                         "fim: a trava de manutenção fica em " + TRAVA.as_posix() + ".\n")
    trava = travar(raiz, "atualização do kit " + str(pre["kit_na_raiz"]) + " para " + str(pre["kit_da_skill"]))
    try:
        if pre["nada_a_fazer"]:
            res = _so_instrucoes(raiz, pre, carimbo)
        else:
            extras = {"wsl": wsl, "trava": trava, "estimativa": estimativa, "prazo_por_etapa": prazo, "cifra": cifra}
            res = _aplicar(raiz, backups, padrao, manter_ensaio, base_do_ensaio, prazo, pre, conferidos, carimbo,
                           extras)
    except Parada as p:
        p.detalhes["trava"] = destravar(raiz, trava)
        raise
    except BaseException:
        destravar(raiz, trava)
        raise
    res["trava"] = destravar(raiz, trava)
    if not res["trava"]["removida"]:
        res.setdefault("resumo", []).append("Atenção: a trava de manutenção não saiu (" + res["trava"]["motivo"] + ").")
    return res


def _aplicar(raiz: Path, backups: Path, padrao: str, manter_ensaio: bool, base_do_ensaio: Path, prazo: int,
             pre: dict, conferidos: dict, carimbo: str, extras: dict) -> dict:
    nova, antiga = pre["kit_da_skill"], pre["kit_na_raiz"]
    registro = {"schema_version": "fundacao.atualizacao/1", "raiz": str(raiz), "iniciado_em": carimbo,
                "kit_antes": antiga, "kit_da_skill": nova, "identidade": pre["identidade"],
                "mudancas": pre["mudancas"], "user_version_antes": pre["user_version"], **extras}
    limpeza = registro["limpeza"] = {}
    codigo, cifra = Path(tempfile.mkdtemp(prefix="codigo-conferido-")), extras["cifra"]
    cifrada, local = cifra["modo"] == "cifrada", None
    try:
        antes = _codigo_conferido(raiz, conferidos, codigo / "antes")  # o código ANTES roda só desta cópia
        rotulo = "antes-kit-" + nova + "-" + carimbo
        if cifrada:  # em claro no preparo local (o código da raiz), cifrada para o disco das cópias (o kit da skill)
            flag = MOTIVO_CLARO_LOCAL if (antes / "fundacao" / "core" / "politica_cifra.py").is_file() else None
            local = _backup(antes, raiz, Path(cifra["preparo_base"]) / rotulo, rotulo, prazo, tentar_de_novo=True,
                            sem_cifra=flag)
            registro["antes"] = {**_kit_cifra(raiz, "converter", backups / local["rotulo"], local["rotulo"], cifra,
                                              Path(local["pasta"]), prazo), "copia_local": local}
        else:
            registro["antes"] = local = _backup(antes, raiz, backups / rotulo, rotulo, prazo, tentar_de_novo=True)
        registro["ensaio"] = _ensaio(raiz, antes, conferidos, local, padrao, manter_ensaio, base_do_ensaio, prazo, limpeza)
        if cifrada:  # a cópia em claro do preparo local sai já: o que fica no disco das cópias é só a cifrada
            limpeza["preparo_local"] = limpar(Path(local["pasta"]))
        _conferir_antes_da_promocao(raiz)
        promo = _promover(raiz, registro)  # instalador e `__pycache__` (R177-ATU-02); interrompida: R177C-B-04
        promo.update(_init_e_cadeia(raiz, "promocao"))
        registro["user_version_depois"] = user_version(raiz)
        registro["instrucoes_raiz"] = _instrucoes_raiz(raiz, carimbo)  # antes da cópia DEPOIS, que as leva
        registro["politica_de_backup"] = politica_de_backup(raiz)  # idem: a cópia DEPOIS já leva as áreas novas
        rotulo = "depois-kit-" + nova + "-" + carimbo
        if cifrada:
            registro["depois"] = _kit_cifra(raiz, "criar", backups / rotulo, rotulo, cifra,
                                            Path(cifra["preparo_base"]) / rotulo, prazo)
        else:
            registro["depois"] = _backup(KIT, raiz, backups / rotulo, rotulo, prazo)
    except Parada as p:
        if cifrada and local and "preparo_local" not in limpeza:  # a cópia em claro do preparo local não fica
            limpeza["preparo_local"] = limpar(Path(local["pasta"]))
        limpeza["codigo"] = limpar(codigo)  # antes do registro: a contagem vai junto
        registro["falha"] = {"etapa": p.etapa, "motivo": p.motivo, **p.detalhes}
        nome = "falha-atualizacao-kit-" + nova + "-" + carimbo + ".json"
        try:  # falha depois da promoção deixa a raiz no kit novo: o `desfazer` precisa poder usar este registro
            p.detalhes["registro"] = str(gravar(raiz, nome, registro, ancorar="promocao" in registro))
        except Parada as q:
            p.detalhes["registro"], p.detalhes["registro_nao_gravado"] = None, q.motivo
        else:
            if "promocao" in registro:  # registro ancorado: o comando pronto para voltar o código (R177C-B-04)
                p.detalhes["para_voltar"] = comando(Path(__file__), "desfazer", "--registro",
                                                    Path(p.detalhes["registro"]))
        p.detalhes["limpeza"] = limpeza
        raise
    finally:
        if "codigo" not in limpeza:
            limpeza["codigo"] = limpar(codigo)
    registro["kit_depois"] = versao_do_kit(raiz)
    registro["concluido_em"] = agora()
    try:  # registro e âncora ANTES do inventário do host: travar ou falhar nele não perde a atualização (R177-VAL-04)
        arq = gravar(raiz, "atualizacao-kit-" + nova + "-" + carimbo + ".json", registro, ancorar=True)
    except Parada as p:
        raise Parada("registro", "a fundação foi atualizada, mas " + p.motivo + "; sem registro não há `desfazer`: a "
                     "volta é a cópia ANTES numa pasta nova (C9)", copia_antes=registro["antes"]["pasta"])
    host = _inventario_host(raiz)
    ensaio, cifrada = registro["ensaio"], cifra["modo"] == "cifrada"
    resumo = ["Fundação atualizada do kit " + str(antiga) + " para " + str(registro["kit_depois"]) + ".",
              *(["As cópias ANTES e DEPOIS estão CIFRADAS para a chave do titular (só ele as abre, com a senha); "
                 "a cópia em claro do preparo local foi apagada."] if cifrada else []),
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
    if registro["promocao"]["bytecode_nao_apagado"]:
        resumo.append("Atenção: o bytecode destas pastas não foi apagado; apague-as antes de usar a fundação (o Python "
                      "as refaz da fonte): " + "; ".join(registro["promocao"]["bytecode_nao_apagado"][:3]))
    if len(registro["antes"].get("tentativas", [])) > 1:
        resumo.append("A cópia ANTES falhou na promoção e foi refeita com o rótulo " + registro["antes"]["rotulo"]
                      + "; a sobra do preparo da primeira tentativa (contada no registro) tem os dados da fundação: "
                      "apague-a pela Lixeira, com o OK do titular.")
    if cifra.get("sem_cifra"):
        resumo.append("Atenção: as cópias saíram em CLARO por --sem-cifra (motivo: " + cifra["sem_cifra"] + ").")
    resumo += _resumo_limpeza(registro["limpeza"])
    resumo += _resumo_instrucoes(raiz, registro["instrucoes_raiz"]) + _resumo_politica(registro["politica_de_backup"])
    resumo += _resumo_host(raiz, host)
    resumo.append("Para voltar o código: " + comando(Path(__file__), "desfazer", "--registro", arq))
    return {"ok": True, "registro": str(arq), "inventario_host": host, "estimativa": registro["estimativa"],
            "limpeza": registro["limpeza"], "resumo": resumo}


def _resumo_limpeza(limpeza: dict) -> list:
    """Sobra do ensaio ou do código conferido, que antes passava em silêncio: tem os dados da fundação."""
    linhas = []
    for nome, rotulo in (("ensaio", "da cópia de ensaio"), ("codigo", "da cópia conferida do código"),
                         ("preparo_local", "da cópia em claro do preparo local")):
        res = limpeza.get(nome) or {}
        if res.get("mantida"):
            linhas.append("A cópia de ensaio ficou em " + res["mantida"] + " (--manter-ensaio): ela tem os dados da "
                          "fundação; apague-a depois de examinar.")
        elif res and not res.get("limpa"):
            s = res.get("sobra") or {}
            linhas.append("Atenção: sobrou parte " + rotulo + " em " + str(res.get("pasta")) + " ("
                          + str(s.get("arquivos")) + " arquivos, " + str(s.get("pastas")) + " pastas, "
                          + str(s.get("bytes")) + " bytes; erros no registro): apague-a pela Lixeira, com o OK do "
                          "titular.")
    return linhas


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    c = sub.add_parser("checar")
    c.add_argument("--raiz", type=Path, required=True)
    a = sub.add_parser("aplicar")
    a.add_argument("--raiz", type=Path, required=True)
    a.add_argument("--backups", type=Path, required=True,
                   help="pasta das cópias ANTES e DEPOIS (de preferência em outro disco; nunca dentro da raiz)")
    a.add_argument("--padrao-testes", default="test*.py", help="padrão da suíte de conformidade no ensaio")
    a.add_argument("--manter-ensaio", action="store_true",
                   help="não apaga a cópia de ensaio (ela tem os dados da fundação; apague-a depois de examinar)")
    a.add_argument("--pasta-ensaio", type=Path, default=None,
                   help="onde nasce a pasta nova do ensaio (padrão: a de --backups; com a chave da cópia instalada, o "
                        "preparo local, no disco interno, e nunca o disco das cópias; nunca dentro da raiz)")
    a.add_argument("--sem-cifra", metavar="MOTIVO", default=None,
                   help="grava as cópias em claro mesmo com a chave da cópia instalada (o motivo vai no registro)")
    a.add_argument("--prazo", type=int, default=None,
                   help="segundos por subprocesso longo (cópia, verificação, restauração e suíte); padrão: o maior "
                        "entre 3600 e três vezes a maior etapa estimada")
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
            if args.prazo is not None and args.prazo < 60:
                ap.error("--prazo deve ter pelo menos 60 segundos")
            res = aplicar(args.raiz, args.backups, args.padrao_testes, args.manter_ensaio, args.pasta_ensaio,
                          args.prazo, args.sem_cifra)
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
