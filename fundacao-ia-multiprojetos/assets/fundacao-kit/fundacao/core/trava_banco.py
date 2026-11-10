"""Trava do banco entre o Windows e o Ubuntu (1.7.10; contratos do lote 2, §4; crítica do desenho, lente de
viabilidade, "trava global do banco").

A regra de AGENTS.md — o banco `state/state.sqlite` nunca é aberto pelo Windows e pelo WSL ao mesmo tempo — passa a ser
conferida, não só seguida:
- Marcador `state/banco.trava`, JSON com `lado` ("windows" ou "ubuntu"), `host`, `pid`, `desde` e `renovada_em`, gravado
  por quem segura o banco por tempo longo: o porteiro do Ubuntu (`assets/host/wsl/porteiro.py`), do início ao fim da
  sessão do projeto, renovado a cada RENOVAR_S segundos e com `flock` entre os porteiros (vários projetos abertos).
- `conferir`, chamada por `core/db.py` ao abrir o banco: marcador do OUTRO lado recusa (`BancoTravado`), vivo ou velho;
  marcador do mesmo lado, ou nenhum, não muda nada (quem abre do mesmo lado continua como antes). Marcador ilegível
  (ligação, outro tipo de arquivo, acima do teto, fora da forma) também recusa: não se sabe de que lado ele é.
- Marcador velho (sem renovação há mais de VIVO_S segundos) sai pelo comando explícito do titular, `python -m fundacao
  banco destravar --confirmar`, que recusa o marcador ainda vivo. Única exceção (1.7.11; lição 6 da 1.7.10.2): o lado do
  Windows, ao ABRIR o banco para escrita (`core/db.connect`), tira sozinho o marcador do Ubuntu quando as quatro coisas
  valem juntas: o marcador é do Ubuntu, está velho, é do host desta máquina e NENHUMA distribuição do WSL está em
  execução (`wsl.exe -l --running -q`, medido na hora). Sem WSL em execução não há processo do Linux com o banco aberto.
  Qualquer dúvida (WSL ligado, `wsl.exe` ausente, com erro ou lento, host diferente, marcador do Windows, vivo ou
  ilegível) mantém a regra de antes: recusa e dá o comando ao titular. A saída sozinha nunca é silenciosa: o evento
  `banco_marcador_velho_liberado` (conteúdo do marcador, medida do WSL, quem e quando) entra na cadeia de eventos ANTES
  de o marcador sair, e um aviso vai para o stderr. A leitura (`conectar_somente_leitura`) e as conferências de
  backup/atualização não tiram nada: só recusam. Limite: `wsl -l` enxerga só as distribuições do usuário do Windows que
  o roda; WSL de OUTRO usuário do Windows nesta máquina não aparece.
Limites (registre sempre): no Windows o kit só confere — os comandos curtos do coordenador não gravam marcador, e o
porteiro não os vê; a trava de manutenção (`state/manutencao.json`) cobre o backup e a atualização. O marcador é um
arquivo comum da raiz: quem grava `state/` o forja ou o apaga. É guarda-corpo contra o engano, não barreira contra uma
sessão tomada; com a raiz em /mnt/e, onde o sandbox não confinou os comandos nas sondas de 31/10/2026, um comando da
sessão do Ubuntu ainda alcança o banco por fora do porteiro (camada lógica, até o canário passar no ambiente real).
"""

from __future__ import annotations

import json
import os
import socket
import stat
import subprocess
from datetime import datetime, timezone
from pathlib import Path

from . import wsl_estado
from .contracts import FundacaoError, ValidationError
from .wsl_estado import WSL_PRAZO_S

MARCADOR = "banco.trava"  # na pasta do banco (state/)
EVENTO_LIBERADO = "banco_marcador_velho_liberado"  # trilha da saída sozinha (cadeia de eventos do banco)
LADOS = ("windows", "ubuntu")
CAMPOS = ("lado", "host", "pid", "desde", "renovada_em")
VIVO_S = 120    # renovado há menos que isto: vivo (o porteiro renova a cada RENOVAR_S)
RENOVAR_S = 30
TETO = 4096     # bytes: o marcador é pequeno; maior que isto não é marcador
_SUBSTITUTA_DE_NOME = 0x20000000  # Windows: junção, link simbólico e afins (bit 29 da etiqueta de reparse)
_LER = os.O_RDONLY | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_BINARY", 0) | getattr(os, "O_NONBLOCK", 0)


