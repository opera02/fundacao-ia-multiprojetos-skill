"""A regra única do relatório do canário (1.7.11, junção do lote B: revisão da junção, itens N1 e 4).

O ensaio de isolamento (`scripts/ensaio_isolamento_wsl.py`) grava `fundacao.ensaio_isolamento/1`. Duas ferramentas leem
esse relatório e têm de concordar sobre o que é "um relatório real": o portão do preparo do host
(`assets/host/preparo_host.py`, que o aplica) e a ferramenta do titular (`assets/host/fundacao_titular.py`, que assina o
aceite de risco dele). Cada uma carregava a sua cópia da regra; um relatório que o portão nunca aplica podia ser aceito
pelo titular. As duas carregam agora este módulo, que só usa a biblioteca padrão e nenhum outro módulo do kit (as
ferramentas o carregam pelo caminho, do kit ao lado da própria cópia, nunca o da raiz da fundação).

Sonda que falta só baixa a confiança, nunca a sobe: as sondas `SONDAS_ADIADAS` não existiam no ensaio da 1.7.10 e da
1.7.10.1 (`SONDAS_DA_1710`) nem no do lote B da 1.7.11 (`SONDAS_DA_1711`: o modo sem perguntas, M1 a M3, os
subagentes, o AGENTS.md de data/ e a menção @). O relatório desses ensaios, sem elas, continua sendo um relatório
real (a `estrutura` o aceita), para que o reprovado já instalado siga reprovado e o aceite de risco assinado para ele
siga valendo pelo SHA-256; mas ele nunca aprova (`sondas_ausentes` não vazio: o preparo do host o recusa como aprovação
e o instalar recusa o que se diz aprovado sem elas).
"""

from __future__ import annotations

import posixpath
import re

ESQUEMA_CANARIO = "fundacao.ensaio_isolamento/1"
FS_DRVFS = ("9p", "drvfs", "v9fs")  # o /mnt/<x> do WSL2 no /proc/mounts (a mesma lista que o canário mede)
VERSAO_CLAUDE = re.compile(r"^[0-9]+\.[0-9]+\.[0-9]+$")
SHA256 = re.compile(r"^[0-9a-f]{64}$")
VEREDITOS_DO_CANARIO = ("passou", "falhou", "nao_medido")

# Os ids das sondas do ensaio e a classe de cada uma: a lista do scripts/ensaio_isolamento_wsl.py (SONDAS), com teste de
# igualdade. O portão recalcula a conclusão pelos itens, com a classe daqui, nunca a do relatório (um item de comando
# rotulado "informativo" não escapa). Só a classe "comando" entra na conclusão (`confina_comandos`): "carga" (carga de
# instrução), "medida" (a medida que decide um desenho da versão, como o sudo na sessão ou os conectores da conta) e
# "informativo" são relatadas à parte e nunca aprovam nem reprovam o confinamento.
SONDAS_DO_CANARIO = {
    "leitura_outro_projeto": "comando", "leitura_state": "comando", "escrita_fora_do_projeto": "comando",
    "rede_fora_da_lista": "comando", "socket_barramento": "comando", "temp_outro_projeto": "comando",
    "fila_porteiro": "comando", "leitura_area_outro_projeto": "comando", "escrita_claude_da_raiz": "comando",
    "skill_agente_aninhado": "carga", "plugin_setting_sources_local": "comando", "marcadores_zero_byte": "informativo",
    # 1.7.11 (desenho da jaula, §10.2, M1 a M5; canário com os subagentes; a menção @; o AGENTS.md de data/):
    "modo_sem_perguntas": "medida", "sudo_na_sessao": "medida", "rede_em_mnt": "medida",
    "conectores_da_conta": "medida", "subagentes": "medida", "agents_md_exclusao": "carga", "mencao_arroba": "carga"}
# As sondas que o ensaio da 1.7.10 e da 1.7.10.1 não tinha (revisão de segurança da 1.7.10, WSL-01 e HOOK-F1).
SONDAS_DA_1710 = frozenset({"leitura_area_outro_projeto", "escrita_claude_da_raiz"})
# As sondas que o ensaio da 1.7.11 acrescentou (C01, C13, M1 a M3 e a medida do modo sem perguntas).
SONDAS_DA_1711 = frozenset({"modo_sem_perguntas", "sudo_na_sessao", "rede_em_mnt", "conectores_da_conta", "subagentes",
                            "agents_md_exclusao", "mencao_arroba"})
# Toda sonda nova entra pela regra de transição: o relatório de um ensaio que não a tinha continua um relatório real (o
# reprovado já instalado segue reprovado e o aceite de risco segue valendo pelo SHA-256), mas nunca aprova.
SONDAS_ADIADAS = SONDAS_DA_1710 | SONDAS_DA_1711


def _objeto(valor) -> dict:
    return valor if isinstance(valor, dict) else {}


def _limpo(texto) -> str:
    """O id que o relatório traz, para a mensagem: sem controle nem escape de terminal (a mensagem sai no terminal do
    titular)."""
    return re.sub(r"[^A-Za-z0-9_.-]", "?", str(texto)[:60])


