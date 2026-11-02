"""O comando fixo da ferramenta do titular para a ficha de aberturas (1.7.10; contratos do lote 2, §5). Saiu de
core/aberturas.py pelo teto de tamanho (divisão por responsabilidade); core/aberturas reexporta os nomes de sempre.

A assinatura é só da ferramenta fixa do titular, nunca de comando montado pela sessão: `comando_do_titular` mostra a
forma fixa dela, só com raiz, projeto e versão, apontando para a CÓPIA PROTEGIDA da ferramenta (revisão do pacote,
31/10/2026: a cópia da skill no perfil do usuário é alterável por uma sessão do Windows, sem sandbox, e pelos comandos
de uma sessão com a raiz em /mnt/e, contratos §0): no Windows, `C:\\ProgramData\\FundacaoIA\\ferramentas\\<versão>`
(ACL de administrador, gravada pelo preparo do titular com UAC), chamada pelo Python fixado que o `hashes.json` de lá
registra; no Ubuntu, `/usr/local/lib/fundacao-ia/<versão>` (root:root, 0755), pelo `/usr/bin/python3`.

Onde o titular roda (reconferências do pacote, 31/10 e 01/11/2026): um shell já aberto e também um terminal NOVO
carregam o perfil ($PROFILE, ~/.bashrc), que a sessão pode ter gravado, e um gancho dele (PSReadLine,
PreCommandLookupAction, trap DEBUG) troca a ferramenta e captura a senha da chave. Só a caixa Executar (Win+R) evita o
perfil: ela abre o python.exe direto (`executar_windows`) ou o `wsl.exe -e python3`, sem bash (`executar_ubuntu`), e a
ferramenta espera um Enter antes de a janela fechar. As formas `powershell` e `bash` ficam como último recurso, com esse
risco; num Linux fora do WSL, sem caixa Executar, a `bash` é a única. As formas do Windows saem também no WSL, onde o
kit do porteiro roda: a chave e a âncora do titular ficam no Windows (comando_titular.shell_padrao), e a cópia protegida
do Windows é conferida por /mnt/c. `onde_rodar` cita só as formas presentes; o que falta vai em `<forma>_pendente`.

Item I13 da integração (os dois baixos da última reconferência do ABERTURAS): sem a cópia protegida do Ubuntu, o
`onde_rodar` começa pelo passo que falta, não pela caixa Executar (a janela abriria e fecharia sem mensagem); o Python
registrado no hashes.json do Windows só vale se esta conta não o altera (a sondagem da âncora) e se o SHA-256 dele
confere — um Python por usuário fica pendente —; e toda forma passa -S, para nenhum .pth de site-packages rodar antes
da ferramenta, que só usa a biblioteca padrão (-I não implica -S). Revisão da integração (defeitos 6 e 10): a cópia do
Ubuntu só conta à vista se ela e as pastas acima, até "/", são de root, sem ligação nem escrita de grupo ou de outros
(como a ferramenta exige ao rodar); sem as duas cópias, o passo diz que as formas do Ubuntu dependem só do preparo do
WSL e a do Windows, do preparar-maquina.ps1.
Limite honesto (§0): um processo hostil do mesmo usuário ainda pode interferir; a cerimônia protege contra arquivo
plantado, não contra isso. A biblioteca padrão do Python fixado (Lib\\) não é conferida por hash, só o python.exe e,
pela sondagem, a pasta dele.
"""

from __future__ import annotations

import hashlib
import os
import re
import stat
import subprocess
from pathlib import Path, PureWindowsPath

from .. import KIT_VERSION
from . import decisoes
from .aberturas_disco import ler_arquivo
from .aberturas_regras import carregar
from .comando_titular import _aspas_bash, _aspas_powershell, caminho_windows, caminho_wsl, em_wsl

