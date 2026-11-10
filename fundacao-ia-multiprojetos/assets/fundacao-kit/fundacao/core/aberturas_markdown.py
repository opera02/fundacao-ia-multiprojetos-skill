"""O conteúdo de cada Markdown de um plugin da ficha de aberturas (1.7.10; contratos do lote 2, §5; emendas E4 e E8;
integração, item I16). Saiu de core/aberturas_plugins.py pelo teto de 350 linhas: ele reexporta os nomes de sempre e
chama `conferir_markdown` para cada Markdown do plugin.

- Texto, em todo Markdown (também README, LICENSE e CHANGELOG da raiz): UTF-8; a marca U+FEFF (BOM) só no começo, onde
  é tirada antes do cabeçalho, como a leitura do cabeçalho do Claude Code 2.1.302 faz; fora do começo ela é caractere
  invisível e recusa (emenda E8); sem controle, direção, CR sozinho, U+2028 nem U+2029, que esconderiam linhas de um
  leitor que só quebra no LF, e sem contexto dinâmico (`` !`comando` `` e cerca de crases ou tils seguida de `!`, em
  qualquer ponto), que roda um comando quando a skill ou o comando carrega (emenda E4).
- Cabeçalho, nos Markdown de skills/, agents/ e commands/ (também os de apoio): só as chaves de primeiro nível da lista
  positiva do tipo (CHAVES_DO_FRONTMATTER, conferida na documentação do Claude Code em 31/10/2026:
  code.claude.com/docs/en/skills e /sub-agents); `hooks` e `mcpServers` em qualquer nível, num valor ou numa chave
  recuada, e recurso de YAML que monta uma chave por escape, etiqueta, âncora, alias, mesclagem ou chave complexa:
  recusa "1.7.11".
- Skill e comando (todo SKILL.md de skills/ e todo Markdown de commands/, também em subpasta: o que o Claude Code
  invoca), as regras do scripts/plugin_candidato.py trazidas para o caminho confiável (integração, item I16: a sessão
  controla a pasta do candidato até a assinatura, e o REVISAO.md e o `conferir` da sessão não bastam; o
  plugin_candidato usa estas mesmas funções): `allowed-tools` só com a lista positiva (FERRAMENTAS_DO_CABECALHO); Bash,
  PowerShell, Monitor, WebFetch, WebSearch e MCP (SO_PELA_FICHA) recusam, com a mensagem de que só abrem pela ficha; o
  valor fora do formato simples e o especificador entre parênteses com caminho para fora (também `..` sozinho, como em
  `Read(..)`, e '$' em qualquer ponto) recusam; e a menção `@` para fora do plugin (absoluto, '~', letra de unidade,
  `file:`, '..', '$' em qualquer ponto), colhida como o Claude Code 2.1.302 a colhe, com as duas varreduras
  independentes dele (a forma entre aspas duplas, que cruza quebra de linha, e cada trecho sem espaço que começa com
  '@'), mais a varredura larga de antes (REFERENCIA): uma '@' dentro de um trecho entre aspas não fica escondida
  (revisão da integração, rodada 2). Limite da regra, que só lê o arquivo: o argumento preenchido na invocação
  ($ARGUMENTS) pode trazer uma menção inteira, que o Claude Code colhe do texto já expandido; ali vale a negação de
  leitura do perfil (reconferência da integração, rodada 2).
- A licença da raiz que não é Markdown (LICENSE, LICENSE.txt): texto UTF-8, sem controle, direção, CR sozinho, U+2028
  nem U+2029 (`conferir_texto`; a regra do plugin_candidato), o que recusa também a mágica binária de um binfmt.
"""

from __future__ import annotations

import re

from .aberturas_regras import mostrar

# Chaves de primeiro nível aceitas no frontmatter. Ficam de fora: das skills, hooks, context e agent (subagente fora da
# ficha), background e shell; dos comandos, também name e paths (que a documentação não aceita neles); dos agentes,
# permissionMode, mcpServers, hooks e initialPrompt (o Claude Code os ignora em plugin, mas não numa cópia em
# .claude/agents/), skills, memory, background, isolation, experimental e omitClaudeMd (sem o CLAUDE.md, o subagente
# perderia as regras do projeto).
_DE_SKILL = ("description", "when_to_use", "argument-hint", "arguments", "disable-model-invocation", "user-invocable",
             "allowed-tools", "disallowed-tools", "model", "effort", "metadata", "license", "compatibility")
