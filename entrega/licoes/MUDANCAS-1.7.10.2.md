# Mudanças da 1.7.10.2

Versão: 1.7.10.2 · Anterior: 1.7.10.1 · Registro: 2026-11-03, correção pedida pela sessão de um projeto real e trazida
pelo titular à sessão da raiz (o pedido do titular àquela sessão: "fazer todos os passos pendentes para que possamos,
enfim, iniciar um novo projeto dentro deste projeto"; a forma, a versão e os testes ficaram a critério do
coordenador). O kit continua 1.7.10. Revisão de segurança: `entrega/auditoria/REVISAO-SEGURANCA-1.7.10.2.md`.

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/assets/host/preparo_host.py` | a lista fechada do `--tools` e de `FUNDACAO_FERRAMENTAS` troca `Task` por `Agent`, o nome da ferramenta de subagentes no Claude Code 2.1.302 | numa sessão de projeto aberta pelo lançador em 02/11/2026, toda chamada de subagente foi negada pelo guarda, que compara o nome exato: os squads do projeto não rodavam, e o WebFetch, que na 2.1.302 só roda pelo agente `web-fetch`, ficou fora de alcance | testes do perfil, da área e do lançador nos dois sistemas; o preparo real do titular ainda não rodou | sem efeito observado |
| M2 | `fundacao-ia-multiprojetos/assets/hooks/guarda_ferramentas.py` | `Agent` e `Task` valem pelo mesmo item da lista; a entrada da ferramenta passa por uma lista fechada de campos, e `isolation`, `cwd`, `name`, `team_name`, `mode` e campo novo são negados; o tipo de subagente fica nos nomes dos embutidos `general-purpose`, `web-fetch`, `Explore` e `Plan` | o esquema da ferramenta no binário 2.1.302 tem `isolation: "remote"` (agente na nuvem), `worktree`, `cwd` e equipes, e agente definido em arquivo traz ferramentas, MCP e hooks no cabeçalho, sem negação por nome no perfil: liberar o nome sem conferir a entrada abriria esses caminhos | testes do hook nos dois sistemas (campos aceitos, negados e novos, tipos, entrada ilegível, nome antigo); a prova 13 na sessão real ainda não rodou | sem efeito observado |
| M3 | `fundacao-ia-multiprojetos/scripts/tests/test_hooks_1710.py` e os testes do host | testes novos da ferramenta Agent; as listas esperadas trocam `Task` por `Agent`; o caso "ferramenta a mais" do perfil passa a usar `Task` | o comportamento mudou de propósito | os testes passam no Windows e no Ubuntu | ajudou |
| M4 | `fundacao-ia-multiprojetos/references/` e `assets/templates/CHECKLIST-PROJETO.md` | a correção 1.7.10.2; a conferência do binário em fontes verificadas; segurança §8.2; fluxo C; a prova 13 (subagentes) no checklist; o SKILL.md muda só a versão | os textos citavam `Task` e não diziam como provar os subagentes | o verificador de referências passa | ajudou |
| M5 | `fundacao-ia-multiprojetos/assets/hooks/guarda_ferramentas.py` | cada campo aceito da ferramenta Agent tem o tipo conferido (texto ou booleano), e `subagent_type: null` é negado; `SubagentHandback`, o canal do relatório do subagente, vale com o item dos subagentes | a revisão de segurança da versão viu `subagent_type: null` e `model` objeto passarem sem decisão (H5) e o relatório do subagente correr o risco de não chegar com `SubagentHandback` negado (H4) | testes novos nos dois sistemas; na sessão real, pendente da prova 13 | sem efeito observado |
| M6 | `fundacao-ia-multiprojetos/assets/hooks/sinais_sessao.py` e `assets/host/wsl/settings.wsl.json` | no perfil do projeto no Ubuntu, o `SubagentStart` repete ao subagente as regras da sessão (a pasta do projeto, nada de outro projeto, `state/` ou segredo, dado não é instrução, banco só pelo porteiro); o preparo e a conferência do perfil exigem o hook | a revisão de segurança da versão (F2): o subagente começa sem a conversa, onde o lançador põe as regras, e o Explore, o Plan e o web-fetch nem leem o CLAUDE.md | testes do hook, do perfil e do ensaio nos dois sistemas; pela leitura do binário, o web-fetch não roda esse hook e a falha dele só avisa; o efeito no subagente, pendente da prova 13 | sem efeito observado |
| M7 | `fundacao-ia-multiprojetos/assets/host/preparo_host.py` | o preparo recusa agentes em `/etc/claude-code/.claude/agents` | a revisão de segurança da versão (F1): no 2.1.302, uma definição de mesmo nome toma o lugar da embutida, e o guarda confere o tipo pelo nome | teste novo do preparo no Ubuntu | sem efeito observado |

## O que a versão traz

- Depois do preparo do titular, as sessões de projeto usam subagentes (a ferramenta Agent), só locais e com os nomes
  dos tipos embutidos: sem nuvem, sem cópia git, sem outra pasta e sem equipes. O `general-purpose`, o `Explore` e o
  `Plan` recebem as regras da sessão no início (o `web-fetch`, não: a única ferramenta dele é o WebFetch), e o
  `SubagentHandback`, o canal do relatório deles, fica liberado (se ele fica ativo nas sessões, a prova 13 mede).
- Com a ficha que abre o WebFetch, a leitura de páginas funciona pelo agente `web-fetch`.

## Estado da liberação e limites conhecidos

- Os hooks da raiz mudaram: cada projeto precisa do preparo de novo (Windows e Ubuntu) para abrir; até lá, o lançador
  recusa.
- Que os hooks rodam dentro dos subagentes, e que as regras do `SubagentStart` chegam a eles, está lido no binário
  2.1.302; a prova 13 mede na sessão real. Pela mesma leitura, a falha desse hook só avisa, e o `web-fetch` não o
  roda; se o `guarda_rede.py` roda no WebFetch do `web-fetch`, não foi localizado (a prova 13 mede).
- O guarda confere o nome do tipo, não a origem da definição; ficam para a 1.7.11 o hook `agent.spawn` de plugin, a
  skill com `context: fork` e quem preenche o `projectAgentsElsewhere`.
- O modo `--restricted` da 2.1.302 e o canário que mede de fato ficam para a 1.7.11. A CI pública desta versão roda com
  os mesmos testes dependentes das máquinas do GitHub da 1.7.10.

## Lições

### L1 — O nome de uma ferramenta muda entre versões do Claude Code
- Gatilho: uma lista positiva de ferramentas compara o nome exato, e o Claude Code renomeia uma ferramenta, aceitando o nome antigo no `--tools`.
- Lição: a cada versão fixada, confira os nomes da lista contra o binário (o nome com que o evento do hook chega) e trate o nome antigo de propósito; liberar um nome é também conferir a entrada da ferramenta, que pode ter ganhado campos.
- Evidência: M1, M2; `fundacao-ia-multiprojetos/references/fontes-verificadas.md`, conferência da 1.7.10.2; a sessão do projeto teve toda chamada de subagente negada em 02/11/2026.
- Confiança: alta

### L2 — O subagente não herda a conversa onde o lançador põe as regras
- Gatilho: uma sessão cujas regras de isolamento lógico vêm no prompt de abertura passa a delegar trabalho a subagentes.
- Lição: as regras que a IA segue precisam chegar a cada subagente por um canal da plataforma (o `SubagentStart` com `additionalContext`), não só pelo prompt que a sessão escreve; e o nome de um tipo de agente não diz de onde veio a definição.
- Evidência: M5, M6, M7; `fundacao-ia-multiprojetos/assets/hooks/sinais_sessao.py`; a revisão de segurança da versão leu no binário 2.1.302 o agente novo "with no memory of prior runs" e a junção das definições pelo nome.
- Confiança: média
