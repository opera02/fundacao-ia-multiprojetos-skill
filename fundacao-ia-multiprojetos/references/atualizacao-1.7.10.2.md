# Correção 1.7.10.2: a ferramenta de subagentes nas sessões de projeto

Escrita em 03/11/2026, a pedido da sessão de um projeto, trazido pelo titular à sessão da raiz. No Claude Code 2.1.302,
a ferramenta de subagentes se chama `Agent`. A lista do lançador trazia o nome antigo, `Task`, que o `--tools` ainda
aceita, e o `guarda_ferramentas.py` comparava o nome exato: toda chamada de subagente era negada. Sem ela, os squads de
um projeto não rodam, e o WebFetch, que na 2.1.302 só roda pelo agente `web-fetch`, fica fora de alcance mesmo com a
ficha que o abre. A skill vai para 1.7.10.2; o kit continua 1.7.10: o banco, o kit da raiz e o perfil do Windows não
mudam. Mudam o preparo do Ubuntu (`assets/host/preparo_host.py` e o modelo `assets/host/wsl/settings.wsl.json`), os
hooks `guarda_ferramentas.py` e `sinais_sessao.py` e os textos.

## O que muda

| Peça | 1.7.10.1 | 1.7.10.2 |
|---|---|---|
| Lista do `--tools` e de `FUNDACAO_FERRAMENTAS` (`FERRAMENTAS_BASE` do preparo) | `Bash, Read, Edit, Write, Glob, Grep, Skill, Task, TodoWrite` | o mesmo, com `Agent` no lugar de `Task` |
| `guarda_ferramentas.py` (hook da raiz, só no perfil do Ubuntu) | compara o nome exato: `Agent` negado | `Agent` e `Task` valem pelo mesmo item da lista; a entrada da ferramenta passa por uma lista fechada de campos |
| Campos aceitos na ferramenta Agent | (ferramenta negada) | `description`, `prompt`, `subagent_type`, `model` e `effort` (texto) e `run_in_background` (booleano), com o tipo conferido pelo guarda; `subagent_type: null` é negado |
| Campos negados | — | `isolation` (`remote` leva o agente para a nuvem; `worktree` cria uma cópia git), `cwd` (outra pasta de trabalho), `name`, `team_name` e `mode` (agente com nome e equipes) e qualquer campo fora da lista |
| Tipos de subagente (`subagent_type`) | — | só os nomes dos embutidos: `general-purpose` (também sem tipo), `web-fetch`, `Explore` e `Plan` |
| `SubagentHandback` | negado (fora da lista) | vale com o item dos subagentes: é o canal do relatório do subagente para quem o chamou |
| `sinais_sessao.py` no perfil do Ubuntu | só `SessionStart` (compactação) | também `SubagentStart`: repete ao subagente as regras da sessão |
| Preparo do Ubuntu | fixa as managed settings (`/etc/claude-code`) pelo SHA-256 | também recusa o preparo com agentes em `/etc/claude-code/.claude/agents` |

**O nome do tipo, não a origem.** Agente definido em arquivo traz no cabeçalho ferramentas, MCP e hooks próprios, que
o guarda não lê. No 2.1.302, as definições se juntam pelo nome, e uma definição de outra fonte com o nome de um tipo
embutido toma o lugar dele. O guarda confere só o nome. Pela leitura do binário na revisão de segurança da versão, o
`--setting-sources local` do lançador deixa de fora as definições de usuário e de projeto, e as de plugin levam o
prefixo do plugin (`<plugin>:<nome>`). Sobram a pasta das managed settings, que o preparo agora recusa, e uma origem
interna cujo preenchimento a revisão não localizou (`projectAgentsElsewhere`, para a 1.7.11). O perfil nega as skills
de subpasta pelo nome, mas não os agentes: um agente de arquivo pede decisão do titular e uma versão que confira o
cabeçalho.