# A cópia protegida da ferramenta do titular (mesma árvore da skill: assets/host/fundacao_titular.py e
# assets/fundacao-kit/fundacao/**, com o hashes.json do lado), instalada pelo preparo do titular.
FERRAMENTA_WINDOWS = r"C:\ProgramData\FundacaoIA\ferramentas"
FERRAMENTA_POSIX = "/usr/local/lib/fundacao-ia"
PYTHON_POSIX = "/usr/bin/python3"
OPCOES_DO_PYTHON = "-I -B -S"  # -S: nenhum .pth de site-packages roda antes da ferramenta (item I13 da integração)
REL_FERRAMENTA = ("assets", "host", "fundacao_titular.py")
ESQUEMA_HASHES = "fundacao.ferramenta_titular/1"
WINDOWS_VISTO_DO_WSL = r"C:\Windows"  # o WSL não herda SystemRoot: o critério de decisoes.SSH_KEYGEN_WINDOWS
CAIXA_EXECUTAR = 259  # caracteres que a caixa Executar aceita (MAX_PATH - 1; a conferir no ambiente real)
TETO_PYTHON = 64 << 20  # bytes do python.exe registrado (cerca de 100 KB): acima disto não é ele
_PYTHON_WINDOWS = re.compile(r"[A-Za-z]:\\(?:[^\\/:*?\"<>|`$'\r\n;&]+\\)*python\.exe", re.I)
_SHA256 = re.compile(r"[0-9a-f]{64}")
_DISTRO = re.compile(r"[A-Za-z0-9][A-Za-z0-9._-]*")  # WSL_DISTRO_NAME (emenda E1), sem cara de opção ('-x')
AVISO = (f"a forma é sempre esta: o Python fixado, a ferramenta na pasta protegida ({FERRAMENTA_WINDOWS} no Windows, "
         f"{FERRAMENTA_POSIX} no Ubuntu) e depois só raiz, projeto e versão; se a sessão mostrar outro caminho ou algo "
         "depois da versão (';', '|', 'iex', '&&'), não rode e avise o coordenador. ")
AVISO_WINDOWS = ("NÃO cole num PowerShell ou bash já aberto: um terminal novo também carrega o perfil ($PROFILE, "
                 "~/.bashrc), que a sessão pode ter gravado; só a caixa Executar (Win+R) evita o perfil, e as formas "
                 "powershell e bash ficam como último recurso, com esse risco.")
AVISO_LINUX = ("Neste sistema não há caixa Executar: o terminal carrega o perfil (~/.bashrc), que uma sessão sem "
               "sandbox pode ter gravado, e a forma bash fica com esse risco (limite registrado).")


def _alteravel(alvo: Path) -> list[str]:
    """O que esta conta consegue no arquivo `alvo` e no caminho dele, pela sondagem de decisoes.conferir_ancora: abri-lo
    para escrita, criar arquivo na pasta dele, ligação em algum ponto e, no Windows, os direitos de alterar, apagar ou
    renomear e de trocar permissões ou dono, do arquivo até a raiz do disco. Sem ler o arquivo como allowed_signers (o
    python.exe é binário, e a conferir_ancora levantaria ao decodificá-lo). Nada é alterado. Vazia: esta conta não o
    altera (item I13 da integração)."""
    abre, cria = decisoes._sondas_de_escrita(alvo)
    problemas = ([f"abrir {alvo} para escrita"] if abre else []) + ([f"criar arquivo em {alvo.parent}"] if cria else [])
    for posicao, item in enumerate((alvo, *alvo.parents)):
        if decisoes._e_ligacao(item):
            problemas.append(f"ligação no caminho: {item}")
        if os.name == "nt":
            pedidos = (decisoes._NO_ARQUIVO if posicao == 0 else decisoes._NA_PASTA_DA_ANCORA if posicao == 1
                       else decisoes._NAS_PASTAS_ACIMA)
            problemas += [f"{nome} em {item}" for nome, sim in decisoes._direitos_windows(item, pedidos).items() if sim]
    return problemas