class BancoTravado(FundacaoError):
    """O banco está (ou pode estar) em uso pelo outro lado: não abre. Sai pelo contrato da CLI (código 2)."""

    code = "E_BANCO_TRAVADO"


def lado_desta_maquina() -> str:
    return "windows" if os.name == "nt" else "ubuntu"


def _data(texto) -> datetime | None:
    if not isinstance(texto, str):
        return None
    try:
        data = datetime.fromisoformat(texto.replace("Z", "+00:00"))
    except ValueError:
        return None
    return data if data.tzinfo else data.replace(tzinfo=timezone.utc)


def valido(marcador) -> bool:
    """O marcador na forma do contrato: os cinco campos, o lado conhecido, o pid inteiro e as duas datas."""
    return (isinstance(marcador, dict) and set(marcador) == set(CAMPOS) and marcador["lado"] in LADOS
            and isinstance(marcador["host"], str) and type(marcador["pid"]) is int
            and _data(marcador["desde"]) is not None and _data(marcador["renovada_em"]) is not None)


def ler(pasta) -> dict | None:
    """O marcador da pasta do banco; None sem marcador; {"ilegivel": motivo} quando não dá para confiar no que há ali
    (ligação, outro tipo de arquivo, vínculo físico, acima do teto, fora da forma). Não segue ligação."""
    arquivo = Path(pasta) / MARCADOR
    try:
        antes = os.lstat(arquivo)
    except FileNotFoundError:
        return None
    except OSError as exc:
        return {"ilegivel": type(exc).__name__}
    if (stat.S_ISLNK(antes.st_mode) or getattr(antes, "st_reparse_tag", 0) & _SUBSTITUTA_DE_NOME
            or not stat.S_ISREG(antes.st_mode)):
        return {"ilegivel": "não é arquivo comum (ligação ou outro tipo)"}
    if antes.st_nlink != 1 or antes.st_size > TETO:
        return {"ilegivel": "vínculo físico ou acima do teto"}
    try:
        fd = os.open(arquivo, _LER)
        try:
            dados = os.read(fd, TETO + 1)
        finally:
            os.close(fd)
        marcador = json.loads(dados.decode("utf-8"))
    except (OSError, ValueError) as exc:  # some no meio, ligação no lugar, lixo ou outro código
        return {"ilegivel": type(exc).__name__}
    return marcador if valido(marcador) else {"ilegivel": "fora da forma do marcador"}


def idade_s(marcador: dict | None, agora: datetime | None = None) -> float | None:
    """Segundos desde a última renovação; None sem marcador legível."""
    if not marcador or "ilegivel" in marcador:
        return None
    return ((agora or datetime.now(timezone.utc)) - _data(marcador["renovada_em"])).total_seconds()


def situacao(marcador: dict | None, agora: datetime | None = None) -> str:
    """"ausente", "ilegivel", "vivo" (renovado há menos de VIVO_S segundos) ou "velho"."""
    if marcador is None:
        return "ausente"
    if "ilegivel" in marcador:
        return "ilegivel"
    return "vivo" if idade_s(marcador, agora) < VIVO_S else "velho"


def _comando_destravar(pasta: Path) -> str:
    return f'python -m fundacao --raiz "{Path(pasta).parent}" banco destravar --confirmar'