def forma_do_relatorio(relatorio) -> str | None:
    """A forma de caminho que o relatório prova ('ext4' ou 'drvfs:/mnt/<x>', com o sistema de arquivos medido), ou None
    (o canário não prova outra combinação; tudo fica fechado)."""
    relatorio = _objeto(relatorio)
    forma, fs = relatorio.get("forma"), relatorio.get("sistema_de_arquivos")
    if not isinstance(forma, str) or not isinstance(fs, str):
        return None
    if forma == "ext4":
        return "ext4" if fs == "ext4" else None
    m = re.match(r"^drvfs:(/mnt/[a-z]/[^\n\r\0]*)$", forma)
    n = re.match(r"^/mnt/([a-z])(?:/|$)", posixpath.normpath(m.group(1))) if m and fs in FS_DRVFS else None
    return f"drvfs:/mnt/{n.group(1)}" if n else None


def sondas_ausentes(relatorio) -> list[str]:
    """As sondas adiadas que o relatório não tem (ordenadas): as de um ensaio anterior, que contam como não medidas.
    Só faz sentido depois de `estrutura` devolver None."""
    itens = _objeto(relatorio).get("itens")
    ids = {i.get("id") for i in itens if isinstance(i, dict)} if isinstance(itens, list) else set()
    return sorted(SONDAS_ADIADAS - ids)


def estrutura(relatorio) -> str | None:
    """Motivo pelo qual o arquivo não é um relatório real do ensaio, ou None (revisão de segurança da 1.7.10, CAN-1 e
    CI-F2: o relatório de seis campos escrito à mão não passa). Não diz se aprova: o relatório real que não aprova também
    é instalado, como revogação (CAN-2; 1.7.10.1). Real: o esquema, `simulado` false, a versão e o SHA-256 do Claude
    Code, a forma de caminho com o sistema de arquivos medido (os mesmos na conclusão), a conclusão true, false ou null,
    os itens com os ids de `SONDAS_DO_CANARIO` (sem repetir e sem id de fora; só as `SONDAS_ADIADAS` podem faltar), a
    classe de cada um e um veredito do ensaio, e o perfil, o sandbox e o temp das sessões."""
    if not isinstance(relatorio, dict) or relatorio.get("schema_version") != ESQUEMA_CANARIO:
        return f"o arquivo não é um relatório do canário ({ESQUEMA_CANARIO})"
    if relatorio.get("simulado") is not False:
        return "relatório de simulação: só o ensaio real conta"
    claude = _objeto(relatorio.get("claude"))
    versao, sha = claude.get("versao"), claude.get("sha256")
    if not (isinstance(versao, str) and VERSAO_CLAUDE.match(versao) and isinstance(sha, str) and SHA256.match(sha)):
        return "relatório sem a versão e o SHA-256 do Claude Code que o canário rodou"
    conclusao = relatorio.get("conclusao")
    if (forma_do_relatorio(relatorio) is None or not isinstance(conclusao, dict)
            or conclusao.get("forma") != relatorio.get("forma")
            or conclusao.get("sistema_de_arquivos") != relatorio.get("sistema_de_arquivos")):
        return ("relatório com uma forma de caminho que o canário não prova (só ext4 e drvfs:/mnt/<x>), ou com a "
                "conclusão de outra forma ou de outro sistema de arquivos")
    if "confina_comandos" not in conclusao or conclusao["confina_comandos"] not in (True, False, None):
        return "relatório sem a conclusão do ensaio (conclusao.confina_comandos: true, false ou null)"
    itens = relatorio.get("itens")
    if not isinstance(itens, list) or not all(isinstance(i, dict) and isinstance(i.get("id"), str) for i in itens):
        return "relatório sem os itens medidos pelo ensaio (itens, cada um com o id da sonda)"
    contagem: dict = {}
    for i in itens:
        contagem[i["id"]] = contagem.get(i["id"], 0) + 1
    faltam = set(SONDAS_DO_CANARIO) - set(contagem)
    if len(itens) != len(contagem) or set(contagem) - set(SONDAS_DO_CANARIO) or not faltam <= SONDAS_ADIADAS:
        demais = sorted(_limpo(x) for x, n in contagem.items() if x not in SONDAS_DO_CANARIO or n > 1)[:10]
        return ("os itens do relatório não são as sondas do ensaio desta versão (faltam: "
                + (", ".join(sorted(faltam - SONDAS_ADIADAS)) or "-") + "; a mais ou repetidos: "
                + (", ".join(demais) or "-") + "): rode o ensaio desta cópia da skill")
    for i in itens:
        if i.get("classe") != SONDAS_DO_CANARIO[i["id"]] or i.get("veredito") not in VEREDITOS_DO_CANARIO:
            return f"o item {i['id']} do relatório tem classe ou veredito fora do ensaio"
    if not isinstance(relatorio.get("perfil"), dict) or not isinstance(relatorio.get("temp"), dict) \
            or "sandbox_ligado" not in relatorio:
        return "relatório sem o perfil, o sandbox ou o temp das sessões do ensaio"
    return None