def conferir_python(alvo: Path, sha256) -> str | None:
    """None quando esta conta não altera o Python registrado na cópia protegida (`_alteravel`, no caminho visto daqui:
    no WSL, por /mnt/c) e o SHA-256 dele é o do hashes.json, lido sem seguir ligação e com teto; senão, o problema
    (item I13 da integração: o Python por usuário, em AppData, grava-se por esta conta, e um .pth plantado em
    site-packages mostraria uma ficha e assinaria outra)."""
    if not (isinstance(sha256, str) and _SHA256.fullmatch(sha256)):
        return "não tem o SHA-256 registrado no hashes.json, na forma esperada"
    try:
        if not alvo.is_file():
            return "não existe neste computador"
        problemas = _alteravel(alvo)
        if problemas:
            return "pode ser alterado por esta conta (" + "; ".join(problemas[:4]) + ")"
        if hashlib.sha256(ler_arquivo(alvo, TETO_PYTHON)).hexdigest() != sha256:
            return "não confere com o SHA-256 registrado no hashes.json"
    except OSError as exc:
        return f"não foi conferido ({exc.__class__.__name__})"
    return None


def python_da_copia_windows(versao: str = KIT_VERSION) -> tuple[str | None, str]:
    """(o Python fixado, "") da cópia protegida da ferramenta do titular no Windows desta máquina, ou (None, o motivo).
    A cópia só vale se esta conta não consegue alterar o hashes.json, a pasta dele nem as de cima (a sondagem da âncora,
    decisoes.conferir_ancora): uma pasta criada por uma sessão sob C:\\ProgramData seria dela. O Python que ela registra
    também, e com o SHA-256 dele (conferir_python; item I13 da integração): o preparo do titular precisa de um Python
    instalado para todos os usuários. No WSL, a mesma cópia por /mnt/c, só com as sondas do POSIX (escrita e ligação):
    dono e direitos, a ferramenta confere ao rodar."""
    pasta, passo = PureWindowsPath(FERRAMENTA_WINDOWS, versao), "passo do titular, com UAC, no preparar-maquina.ps1"
    try:
        hashes = Path(str(pasta) if os.name == "nt" else caminho_wsl(pasta)) / "hashes.json"
        if not hashes.is_file():
            return None, f"a cópia protegida da ferramenta do titular ainda não foi instalada em {pasta} ({passo})"
        sondagem = decisoes.conferir_ancora(hashes)
        if not sondagem.get("protegida"):
            return None, f"a cópia em {pasta} não está protegida ({sondagem.get('motivo')}): refaça o {passo}"
        dados = carregar(ler_arquivo(hashes, 1 << 20))
    except (OSError, ValueError, subprocess.SubprocessError) as exc:
        return None, f"a cópia em {pasta} não foi conferida ({exc.__class__.__name__}): refaça o {passo}"
    registro = (dados.get("python") if isinstance(dados, dict) and dados.get("schema_version") == ESQUEMA_HASHES
                else None)
    python = registro.get("caminho") if isinstance(registro, dict) else None
    if not isinstance(python, str) or not _PYTHON_WINDOWS.fullmatch(python):
        return None, f"o hashes.json da cópia em {pasta} não registra o Python fixado na forma esperada ({passo})"
    problema = conferir_python(Path(python if os.name == "nt" else caminho_wsl(python)), registro.get("sha256"))
    if problema:
        return None, (f"o Python registrado na cópia ({python}) {problema}: o preparo do titular precisa de um Python "
                      f"instalado para todos os usuários ({passo})")
    return python, ""


def _executavel_do_sistema(*partes: str) -> str | None:
    """Caminho absoluto de um executável do Windows, da pasta de sistema lida do ambiente (SystemRoot/windir), nunca o
    nome nu, que CreateProcess buscaria na pasta atual (orientação do coordenador). Sem a variável: None no Windows e,
    no WSL (que não a herda; o porteiro passa `env -i`), o caminho fixo WINDOWS_VISTO_DO_WSL."""
    raiz = os.environ.get("SystemRoot") or os.environ.get("windir") or (WINDOWS_VISTO_DO_WSL if em_wsl() else None)
    return str(PureWindowsPath(raiz, "System32", *partes)) if raiz else None


def _aspas_run(valor: str) -> str | None:
    """Um argumento entre aspas duplas para a caixa Executar (Win+R) e o `wsl.exe -e`, que dividem a linha pela regra
    do Windows (aspa dupla, não a simples). None com aspa dupla, '%' (a caixa expande %VAR%), controle ou barra
    invertida no fim (que escaparia a aspa de fecho): quebrariam a divisão em argumentos."""
    return None if any(c in valor for c in '"%\r\n\0') or valor.endswith("\\") else f'"{valor}"'