CHAVES_DO_FRONTMATTER = {
    "skills": frozenset(_DE_SKILL + ("name", "paths")),
    "commands": frozenset(_DE_SKILL),
    "agents": frozenset({"name", "description", "tools", "disallowedTools", "model", "effort", "color", "maxTurns"})}
_PROIBIDAS_NO_FRONTMATTER = re.compile(r"(?i)\b(?:hooks|mcpservers|mcp_servers|mcp-servers)\b")
_YAML_NAO_CONFERIDO = re.compile(r"\\|<<|^\s*\?(?:\s|$)|(?:^\s*|:\s+|-\s+|[\[{,]\s*)[!&*]", re.M)
_CHAVE_DE_PRIMEIRO_NIVEL = re.compile(r"([A-Za-z][A-Za-z0-9_-]*):(?:[ \t].*)?")
# Execução de shell embutida, como o Claude Code 2.1.302 a lê (emenda E4 dos contratos; igual ao SHELL_EMBUTIDO do
# scripts/plugin_candidato.py): `!`comando`` e cerca de crases ou tils seguida de `!`, em QUALQUER ponto (sem âncora;
# o 2.1.302 roda /```!\s*\n?.../g e /(?<=^|\s)!`.../gm). A cerca só casa onde a sequência começa (o lookbehind), para
# uma linha longa de crases não ser varrida a cada posição (tempo quadrático num arquivo de 1 MiB).
_CONTEXTO_DINAMICO = re.compile(r"!`|(?<!`)`{3,}[ \t]*!|(?<!~)~{3,}[ \t]*!")
# Controle e direção: o CONTROLE do scripts/plugin_candidato.py (emenda E4; reconferência do pacote, 01/11/2026). Pega
# também o FF, o VT, o NEL e os separadores FS, GS e RS, em que str.splitlines (e um YAML) quebra a linha: um FF antes
# de '---' fecharia o cabeçalho aqui e esconderia o resto. Ficam de fora o tab, o LF e o CR (o do CRLF; o CR sozinho é
# o _QUEBRA_ESCONDIDA, abaixo).
_CONTROLE = re.compile("[\x00-\x08\x0b\x0c\x0e-\x1f\x7f-\x9f\U0000202a-\U0000202e\U00002066-\U00002069"
                       "\U000e0000-\U000e007f]")
# CR sozinho e os separadores de linha do Unicode (emenda E4): o YAML 1.2 lê o CR sozinho como quebra, e o 1.1 lê
# também U+2028 e U+2029; o Claude Code passa o bloco cru ao analisador de YAML. Uma chave depois deles ficaria
# escondida de um leitor que só quebra no LF, então recusamos.
_QUEBRA_ESCONDIDA = re.compile(r"\r(?!\n)|[\u2028\u2029]")
BOM = "\ufeff"  # emenda E8: tirado só no começo; em qualquer outro ponto, recusa
TETO_PY = 512 * 1024  # o script da ficha (conferir_python)
_CODIFICACAO = re.compile(r"[ \t\f]*#.*?coding[:=][ \t]*([-_.a-zA-Z0-9]+)")  # PEP 263, nas duas primeiras linhas
# allowed-tools (integração, item I16; a lista positiva do scripts/plugin_candidato.py, crítica do desenho e revisão do
# pacote PLUGINS): só o que lê, grava no projeto (as negações do perfil continuam valendo: uma regra de permissão não
# abre exceção numa negação) ou delega a outra skill ou agente. Bash, PowerShell, Monitor, WebFetch, WebSearch e MCP só
# abrem pela ficha (e pelo perfil gerado dela); o resto (RemoteTrigger, CronCreate, SendMessage...) também recusa.
FERRAMENTAS_DO_CABECALHO = frozenset({"Read", "Grep", "Glob", "Write", "Edit", "MultiEdit", "NotebookEdit", "TodoWrite",
                                      "Task", "Agent", "Skill"})
