# Matriz de hosts, validadores e verificações — skill 1.4.3

Data: 19/10/2026. Responde aos itens F20, O2 e O4 da auditoria externa da 1.3.4
(`auditoria/RELATORIO-AUDITORIA-EXTERNA-1.3.4.md`), ao PRM-02 do relatório técnico sobre a 1.4.0
(`auditoria/VERIFICACAO-RELATORIO-TECNICO-1.4.0.md`), ao ING-01, SEC-02 e OPS-01 da auditoria sobre a 1.4.1
(`auditoria/VERIFICACAO-AUDITORIA-1.4.1.md`) e aos AF-02 a AF-05 e AF-08 da auditoria final da 1.4.2
(`auditoria/AUDITORIA-FINAL-1.4.2.md`). Só entra como "executado" o que rodou nesta sessão ou na da
auditoria final, com o registro indicado; o resto fica marcado como não testado, com o motivo.

## 1. Validadores e empacotador (F20)

| Ferramenta | Onde | Hash | Resultado sobre a 1.4.3 (árvore e pacote extraído) | Situação |
|---|---|---|---|---|
| Especificação Agent Skills (S1) | agentskills.io/specification | — | `compatibility` aceito na raiz (até 500 caracteres) ou como texto em `metadata`; desde a 1.4.1, está em `metadata` (436 caracteres na 1.4.3); descrição com 852 de 1.024; nome com 25 de 64; `license` na raiz como texto (MIT, apontando para `LICENSE.txt`) | referência normativa |
| skill-creator `anthropic-skills` (aplicativo; usado no empacotamento) | `%APPDATA%\Claude\local-agent-mode-sessions\skills-plugin\…\skills\skill-creator` | `quick_validate.py` f6531597…e01892 · `package_skill.py` 1a33059b…8d1c0f | **Skill is valid!** (código 0) na árvore e no pacote 1.4.3 (`auditoria-final-1.4.2/execucoes/21-…`, `24-…`) | executado |
| skill-creator do plugin oficial (versão ativa `ea10b213686c`) | `~\.claude\plugins\cache\claude-plugins-official\skill-creator\ea10b213686c\…` | `quick_validate.py` 67cf5703…5fde365 · `package_skill.py` igual ao de cima | **Skill is valid!** (código 0) na árvore e no pacote 1.4.3 | executado |
| skill-creator variante Work (da sessão do auditor) | não disponível aqui | — | na 1.4.0, recusou `compatibility` como chave inesperada e listou as permitidas: `allowed-tools`, `description`, `license`, `metadata` e `name` (registro do auditor, `audit/results/creator_validation.log`). Desde a 1.4.1, as chaves da raiz estão nessa lista (conferência da regra no CEN-11 e no pacote extraído da 1.4.3) | **não executado** aqui |

**Decisão registrada (1.4.1, 19/10/2026):** o titular vai usar a skill no Chat/Work. Por isso,
`compatibility` saiu da raiz e foi para `metadata.compatibility`, com o conteúdo atualizado. A
especificação aceita o texto nos dois lugares (`metadata` é um mapa de textos); a lista do validador
Work só aceita o segundo; o Claude Code não usa o campo. `license` continua na raiz, porque a mesma
lista o aceita. Há um único perfil para todos os destinos, e o CEN-11 confere o cabeçalho contra essa
lista. Na 1.4.0, a decisão tinha sido manter o campo na raiz, porque nenhum destino exigia a mudança.
O carregamento no catálogo do Chat/Work continua **não testado**. O empacotador da entrega (`empacotar.py`) exige
`scripts/package_skill.py` e grava em `dist/EMPACOTAMENTO.json` o caminho e o hash da ferramenta
usada, para que a variante fique identificada em cada pacote.

## 2. Hosts e formas de instalação (O2)