def _na_caixa(out: dict, chave: str, exe: str, meio: str, ferramenta: str, alvo: str, resto: str) -> None:
    """A forma da caixa Executar em out[chave], cada caminho entre aspas duplas; se um caminho não passa inteiro ou o
    comando não cabe na caixa, o motivo em out[chave + "_pendente"]."""
    partes = [_aspas_run(valor) for valor in (exe, ferramenta, alvo)]
    comando = f"{partes[0]} {meio} {partes[1]}" + resto.format(partes[2]) if all(partes) else ""
    if comando and len(comando) <= CAIXA_EXECUTAR:
        out[chave] = comando
    else:
        out[chave + "_pendente"] = (f"o comando passaria de {CAIXA_EXECUTAR} caracteres, o limite da caixa Executar"
                                    if comando else "um caminho tem aspa dupla, '%', controle ou barra invertida no "
                                    "fim, que a caixa Executar não passa inteiros")


def _formas_do_windows(raiz, resto: str, out: dict) -> None:
    """`executar_windows` (caixa Executar: o python.exe direto) e `powershell` (último recurso), na cópia protegida do
    Windows; sem ela, ou sem caminho do Windows para a raiz, o motivo em `executar_windows_pendente`."""
    python, motivo = python_da_copia_windows()
    if not python:
        out["executar_windows_pendente"] = motivo + ": sem ela, a ficha não é assinada no Windows"
        return
    try:
        alvo = caminho_windows(raiz)
    except decisoes.DecisaoInvalida:
        out["executar_windows_pendente"] = "a raiz não tem caminho equivalente no Windows"
        return
    ferramenta = str(PureWindowsPath(FERRAMENTA_WINDOWS, KIT_VERSION, *REL_FERRAMENTA))
    out["powershell"] = (f"& {_aspas_powershell(python)} {OPCOES_DO_PYTHON} {_aspas_powershell(ferramenta)}"
                         + resto.format(_aspas_powershell(alvo)))
    _na_caixa(out, "executar_windows", python, OPCOES_DO_PYTHON, ferramenta, alvo, resto)


def _de_root(st: os.stat_result) -> bool:
    """Dono root e sem escrita de grupo nem de outros: a regra de porteiro._de_root e de
    fundacao_titular._problemas_de_dono_posix (revisão da integração, defeito 6)."""
    return st.st_uid == 0 and not st.st_mode & 0o022


def _pendencia_da_copia_posix(ferramenta: str) -> str | None:
    """None quando a cópia protegida do Ubuntu está à vista daqui e é de root: o arquivo da ferramenta é arquivo comum,
    e ele e cada pasta acima, até "/", não são ligação, são de root e não têm escrita de grupo nem de outros (lstat, sem
    seguir ligação: a regra que a ferramenta exige ao rodar, fundacao_titular.conferir_copia). Senão, o texto de
    `ubuntu_pendente`. Revisão da integração (defeito 6): só o arquivo existir não bastava — num Linux com /usr/local
    gravável pelo grupo, o kit indicaria uma cópia plantada, e a ferramenta plantada não se recusaria. Os hashes, a
    ferramenta confere ao rodar."""
    caminho, pasta = Path(ferramenta), f"{FERRAMENTA_POSIX}/{KIT_VERSION}"
    passo, problema = "passo do titular, com sudo, no preparo do WSL", None
    try:
        for posicao, item in enumerate((caminho, *caminho.parents)):
            st = os.lstat(item)
            if stat.S_ISLNK(st.st_mode):
                problema = f"ligação no caminho: {item}"
            elif posicao == 0 and not stat.S_ISREG(st.st_mode):
                problema = f"{item} não é arquivo comum"
            elif not _de_root(st):
                problema = f"{item} não é de root ou tem escrita de grupo ou de outros"
            if problema:
                break
    except FileNotFoundError:
        return (f"a cópia protegida da ferramenta do titular ainda não foi instalada em {pasta} ({passo}): as formas "
                "do Ubuntu só rodam depois dele")
    except OSError as exc:
        problema = f"não foi conferida: {exc.__class__.__name__}"
    if problema is None:
        return None
    return (f"a cópia da ferramenta do titular em {pasta} não está protegida ({problema}): refaça o {passo}; as formas "
            "do Ubuntu só rodam depois dele")