SO_PELA_FICHA = ("bash", "powershell", "pwsh", "shell", "killshell", "killbash", "monitor", "webfetch", "websearch")
# Menção de arquivo com '@', varredura larga: entre aspas (`@"caminho com espaço"`, que cruza quebra de linha) ou o
# token inteiro até o próximo espaço (reconferência do pacote PLUGINS: parar em `,;)'` deixava `@x,/../../outro`
# passar, e o Claude Code o resolve para fora do projeto). Sozinha ela não basta: o trecho entre aspas consome a menção
# de dentro (`@"guia.md @/etc/passwd "`), que o Claude Code lê (revisão da integração, rodada 2); por isso as duas
# varreduras dele, abaixo, rodam à parte. A varredura é linear: a forma entre aspas para na aspa seguinte, que a próxima
# menção entre aspas sempre traz.
REFERENCIA = re.compile(r"(?<![\w.@/\\-])@(?:\"([^\"]+)\"|'([^']+)'|(\S+))")
# A leitura das menções no Claude Code 2.1.302 (lida no binário em 01/11/2026: as funções yJr e KIn), com duas
# varreduras independentes: (1) a forma entre aspas duplas, `(^|[\s。、？！])@"([^"]+)"`, que cruza quebra de linha; (2)
# cada trecho sem espaço (`[^\s]+`), com a primeira '@' do começo dele ou logo depois de 。、？！, até o fim do trecho
# sem os caracteres do fim que não são [0-9A-Za-z_]. Aspas simples não têm tratamento lá. O \s é o do JavaScript
# (_ESPACO_JS: com o U+FEFF; sem o FS, o GS, o RS, o US e o NEL, que o \s do Python tem).
_ESPACO_JS = ("\t\n\x0b\x0c\r \xa0\U00001680\U00002000-\U0000200a\U00002028\U00002029"
              "\U0000202f\U0000205f\U00003000\U0000feff")
_DEPOIS_DE = "\U00003002\U00003001\U0000ff1f\U0000ff01"  # os de FAe no 2.1.302
_ENTRE_ASPAS = re.compile(f'(?<![^{_ESPACO_JS}{_DEPOIS_DE}])@"([^"]+)"')
_TRECHO = re.compile(f"[^{_ESPACO_JS}]+")
_FIM_SEM_PALAVRA = re.compile(r"[^0-9A-Za-z_]*")  # casado no trecho invertido: linear
_FORA_NO_COMECO = re.compile(r"[/\\~%]|[A-Za-z]:|(?i:file:)")  # o '$' conta em qualquer ponto (de_fora)
_SEPARADOR = re.compile(r"[\\/#]")  # o '#' também: o Claude Code tira o `#L10-20` do fim antes de abrir o arquivo
_ESPECIFICADOR = re.compile(r"\(([^()]*)\)")


def ferramentas_do_valor(valor: str) -> list | None:
    """Os nomes de ferramenta de `allowed-tools` (lista YAML, entre colchetes ou separada por vírgula ou espaço), sem
    o que vem entre parênteses; None quando o valor foge desse formato (curinga, escape, âncora, mapa ou bloco)."""
    nomes, atual, profundidade = [], "", 0
    for c in valor:
        if profundidade:
            if c in "\\\r\n":
                return None
            profundidade += {"(": 1, ")": -1}.get(c, 0)
        elif c.isascii() and (c.isalnum() or c == "_"):
            atual += c
        else:
            if atual:
                nomes.append(atual)
                atual = ""
            if c == "(":
                if not nomes:
                    return None
                profundidade = 1
            elif c not in " \t\r\n,[]'\"-":
                return None
    if profundidade:
        return None
    return nomes + ([atual] if atual else [])


def so_pela_ficha(ferramenta: str) -> bool:
    dobrado = ferramenta.casefold()
    return dobrado.startswith(SO_PELA_FICHA) or "mcp" in dobrado


def de_fora(alvo: str) -> bool:
    """O alvo de uma menção '@' (ou o especificador de uma regra de allowed-tools) aponta para fora do plugin: absoluto,
    '~', letra de unidade (também a relativa do Windows, `C:x`), `file:`, um componente '..' (o '#' também separa) ou
    '$' em qualquer ponto. Vale para o alvo inteiro e para ele sem a pontuação de prosa do fim: antes só a segunda forma
    contava, e o '..' do fim saía com a pontuação (`Read(..)`, `Edit(./..)` e `@".."` passavam; revisão da integração,
    rodada 2). O '$': o Claude Code 2.1.302 troca os argumentos ($ARGUMENTS, $1, $ARGUMENTS[0], $nome) e as variáveis
    (${CLAUDE_PLUGIN_ROOT}, ${CLAUDE_PROJECT_DIR}, ${CLAUDE_PLUGIN_DATA}, ${CLAUDE_SKILL_DIR}) antes de colher as
    menções, e o mesmo no allowed-tools; só o '$' do começo contava, e `@..${CLAUDE_PROJECT_DIR}`, `@docs/$1` e
    `Read(..${CLAUDE_PLUGIN_ROOT}/**)` passavam (reconferência da integração, rodada 2)."""
    bruto = alvo.strip()
    return "$" in bruto or any(_FORA_NO_COMECO.match(forma) is not None or ".." in _SEPARADOR.split(forma)
                               for forma in (bruto, bruto.rstrip(".,:;!?")))