| Destino | Como instala | Situação na 1.4.3 | Prova necessária |
|---|---|---|---|
| Pacote Agent Skills (`.skill`) | arquivo zip com a pasta na raiz, sem `evals/` | gerado e conferido (estrutura, hashes; 123 arquivos, com `LICENSE.txt`) | — |
| Claude Code (local) | `entrega/instalar_skill.py instalar|atualizar` → `~/.agents/skills/…` + junção em `~/.claude/skills/…` | **1.4.2 instalada** em 19/10, 18h29, com o OK do titular (a 1.4.0 às 10h35 e a 1.4.1 às 11h51): `atualizar --sha256` com o hash do pacote conferido antes de extrair e troca por renomeação; `verificar --origem` com 121 arquivos, 0 divergências, junção válida e integridade conferida; skill listada pelo host; carregamento num pedido real **não** testado. **1.4.3 instalada** em 19/10, 20h05, com o OK do titular (`atualizar --sha256`; 123 arquivos, 0 divergências, junção válida; a 1.4.2 guardada em `skills-anteriores` e conferida); carregamento num pedido real **não** testado | ver a skill carregada pelo host num pedido real |
| Codex (local) | mesma cópia em `~/.agents/skills/` | **projetado, não testado** (nenhuma sessão Codex rodou a skill) | sessão Codex que liste e invoque a skill |
| Chat/Work (catálogo do aplicativo) | no claude.ai: Customize > Skills, "+", "Create skill", "Upload a skill", com um ZIP da pasta; exige a execução de código ligada (central de ajuda, conferida em 19/10/2026: https://support.claude.com/en/articles/12512180-using-skills-in-claude) | **não testado**. Desde a 1.4.1, o cabeçalho tem na raiz só chaves da lista do validador Work (conferência da regra, não o validador). O arquivo de envio é `transferencia/fundacao-ia-multiprojetos-1.4.3-para-claude-ai.zip`, o mesmo `.skill` com extensão `.zip`. Arquivos em `~/.agents` e `~/.claude` não provam instalação nesse catálogo | enviar no claude.ai e ver a skill listada e usada |
| `agents/openai.yaml` (apresentação no Codex) | opcional (skill-creator) | **não acrescentado**: Codex ainda não foi testado; é apresentação, não requisito do padrão | decidir junto com o primeiro teste em Codex |

## 3. Requisitos por peça (O2, F17)

| Peça | Requisito | Conferência |
|---|---|---|
| Núcleo do kit e scripts da skill | Python 3.10+ (biblioteca padrão), SQLite com FTS5 | suíte rodada só em 3.12.10 (Windows); 3.10/3.11 **não** rodados |
| Instalador da skill (`entrega/instalar_skill.py`) | Python 3.10+, pré-verificado antes de qualquer alteração; junção reconhecida também sem `os.path.isjunction` | ciclo completo com junção real no 3.12; ausência da API do 3.10/3.11 **simulada**; versão < 3.10 recusada (simulada). Na 1.4.2: hash do pacote conferido antes de extrair (`--sha256` e `SHA256SUMS.txt` ao lado), instalação e atualização com retorno e falha injetada no meio da cópia, todos em perfil descartável no 3.12 (`testes/test_auditoria_1_4_1.py`). Na 1.4.3: troca por duas renomeações com marca — exceção na troca sem sobras, queda entre as renomeações concluída pelo próximo comando, `remover` limpando a área de preparo —, `name` do cabeçalho conferido e ligação alheia mantida (`testes/test_auditoria_final_1_4_2.py`) |
| Servidor MCP do kit | SDK `mcp` 2.x (que exige Python 3.11+) | `mcp` 2.3.0 presente aqui: teste em processo (SDK real) e CEN-15 por stdio; registro no host **não** testado |
| CAG real | `torch`, `transformers` e modelo local autorizado | `torch` 2.12.0 e `transformers` 5.10.2 presentes, mas **nenhum modelo autorizado**: CAG real não rodado (CEN-10 usa modelo sintético, só o mecanismo) |
| Validação e avaliações | PyYAML (só nas ferramentas de avaliação) | PyYAML 6.0.3 presente |

## 4. Matriz de execução por risco e versão (O4)

Ambiente desta sessão: Windows 11 Home 10.0.26200, Python 3.12.10, SQLite 3.49.1 (FTS5), sem modo de
desenvolvedor (link simbólico indisponível; junção disponível). Registros em
`fundacao-ia-multiprojetos-workspace/auditoria-externa-1.3.4/execucoes/` (1.4.0) e em
`fundacao-ia-multiprojetos-workspace/auditoria-final-1.4.2/execucoes/` (1.4.2 reproduzida e 1.4.3).

| Verificação | Windows · 3.12 | Windows · 3.10/3.11 | Linux · 3.12 | Linux · 3.10/3.11 |
|---|---|---|---|---|
| Suíte do kit (166 testes) | **executado** (3 pulados: link simbólico de arquivo) | não executado | não executado nesta versão (o auditor rodou a 1.3.4 em Linux 3.12.14) | não executado |
| Regressões das auditorias (vermelho na versão anterior, verde na seguinte) | **executado** (1.3.4→1.4.0, 1.4.0→1.4.1, 1.4.1→1.4.2, 1.4.2→1.4.3) | não executado | não executado | não executado |
| Testes dos scripts da skill (23) e da entrega (34) | **executado** | não executado | não executado | não executado |
| Cenários CEN-01 a CEN-16 (110 verificações; 2 delas puladas em perfil sem validador ou book-to-skill) | **executado** | não executado | não executado | não executado |
| Ligações: junção (Windows) e link simbólico (Linux) | junção **executada**; link de arquivo indisponível | — | não executado (os testes criam link simbólico no Linux) | não executado |
| Ciclo instalar/verificar/atualizar/remover com junção | **executado** com a API do 3.12 e com a ausência dela simulada | **não executado** (só simulado) | — | — |
| MCP com SDK real | **executado** em processo e por stdio (sem host) | — (SDK exige 3.11+) | não executado | não executado |
| CAG real | não executado (sem modelo autorizado) | — | não executado | não executado |
| Avaliações comportamentais com subagentes | **não repetidas** na 1.4.0 (custo; decisão do titular) | — | — | — |

Cenários comportamentais a repetir primeiro, quando autorizado (o que mudou desde a 1.0.0/1.1.0):
inspeção sem listar outros projetos; negativa antes de leitura (com trace de ferramentas); retomada
sem repetir efeitos; projeto existente com preservação comprovada; bloqueio de integração sem
autorização. Registrar versão e hash da skill, entradas, recursos presentes e o trace de cada execução;
para comparar desempenho, repetir os mesmos cenários (≥ 3 execuções por configuração).