def _copia_posix_vista(ferramenta: str) -> bool:
    """A cópia protegida do Ubuntu está à vista daqui e é de root (_pendencia_da_copia_posix): é o que decide, no Linux,
    se o `onde_rodar` manda usar as formas do Ubuntu (item I13 da integração; revisão da integração, defeito 6)."""
    return _pendencia_da_copia_posix(ferramenta) is None


def _onde_rodar(out: dict, windows: bool) -> str:
    """O passo do titular, citando só as formas presentes em `out` (reconferência do pacote, 01/11/2026). Item I13 da
    integração: sem a cópia protegida do Ubuntu à vista (`ubuntu_pendente`), as formas do Ubuntu ficam na saída, para
    depois do preparo, mas o passo não manda colá-las e, sem outra forma pronta, começa pelo que falta; "a janela espera
    um Enter no fim" só da forma cuja cópia foi vista (a do Windows, conferida aqui; a do Ubuntu, só no Linux); na
    sessão do Windows, que não enxerga o Ubuntu, a forma do Ubuntu vem com a condição do preparo do WSL."""
    sem_ubuntu = "ubuntu_pendente" in out
    prontas = [c for c in ("executar_windows", "executar_ubuntu", "powershell", "bash")
               if c in out and not (sem_ubuntu and c in ("executar_ubuntu", "bash"))]
    caixa = [c for c in prontas if c.startswith("executar_")]
    ultimas = [c for c in prontas if not c.startswith("executar_")]
    so_depois = (f"só roda depois de o preparo do WSL (sudo) instalar a cópia protegida em {FERRAMENTA_POSIX}/"
                 f"{KIT_VERSION}; antes disso, a janela abre e fecha sem mensagem")
    if sem_ubuntu and not prontas:
        faltam = [out[c] for c in ("ubuntu_pendente", "executar_windows_pendente") if c in out]
        texto = "Ainda não dá para assinar por aqui: " + "; ".join(faltam) + ". "
        if len(faltam) == 1:
            texto += "As formas desta saída só rodam depois dele."
        else:  # revisão da integração (defeito 10): as do Ubuntu dependem só do preparo do WSL, não do passo do Windows
            do_ubuntu = " e ".join(c for c in ("executar_ubuntu", "bash") if c in out)
            texto += (f"As formas do Ubuntu desta saída ({do_ubuntu}) só rodam depois do preparo do WSL (sudo); a do "
                      "Windows " + ("aparece depois do preparar-maquina.ps1 (UAC)." if "preparar-maquina.ps1"
                                    in out["executar_windows_pendente"] else "não sai para esta raiz."))
    elif caixa:
        vista = caixa[0] == "executar_windows" or os.name != "nt"
        abre = (f"tecle Win+R (a caixa Executar), cole o texto de '{caixa[0]}' e tecle Enter. Ela abre o Python "
                "direto, sem PowerShell nem bash (logo sem o perfil deles), e " + ("a janela espera um Enter no fim."
                                                                                   if vista else so_depois + "."))
        if caixa[0] == "executar_ubuntu":
            texto = ("FORA do Claude. A forma do Windows, a da chave do titular criada pelo preparar-maquina.ps1, "
                     "ainda não está pronta; se a sua chave do titular estiver no Ubuntu, " + abre)
        elif len(caixa) == 2:
            texto = ("FORA do Claude: " + abre + " Ela usa a chave do titular no Windows; se a sua estiver no Ubuntu, "
                     "use 'executar_ubuntu'" + (", que " + so_depois if os.name == "nt" else "") + ".")
        else:
            texto = "FORA do Claude: " + abre + (" Ela usa a chave do titular no Windows; a forma do Ubuntu só roda "
                                                 "depois do passo que falta (o de 'ubuntu_pendente')." if sem_ubuntu
                                                 else "")
    elif ultimas and not windows:
        texto, ultimas = ("FORA do Claude, num terminal novo, cole o texto de 'bash' e tecle Enter (neste sistema não "
                          "há caixa Executar)."), []
    else:
        texto = "Nenhuma forma pela caixa Executar (Win+R) ficou pronta." if windows else "Nenhuma forma ficou pronta."
    if ultimas:
        texto += " Último recurso, com o risco do perfil: " + " ou ".join(f"'{c}'" for c in ultimas) + ", colado num " \
                 "terminal novo."
        if os.name == "nt" and "bash" in ultimas:  # a cópia do Ubuntu não é vista daqui (item I13)
            texto += " A 'bash' também só roda depois do preparo do WSL (sudo)."
    pendentes = sorted(c for c in out if c.endswith("_pendente"))
    return texto + (" O que falta: " + ", ".join(f"'{c}'" for c in pendentes) + "." if pendentes else "")