def _alvos(texto: str) -> set:
    """Os alvos das menções '@' do texto: as duas varreduras do Claude Code 2.1.302, cada uma à parte (a forma entre
    aspas; e, de cada trecho sem espaço, o alvo exato dele e o mesmo sem as aspas do começo, que o Claude Code descarta
    quando a primeira é dupla), e a varredura larga (REFERENCIA). Tudo linear no tamanho do texto."""
    if "@" not in texto:
        return set()
    alvos = {m.group(1) for m in _ENTRE_ASPAS.finditer(texto)}
    alvos.update(next(g for g in m.groups() if g is not None) for m in REFERENCIA.finditer(texto))
    for m in _TRECHO.finditer(texto):
        trecho = m.group(0)
        h = trecho.find("@")
        while h > 0 and trecho[h - 1] not in _DEPOIS_DE:
            h = trecho.find("@", h + 1)
        if h != -1:
            resto = trecho[h + 1:]
            alvos.update((resto[:len(resto) - _FIM_SEM_PALAVRA.match(resto[::-1]).end()], resto.lstrip("\"'")))
    return alvos


def referencias_de_fora(texto: str) -> list:
    """Os alvos das menções '@' do texto (`_alvos`) que apontam para fora do plugin, ordenados."""
    return sorted(alvo for alvo in _alvos(texto) if de_fora(alvo))


def problemas_do_allowed_tools(valor: str) -> list[str]:
    """Por que o valor de `allowed-tools` (o da linha da chave e as linhas recuadas dela) recusa; vazio se aceito. É a
    regra do scripts/plugin_candidato.py (integração, item I16), com as mesmas mensagens."""
    motivos, ferramentas = [], ferramentas_do_valor(valor)
    if ferramentas is None:
        motivos.append("allowed-tools fora do formato simples (curinga fora de parênteses, escape, âncora ou bloco)")
        ferramentas = []
    if abre := sorted({f for f in ferramentas if so_pela_ficha(f)}):
        motivos.append(f"allowed-tools concede {', '.join(abre)}: o cabeçalho de uma skill ou comando não pré-aprova "
                       "ferramenta que roda comando ou abre rede (a ferramenta só abre pela ficha de aberturas do "
                       "projeto e pelo perfil gerado dela; MCP, só na 1.7.11)")
    if fora := sorted({f for f in ferramentas if not so_pela_ficha(f) and f not in FERRAMENTAS_DO_CABECALHO}):
        motivos.append(f"allowed-tools pré-aprova {', '.join(fora)}, fora da lista do cabeçalho (só "
                       f"{', '.join(sorted(FERRAMENTAS_DO_CABECALHO))}): o resto não abre pelo cabeçalho")
    # Read(//**), Edit(~/.bashrc): a regra pré-aprovaria, sem perguntar, leitura ou escrita fora do projeto
    if fora_da_area := sorted({e for e in _ESPECIFICADOR.findall(valor) if de_fora(e)}):
        motivos.append(f"allowed-tools com caminho para fora do projeto ({', '.join(fora_da_area[:3])}): a regra "
                       "pré-aprovaria leitura ou escrita sem perguntar")
    return motivos


def de_componente(partes: tuple) -> bool:
    """Skill ou comando: o SKILL.md de skills/ (em qualquer nível) e todo Markdown de commands/ (também em subpasta,
    que o Claude Code lê com prefixo): os que o Claude Code invoca, com o allowed-tools e as menções '@'. Agentes e o
    Markdown de apoio, não (como no plugin_candidato)."""
    nome = partes[-1].casefold()
    return len(partes) > 1 and ((partes[0] == "skills" and nome == "skill.md")
                                or (partes[0] == "commands" and nome.endswith(".md")))


def _chaves_fora_da_lista(corpo: list[str], permitidas: frozenset) -> list[str]:
    """As chaves de primeiro nível (linha na coluna 0, `chave:`) fora de `permitidas`, e as linhas que não são chave,
    comentário nem continuação recuada. A primeira linha com conteúdo recuada (mapeamento todo recuado) também conta."""
    fora, inicio = [], True
    for linha in corpo:
        if not linha.strip() or linha.lstrip().startswith("#"):
            continue
        if linha[0] in " \t":
            if inicio:
                fora.append("(frontmatter recuado)")
            inicio = False
            continue
        inicio = False
        achada = _CHAVE_DE_PRIMEIRO_NIVEL.fullmatch(linha)
        if achada is None:
            fora.append(mostrar(linha[:30]))
        elif achada.group(1) not in permitidas:
            fora.append(achada.group(1))
    return fora