def wsl_em_execucao() -> dict:
    """Quais distribuições do WSL estão em execução agora: {"medido": True, "em_execucao": [nomes], "registradas":
    [nomes]} ou {"medido": False, "motivo": ...}. Só no Windows. Usa as saídas `-q` (só nomes, sem o texto traduzido do
    wsl.exe): `-l --running -q` vazia com código 0 é "nenhuma em execução" e `-l -q` tem de listar ao menos uma
    registrada, para a resposta vazia não ser uma falha disfarçada. Código diferente de 0, saída ilegível, tempo
    esgotado ou wsl.exe ausente: "não medido" (quem decide trata como dúvida)."""
    if lado_desta_maquina() != "windows":
        return {"medido": False, "motivo": "o WSL só se mede pelo Windows"}
    try:
        cod_exec, saida_exec = wsl_estado._rodar_wsl(["-l", "--running", "-q"])
        cod_reg, saida_reg = wsl_estado._rodar_wsl(["-l", "-q"])
    except subprocess.TimeoutExpired:
        return {"medido": False, "motivo": f"o wsl.exe não respondeu em {WSL_PRAZO_S} s"}
    except (OSError, subprocess.SubprocessError) as exc:
        return {"medido": False, "motivo": f"o wsl.exe não rodou ({type(exc).__name__})"}
    if cod_exec != 0 or cod_reg != 0:
        return {"medido": False, "motivo": f"o wsl.exe terminou com erro (código {cod_exec} e {cod_reg})"}
    em_execucao, registradas = wsl_estado._nomes_do_wsl(saida_exec), wsl_estado._nomes_do_wsl(saida_reg)
    if em_execucao is None or registradas is None:
        return {"medido": False, "motivo": "a saída do wsl.exe não está em UTF-16"}
    if not registradas:
        return {"medido": False, "motivo": "o wsl.exe não listou nenhuma distribuição registrada"}
    return {"medido": True, "em_execucao": em_execucao, "registradas": registradas}


def _host_local() -> str:
    return socket.gethostname()


def _mesmo_host(host: str) -> bool:
    return host.strip().casefold() == _host_local().strip().casefold()


def avaliar_liberacao(pasta, marcador: dict, *, lado: str | None = None, agora: datetime | None = None,
                      wsl: dict | None = None) -> dict:
    """O marcador `marcador` (lido de `pasta`) pode sair sozinho? {"pode": bool, "motivo": str, "wsl": dict | None,
    "marcador": dict | None, "idade_s": float | None}. Pode só se TODAS valem: este lado é o Windows; o marcador é
    legível, do Ubuntu, velho e do host desta máquina (o host é conferido antes de chamar o wsl.exe); o WSL foi medido
    e nenhuma distribuição está em execução; e o marcador, relido depois da medida, é o mesmo. Qualquer dúvida: não.
    `wsl` é uma medida já feita (`wsl_em_execucao()`), para não medir duas vezes."""
    lado = lado or lado_desta_maquina()

    def nao(motivo: str, medida: dict | None = None) -> dict:
        return {"pode": False, "motivo": motivo, "wsl": medida, "marcador": None, "idade_s": None}

    if not isinstance(marcador, dict) or "ilegivel" in marcador:
        return nao("o marcador não é legível: só o titular decide")
    if lado != "windows":
        return nao("só o lado do Windows tira o marcador sozinho")
    if marcador["lado"] != "ubuntu":
        return nao("o marcador é do lado do Windows: só o titular decide")
    if situacao(marcador, agora) != "velho":
        return nao("o marcador ainda é recente (renovado há menos de %d s)" % VIVO_S)
    if not _mesmo_host(marcador["host"]):
        return nao(f"o marcador é de outro host ({marcador['host']}), não desta máquina")
    wsl = wsl if wsl is not None else wsl_em_execucao()
    if not wsl["medido"]:
        return nao(f"não deu para medir o WSL: {wsl['motivo']}", wsl)
    if wsl["em_execucao"]:
        return nao("há distribuição do WSL em execução (" + ", ".join(wsl["em_execucao"]) + "): o Ubuntu pode estar "
                   "usando o banco", wsl)
    if ler(pasta) != marcador:
        return nao("o marcador mudou durante a conferência", wsl)
    return {"pode": True, "motivo": "marcador velho do Ubuntu, deste host, sem nenhuma distribuição do WSL em execução",
            "wsl": wsl, "marcador": marcador, "idade_s": idade_s(marcador, agora)}