def comando_do_titular(raiz, projeto: str, versao: int) -> dict:
    """A forma FIXA do comando da ferramenta do titular, na cópia protegida (ver o módulo), só com raiz, projeto e
    versão: nada do rascunho entra nele. No Windows e no WSL: `executar_windows` e `executar_ubuntu` (caixa Executar;
    no WSL, com `-d <WSL_DISTRO_NAME>`), `powershell` e `bash` (último recurso); num Linux fora do WSL, só `bash`. Mais
    `onde_rodar` (só com as formas presentes), `aviso` e os `<forma>_pendente`. Toda forma chama o Python com
    OPCOES_DO_PYTHON (-I -B -S)."""
    if os.name == "nt":  # antes de python_da_copia_windows → decisoes.conferir_ancora: sem busca de exe na pasta
        os.environ["NoDefaultCurrentDirectoryInExePath"] = "1"  # atual (powershell/icacls plantados ali rodariam)
    windows, out = os.name == "nt" or em_wsl(), {}
    resto = f" assinar-ficha --raiz {{}} --projeto {projeto} --versao {int(versao)}"
    posix = "/".join((FERRAMENTA_POSIX, KIT_VERSION, *REL_FERRAMENTA))
    try:
        unix = None if any(c in str(raiz) for c in "\r\n\0") else caminho_wsl(raiz)
    except decisoes.DecisaoInvalida:
        unix = None
    if windows and unix:
        _formas_do_windows(raiz, resto, out)
        wsl = _executavel_do_sistema("wsl.exe")
        distro = os.environ.get("WSL_DISTRO_NAME", "") if os.name != "nt" else ""
        if wsl:  # Win+R para o Ubuntu: wsl.exe (caminho absoluto do sistema) -e python3 direto, sem bash nem ~/.bashrc
            meio = (f"-d {distro} " if _DISTRO.fullmatch(distro) else "") + f"-e {PYTHON_POSIX} {OPCOES_DO_PYTHON}"
            _na_caixa(out, "executar_ubuntu", wsl, meio, posix, unix, resto)
        else:
            out["executar_ubuntu_pendente"] = "SystemRoot ausente no ambiente: sem o caminho do wsl.exe do sistema"
    if unix:
        out["bash"] = f"{PYTHON_POSIX} {OPCOES_DO_PYTHON} {_aspas_bash(posix)}" + resto.format(_aspas_bash(unix))
        if os.name != "nt" and not _copia_posix_vista(posix):
            out["ubuntu_pendente"] = _pendencia_da_copia_posix(posix) or (
                f"a cópia da ferramenta do titular em {FERRAMENTA_POSIX}/{KIT_VERSION} não foi conferida (passo do "
                "titular, com sudo, no preparo do WSL): as formas do Ubuntu só rodam depois dele")
    out["onde_rodar"] = _onde_rodar(out, windows) if unix else ("Nenhuma forma ficou pronta: o caminho da raiz tem "
                                                               "quebra de linha ou NUL, ou não tem forma no Ubuntu.")
    out["aviso"] = AVISO + (AVISO_WINDOWS if windows else AVISO_LINUX)
    return out