def _valores_da_chave(corpo: list[str], chave: str) -> list[str]:
    """Cada valor de `chave` no cabeçalho, lido como o plugin_candidato.cabecalho lê: o resto da linha da chave e as
    linhas seguintes recuadas ou com '-' (o comentário e a linha vazia não encerram a chave; '---' e '...' encerram);
    todas as ocorrências (uma chave repetida não esconde a segunda)."""
    valores, atual = [], None
    for linha in corpo:
        if linha.startswith(("---", "...")):
            atual = None
        elif linha[:1] in (" ", "\t", "-"):
            if atual is not None:
                atual.append(linha)
        elif not linha.startswith("#") and linha.strip():
            achada = _CHAVE_DE_PRIMEIRO_NIVEL.fullmatch(linha)
            atual = [linha[len(chave) + 1:]] if achada and achada.group(1) == chave else None
            if atual is not None:
                valores.append(atual)
    return ["\n".join(v) for v in valores]


def _conteudo(rel: str, dados: bytes, erro) -> str | None:
    """O texto de um Markdown do plugin, sem o BOM do começo, ou None se recusado (ver o módulo)."""
    try:
        texto = dados.decode("utf-8").removeprefix(BOM)
    except UnicodeDecodeError:
        erro(rel, "Markdown fora do UTF-8")
        return None
    if _CONTEXTO_DINAMICO.search(texto):
        erro(rel, "contexto dinâmico (!`comando` ou cerca de crases/tils seguida de !): roda um comando quando a skill "
                  "ou o comando carrega, sem pedido do modelo: só na 1.7.11", "1.7.11")
    if _CONTROLE.search(texto) or _QUEBRA_ESCONDIDA.search(texto):
        erro(rel, "caractere de controle ou de direção, CR sozinho, U+2028 ou U+2029 no Markdown do plugin: o YAML do "
                  "Claude Code veria linhas que esta conferência não vê (use LF ou CRLF): só na 1.7.11", "1.7.11")
        return None
    if BOM in texto:
        erro(rel, "U+FEFF (BOM) fora do começo do Markdown: caractere invisível que esconde texto do titular (só no "
                  "começo ele é tirado, como o Claude Code faz ao ler o cabeçalho)")
        return None
    return texto


def conferir_texto(rel: str, dados: bytes, erro) -> None:
    """A licença da raiz que não é Markdown (LICENSE, LICENSE.txt): texto UTF-8 (o BOM do começo sai), sem controle,
    direção, CR sozinho, U+2028 nem U+2029, a regra do scripts/plugin_candidato.py para ela (revisão da integração,
    rodada 2: o kit não a lia, e, num DrvFs sem a opção metadata, um LICENSE com a mágica binária de um binfmt do WSL,
    como a do python3.12, passava)."""
    try:
        texto = dados.decode("utf-8").removeprefix(BOM)
    except UnicodeDecodeError:
        erro(rel, "a licença da raiz não é texto UTF-8")
        return
    if _CONTROLE.search(texto) or _QUEBRA_ESCONDIDA.search(texto):
        erro(rel, "caractere de controle ou de direção, CR sozinho, U+2028 ou U+2029 na licença da raiz: pode esconder "
                  "texto do titular (use LF ou CRLF)")