def _recusa(pasta: Path, marcador: dict, lado: str, agora: datetime | None, nao_tirado: str | None = None
            ) -> BancoTravado:
    arquivo = Path(pasta) / MARCADOR
    s = situacao(marcador, agora)
    if s == "ilegivel":
        return BancoTravado(f"o marcador {arquivo} existe e não é legível ({marcador['ilegivel']}): o banco não abre "
                            "sem saber de que lado ele está em uso. Confira-o à mão; se nada usa o banco, o titular o "
                            f"tira com: {_comando_destravar(pasta)}", situacao=s)
    detalhes = {k: marcador[k] for k in CAMPOS}
    idade = round(idade_s(marcador, agora) or 0)
    if s == "vivo":
        return BancoTravado(f"o banco está em uso pelo {marcador['lado']} (host {marcador['host']}, pid "
                            f"{marcador['pid']}, desde {marcador['desde']}, renovado há {idade} s): feche o que o usa "
                            f"lá (no Ubuntu, as sessões de projeto) antes de abri-lo pelo {lado}", situacao=s,
                            **detalhes)
    extra = {"nao_tirado_sozinho": nao_tirado} if nao_tirado else {}
    sufixo = f" (não saiu sozinho: {nao_tirado})" if nao_tirado else ""
    return BancoTravado(f"há um marcador antigo do {marcador['lado']} (host {marcador['host']}, sem renovação há "
                        f"{idade} s): se nada usa o banco lá — feche as sessões e confira —, o titular o tira com: "
                        f"{_comando_destravar(pasta)}{sufixo}", situacao=s, **detalhes, **extra)


def conferir(pasta, *, lado: str | None = None, agora: datetime | None = None,
             liberar_sozinho: bool = False) -> dict | None:
    """Chamada ao abrir o banco da pasta `pasta` (state/): recusa com marcador do outro lado ou ilegível. Sem marcador,
    ou com o do mesmo lado, não faz nada (devolve None). Com `liberar_sozinho` (só `core/db.connect`, a abertura para
    escrita, que pode gravar o evento), um marcador que passa em `avaliar_liberacao` não recusa: devolve o plano
    (`pode` verdadeiro, com o marcador lido), que quem chamou cumpre com `liberar` DEPOIS de gravar o evento. Sem passar,
    recusa como sempre e acrescenta o motivo de não ter saído sozinho."""
    marcador = ler(pasta)
    if marcador is None:
        return None
    lado = lado or lado_desta_maquina()
    if "ilegivel" not in marcador and marcador["lado"] == lado:
        return None
    nao_tirado = None
    if liberar_sozinho:
        plano = avaliar_liberacao(pasta, marcador, lado=lado, agora=agora)
        if plano["pode"]:
            return plano
        nao_tirado = plano["motivo"]
    raise _recusa(Path(pasta), marcador, lado, agora, nao_tirado)


def liberar(pasta, plano: dict) -> bool:
    """Cumpre o plano de `conferir(liberar_sozinho=True)`: tira o marcador, só se ele ainda é exatamente o do plano.
    False se já tinha saído (outra abertura se adiantou); BancoTravado se mudou (alguém o renovou ou trocou)."""
    atual = ler(pasta)
    if atual is None:
        return False
    if atual != plano["marcador"]:
        raise BancoTravado("o marcador mudou antes de sair: o banco pode estar em uso; nada foi tirado",
                           situacao=situacao(atual))
    try:
        os.unlink(Path(pasta) / MARCADOR)  # tira o nome: ligação no lugar já foi recusada por `ler`
    except FileNotFoundError:
        return False
    return True