**As regras da sessão no subagente.** O subagente começa sem a conversa da sessão, onde o lançador põe as regras, e o
Explore, o Plan e o web-fetch nem leem o CLAUDE.md. O `sinais_sessao.py` responde ao `SubagentStart` com as regras em
`additionalContext`, que o binário aceita: pela leitura da revisão de segurança da versão, elas chegam ao
`general-purpose`, ao `Explore` e ao `Plan`. Ao `web-fetch` embutido, não: ele roda o `SubagentStart` só com os hooks
das managed settings, e a única ferramenta dele é o WebFetch. Se o hook falhar, o 2.1.302 só avisa e o subagente
segue sem as regras, apesar do `onFailure: "block"` do perfil. O agente local roda no mesmo processo, e as ferramentas
dele passam pelos hooks da sessão (o esquema lido no binário diz que o evento traz `agent_id` e `agent_type` quando
vem de um subagente), pelas regras do perfil e pelo sandbox. Se o `guarda_rede.py` roda nas chamadas de WebFetch do
`web-fetch` não foi localizado no binário. A prova 13 do `assets/templates/CHECKLIST-PROJETO.md` mede isso na sessão
real.

## O que o binário 2.1.302 mostra (lido sem executar, 03/11/2026)

- A entrada da ferramenta Agent tem `description`, `prompt`, `subagent_type`, `model`, `effort`, `run_in_background`,
  `name`, `team_name` e `mode` (os dois últimos marcados como obsoletos e ignorados), `isolation` (`worktree` ou
  `remote`) e `cwd`, que o esquema mostrado ao modelo omite.
- O esquema da entrada dos hooks diz que `agent_id` falta na conversa principal e que `agent_type` vem "quando o hook
  dispara de dentro de um subagente".
- O WebFetch não fica disponível direto na sessão: ela usa a ferramenta Agent com `subagent_type: "web-fetch"`, e esse
  agente roda sempre local.
- `isolation: "remote"` depende do login no claude.ai e de uma opção remota; sem eles, o pedido cai para `worktree` (com
  repositório git) ou para o agente local. O guarda nega o campo de qualquer forma.
- Existe o modo `--restricted`: tira as ferramentas que rodam código e o WebFetch que o `--tools` não nomeia, ignora os
  arquivos de configuração de usuário, de projeto e local e impede as sessões na nuvem. Não entra na 1.7.10.2: fica para
  a 1.7.11, medido no canário.

Detalhes e o que cada fato muda: [fontes verificadas](fontes-verificadas.md), conferência da 1.7.10.2.

## Ordem numa fundação em uso

1. **Executor:** a liberação da 1.7.10.2 (publicada, instalada no perfil e aplicada na fundação, com kit igual).
2. **Titular, no Windows:** o `preparar-maquina.ps1`, como no preparo da 1.7.10. Ele copia o `guarda_ferramentas.py` e o
   `sinais_sessao.py` novos para `<raiz>/.claude/hooks/`; sem isso, o preparo do Ubuntu recusa ("o hook ... da raiz
   difere do da skill").
3. **Titular, no Ubuntu, com as sessões do Ubuntu fechadas:** o `preparar-wsl.sh` com todos os projetos (um
   `--projeto` para cada). O lançador confere os hooks da raiz pelo SHA-256: o projeto que não passar pelo preparo não
   abre ("mudou desde o preparo"). O projeto com a ficha sob o aceite de risco não precisa do `--canario`: o relatório
   e o aceite já estão na área.
4. **Sessão de cada projeto que usa subagentes:** a prova 13 do checklist, antes do primeiro trabalho com eles.

## Retorno

Voltar para a 1.7.10.1: o `preparar-maquina.ps1` e o `preparar-wsl.sh` dela, na mesma ordem. A lista volta a ter
`Task`, e o guarda antigo volta a negar `Agent`. Nada no banco muda.

## Limites (registre sempre)

- Os hooks são guarda-corpos do processo do Claude Code, não barreira do sistema. Com a raiz em `/mnt/e`, o sandbox não
  confinou os comandos nas sondas de 31/10/2026: o isolamento entre projetos continua lógico.
- Que os hooks rodem dentro dos subagentes, e que o `additionalContext` do `SubagentStart` chegue a eles, está lido no
  binário, não medido; a prova 13 é a medida.
- O guarda confere os nomes e os tipos dos campos, não o conteúdo do `prompt`: o que o subagente faz passa pelas mesmas
  regras da sessão, nada além delas.
- Ficam para a 1.7.11, como hipóteses da revisão de segurança da versão: o hook `agent.spawn` de plugin, que pode trocar
  o tipo depois do guarda; a skill com `context: fork` e `agent:`, que cria subagente sem passar pela ferramenta Agent
  (já era assim antes desta versão); e quem preenche o `projectAgentsElsewhere`.