def conferir_python(rel: str, dados: bytes, erro) -> None:
    """O `.py` que a ficha lista (`skills_com_scripts`, 1.7.11, lote S1): até TETO_PY bytes, UTF-8 (o BOM só no começo),
    sem controle, direção, CR sozinho, U+2028 nem U+2029, as regras do Markdown, e sem `#!` (o executor chama o
    interpretador), ELF ou MZ. Declaração de codificação (PEP 263) só utf-8: outra faria o interpretador ler texto
    diferente do conferido."""
    if len(dados) > TETO_PY:
        return erro(rel, f"script acima de {TETO_PY} bytes")
    try:
        texto = dados.decode("utf-8").removeprefix(BOM)
    except UnicodeDecodeError:
        return erro(rel, "script fora do UTF-8")
    if texto.startswith("#!"):
        erro(rel, "tire a primeira linha #!: o executor chama o interpretador", "1.7.11")
    elif dados.startswith((b"\x7fELF", b"MZ")):
        erro(rel, "script que começa como binário executável (ELF ou MZ)", "1.7.11")
    if _CONTROLE.search(texto) or _QUEBRA_ESCONDIDA.search(texto) or BOM in texto:
        erro(rel, "caractere de controle ou de direção, CR sozinho, U+2028, U+2029 ou U+FEFF fora do começo no script: "
                  "esconderia código de quem o lê")
    for linha in texto.split("\n", 2)[:2]:
        achada = _CODIFICACAO.match(linha)
        if achada and achada.group(1).casefold().replace("_", "-") not in ("utf-8", "utf8"):
            erro(rel, f"declaração de codificação {achada.group(1)!r}: só utf-8")


def _frontmatter(partes: tuple, texto: str, erro) -> None:
    """O frontmatter de um Markdown de skills/, agents/ ou commands/, já aceito por _conteudo: chave fora da lista
    positiva do tipo, `hooks`/`mcpServers` em qualquer nível e recurso de YAML que monta uma chave por escape, etiqueta,
    âncora, mesclagem ou chave complexa; numa skill ou num comando, o valor de allowed-tools (item I16). Ele abre na
    primeira linha com conteúdo, no começo dela (sem recuo), que seja só `---` (`---yaml` e `  ---` recusam) e fecha SÓ
    numa linha cujo começo é `---` com, no máximo, espaço ou tab no fim (o `...` do YAML e um `---` recuado não encerram
    a conferência); sem fechamento, recusa. O Claude Code 2.1.302, no hi com o Lk, fecha no primeiro `---` em qualquer
    ponto (recuado ou no meio da linha); o cabeçalho que o kit confere vai até a primeira linha `---` e contém o dele:
    mais estrito (reconferência da integração, rodada 2: o texto de antes dizia "leitor ancorado")."""
    rel, tipo = "/".join(partes), partes[0]
    linhas = texto.splitlines()  # recusados antes controle, CR sozinho, LS e PS: aqui só o LF e o CRLF quebram
    inicio = next((i for i, linha in enumerate(linhas) if linha.strip()), None)
    if inicio is None or not linhas[inicio].startswith("---"):
        return
    fim = next((i for i in range(inicio + 1, len(linhas)) if linhas[i].rstrip(" \t") == "---"), None)
    if linhas[inicio].rstrip(" \t") != "---" or fim is None:
        erro(rel, "frontmatter fora da forma conferida (só '---' na abertura, no começo da linha, e uma linha '---' "
                  "que o fecha, com espaço ou tab no fim no máximo): só na 1.7.11", "1.7.11")
        return
    corpo = linhas[inicio + 1:fim]
    juntos = "\n".join(corpo)
    if _PROIBIDAS_NO_FRONTMATTER.search(juntos) or _YAML_NAO_CONFERIDO.search(juntos):
        erro(rel, "frontmatter com hooks ou mcpServers (rodam fora do sandbox) ou com recurso de YAML que a 1.7.10 não "
                  "confere (barra invertida, etiqueta, âncora, mesclagem, chave complexa): só na 1.7.11", "1.7.11")
    fora = _chaves_fora_da_lista(corpo, CHAVES_DO_FRONTMATTER[tipo])
    if fora:
        erro(rel, f"frontmatter com campo fora da lista aceita na 1.7.10 para {tipo} ({', '.join(fora[:8])}): só na "
                  "1.7.11", "1.7.11")
    if de_componente(partes):
        for valor in _valores_da_chave(corpo, "allowed-tools"):
            for motivo in problemas_do_allowed_tools(valor):
                erro(rel, motivo)


def conferir_markdown(partes: tuple, dados: bytes, erro) -> None:
    """Um Markdown do plugin (`partes`: o caminho dentro do plugin): o texto em todos; o cabeçalho fora da raiz; na
    skill e no comando, também a menção '@' para fora. Cada problema vai para `erro(rel, motivo, versao=None)`."""
    rel = "/".join(partes)
    texto = _conteudo(rel, dados, erro)
    if texto is None:
        return
    if len(partes) > 1:
        _frontmatter(partes, texto, erro)
    if de_componente(partes) and (fora := referencias_de_fora(texto)):
        erro(rel, f"referência de arquivo com @ para fora do plugin ({', '.join(fora[:3])}): o Claude Code a lê ao "
                  "invocar")