def descrever(pasta, agora: datetime | None = None) -> dict:
    """`banco situacao`: o marcador e a situação dele, sem abrir o banco nem exigir identidade. No Windows diz também
    se alguma distribuição do WSL está em execução (`wsl`) e, com marcador velho ou ilegível, o que fazer."""
    marcador = ler(pasta)
    s = situacao(marcador, agora)
    res = {"marcador": str(Path(pasta) / MARCADOR), "situacao": s, "lado_desta_maquina": lado_desta_maquina(),
           "vivo_ate_s": VIVO_S}
    if lado_desta_maquina() == "windows":
        res["wsl"] = wsl_em_execucao()
    if marcador is not None:
        res["conteudo"] = marcador
        res["renovado_ha_s"] = idade_s(marcador, agora)
        if s in ("velho", "ilegivel"):
            res["para_o_titular"] = _comando_destravar(Path(pasta))
            res["o_que_fazer"] = _o_que_fazer(Path(pasta), marcador, s, res.get("wsl"), agora)
    return res


def _o_que_fazer(pasta: Path, marcador: dict, s: str, wsl: dict | None, agora: datetime | None) -> str:
    """Frase em português simples para o titular (marcador velho ou ilegível)."""
    comando = _comando_destravar(pasta)
    if wsl is None:
        return ("Confira se alguma sessão do Ubuntu usa o banco; se nenhuma usa, tire o marcador com: " + comando)
    if not wsl["medido"]:
        return (f"Não deu para ver se o Ubuntu está ligado ({wsl['motivo']}). Feche o Ubuntu (wsl --shutdown) e, só "
                f"depois, tire o marcador com: {comando}")
    if wsl["em_execucao"]:
        return ("O Ubuntu está ligado (" + ", ".join(wsl["em_execucao"]) + "): feche as sessões de projeto e depois o "
                "Ubuntu (wsl --shutdown) antes de tirar o marcador. Com ele fechado, o marcador velho sai sozinho na "
                f"próxima abertura do banco, ou com: {comando}")
    plano = avaliar_liberacao(pasta, marcador, agora=agora, wsl=wsl)
    if plano["pode"]:
        return ("O Ubuntu está fechado e o marcador é velho e deste computador: ele sai sozinho na próxima abertura "
                f"do banco (e fica registrado no histórico), ou agora com: {comando}")
    return (f"O Ubuntu deste computador está fechado, mas o marcador não sai sozinho ({plano['motivo']}). Se tem "
            f"certeza de que nada usa o banco, tire-o com: {comando}")


def destravar(pasta, *, confirmar: bool, agora: datetime | None = None) -> dict:
    """Comando explícito do titular: tira o marcador velho ou ilegível, só com `confirmar`. Marcador vivo (ainda
    renovado por quem segura o banco) é recusado: feche a sessão de lá primeiro. Sem marcador, nada a fazer."""
    pasta = Path(pasta)
    marcador = ler(pasta)
    s = situacao(marcador, agora)
    if marcador is None:
        return {"removido": False, "situacao": s, "mensagem": "não há marcador: o banco não está travado"}
    if s == "vivo":
        raise BancoTravado(f"o marcador ainda é renovado pelo {marcador['lado']} (pid {marcador['pid']}, há "
                           f"{round(idade_s(marcador, agora) or 0)} s): feche a sessão de lá; ele sai sozinho quando o "
                           "porteiro termina", situacao=s)
    if not confirmar:
        raise ValidationError("confirme que nada usa o banco do outro lado (sessões do Ubuntu fechadas) e repita com "
                              "--confirmar", situacao=s, conteudo=marcador)
    try:
        os.unlink(pasta / MARCADOR)  # tira o nome: ligação no lugar sai como ligação, sem tocar o destino
    except FileNotFoundError:
        return {"removido": False, "situacao": "ausente", "mensagem": "o marcador já tinha saído"}
    return {"removido": True, "situacao": s, "marcador_removido": marcador}


def executar(pasta, acao: str, *, confirmar: bool = False) -> dict:
    """`python -m fundacao banco situacao|destravar [--confirmar]` (a CLI entrega a pasta state/ da raiz)."""
    if acao == "destravar":
        return destravar(pasta, confirmar=confirmar)
    if acao == "situacao":
        return descrever(pasta)
    raise ValidationError("ação do banco desconhecida", acao=acao)
