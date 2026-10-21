# Árvore da skill e finalidade de cada componente

Raiz: `fundacao-ia-multiprojetos/` · 181 arquivos. Pastas com muitos arquivos de mesma natureza são descritas uma vez. `evals/` fica fora do pacote `.skill` (vai no pacote completo).

| Caminho | Finalidade |
|---|---|
| `LICENSE.txt` | Licença MIT da skill (texto integral; o campo `license` do SKILL.md aponta para ele). |
| `SKILL.md` | Ponto de entrada: finalidade, acionamento, seleção do fluxo (A/B/C), regras comuns, autonomia, retomada, critérios de conclusão e mapa de referências. |
| `assets/fundacao-kit/fundacao/__init__.py` | Versão do kit. |
| `assets/fundacao-kit/fundacao/__main__.py` | CLI da fundação (init, status, projeto, tarefa, decisao, componente, acl, eventos, backup). |
| `assets/fundacao-kit/fundacao/adapters/` (4 arquivos) | Adaptadores de provedores: contrato base, simulado (rotulado) e CLIs Claude/Codex (código presente, não executado). |
| `assets/fundacao-kit/fundacao/components/` (2 arquivos) | Componentes substituíveis registrados (exemplo: manifesto de fontes). |
| `assets/fundacao-kit/fundacao/core/` (20 arquivos) | Núcleo do kit de referência (Python + SQLite): banco e migrações, identidade e ACL, projetos, tarefas/orquestração, componentes, memória, conhecimento (GOLD/RAG), cache, uso, backup, rotas, eventos e decisões assinadas do titular. |
| `assets/fundacao-kit/fundacao/mcp_servidor.py` | Servidor MCP de leitura da fundação (listar_projetos, listar_documentos, buscar) pela camada de autorização. |
| `assets/fundacao-kit/registry/` (3 arquivos) | Registro de componentes (desligados por padrão), política de rotas e política de decisões. |
| `assets/fundacao-kit/templates/project/` (3 arquivos) | Modelo de projeto (instruções, contrato de entregas, exemplo fictício). |
| `assets/fundacao-kit/tests/` (31 arquivos) | Suíte de conformidade (301 testes positivos e negativos, incluídas as regressões da auditoria externa da 1.3.4 em test_auditoria_*.py, as da auditoria final da 1.4.2 em test_auditoria_final_1_4_2.py, as da 1.5.0 em test_auditoria_1_5_0_*.py e as decisões assinadas em test_decisoes*.py; até 5 pulados: links simbólicos que o sistema não permite criar, por falta de privilégio no Windows ou em volume exFAT, e o ensaio do comando de assinatura no bash, que só roda no Linux ou no WSL). |
| `assets/hooks/guarda_caminho.py` | Hook preventivo (PreToolUse) que nega escrita fora do projeto autenticado e ferramentas MCP não liberadas; falha fechada. |
| `assets/hooks/guarda_identidade.py` | Hook PreToolUse (Bash/PowerShell) do regime de dados reais: nega troca de FUNDACAO_PRINCIPAL pela sessão; falha fechada. |
| `assets/host/preparo_host.py` | Ajudante (biblioteca padrão): gera settings.json, settings.wsl.json e settings.local.json pelos modelos, normaliza o /etc/wsl.conf e monta o lançador. |
| `assets/host/windows/preparar-maquina.ps1` | PowerShell do titular: chave das decisões, âncora allowed_signers com dono Administradores e herança cortada (UAC só aí), hooks e perfis em <raiz>/.claude; simulação, -SemUAC e relatório JSON. |
| `assets/host/windows/settings.json` | Modelo do perfil das sessões do Windows: negações de segredos e de state/, MCP do aplicativo e os dois hooks. |
| `assets/host/wsl/abrir-sessao.sh` | Modelo do lançador: confere Claude Code, perfil e hooks pelo hash, a identidade e a interoperabilidade desligada; abre com o prompt de retomada. |
| `assets/host/wsl/preparar-wsl.sh` | bash do titular no Ubuntu: bubblewrap e socat, AppArmor do bwrap, um só [interop] desligado, Claude Code fixado por SHA-256 e o lançador. |
| `assets/host/wsl/settings.wsl.json` | Modelo do perfil da sessão de dados reais no WSL2: sandbox estrito, state/ em allowRead e allowWrite, escrita negada nos outros projetos. |
| `assets/templates/` (17 arquivos) | Modelos reutilizáveis (diagnóstico, mapa funcional, plano de adaptação, decisão, contrato, inventário, evidências, aprovação, proveniência, auditoria, relatório final, checklist de dados reais, compatibilidade de hosts, retomada, matriz, formulário de implantação, folha de decisões). |
| `evals/acionamento/montar_simulacao.py` | Monta e pontua a simulação de acionamento (catálogo real de skills, sem gabarito). |
| `evals/cenarios/run_cenarios.py` | Executor determinístico dos cenários CEN-01–CEN-16 em pastas descartáveis. |
| `evals/evals.json` | Avaliações com subagentes (9: novo, existente, reexecução, incompatível, dependência, retomada, acesso cruzado, referência ausente, injeção em conteúdo autorizado). |
| `evals/fixtures/legado-incompativel/` (2 arquivos) | Sistema fictício incompatível (caminho absoluto, escape, credencial, rede). |
| `evals/fixtures/legado-squad/` (15 arquivos) | Projeto legado fictício (squad de petições) com defeitos didáticos para o Fluxo B. |
| `evals/preparar_avaliacoes.py` | Prepara ambientes descartáveis das avaliações com subagentes. |
| `evals/trigger-evals.json` | 20 consultas de acionamento (10 devem acionar, 10 não). |
| `evals/verificar_execucoes.py` | Coleta fatos objetivos das execuções (origem intacta, vazamentos, banco, ACL e, em E7/E9, acessos ao outro projeto no trace de ferramentas). |
| `references/autonomia-e-escalonamento.md` | Quando decidir sozinho, preparar e pedir decisão ou bloquear; formato de pergunta e de bloqueio. |
| `references/capacidades/01-orquestracao.md` | Orquestração: escolha de framework × própria, estados, checkpoints, recibos, retomada, cancelamento, decisão humana. |
| `references/capacidades/02-agentes-subagentes.md` | Agentes e subagentes: papéis, contratos, orçamento, contexto autorizado, paralelismo e divergências. |
| `references/capacidades/03-provedores-modelos.md` | Dois ou mais provedores: regimes (assinatura, CLI, API, SDK), rotas, fallback autorizado, continuidade. |
| `references/capacidades/04-memoria.md` | Memória persistente: origem, versão, escopo, revisão, concorrência, retirada, recuperação entre sessões. |
| `references/capacidades/05-gold.md` | GOLD: preparação, curadoria (rubrica), aprovação por hash, vigência, proveniência, retirada. |
| `references/capacidades/06-rag.md` | RAG: ingestão, indexação, recuperação autorizada antes do LIMIT, citações verificáveis, avaliação separada. |
| `references/capacidades/07-cag-caches.md` | CAG com reutilização real do estado KV (frio × quente, invalidação) × cache de prompt × cache de resposta. |
| `references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md` | Ciclo de vida de ferramentas, hooks, MCP, skills e plugins por host. |
| `references/capacidades/09-consumo-qualidade.md` | Orçamento, limites, contexto seletivo; medição × estimativa × desconhecido. |
| `references/capacidades/10-observabilidade-conversa.md` | Eventos, painel de estado, seleção do projeto autorizado, operação por conversa. |
| `references/capacidades/11-manutencao-recuperacao.md` | Dependências reproduzíveis, atualização, substituição, backup, restauração isolada, retomada sem duplicar efeitos. |
| `references/comunicacao-leigo.md` | Comunicação com o titular leigo: parar só com motivo, cartão de parada, uma ação por vez, comando pronto no shell certo, linguagem simples. |
| `references/fluxo-a-implantar.md` | Fluxo A (A1–A8): implantar a fundação e criar projetos; entradas, ações, saídas, conclusão e falhas; preparo do host para dados reais (§Host); comandos do kit. |
| `references/fluxo-b-adaptar.md` | Fluxo B (B1–B10): diagnosticar e adaptar projeto existente; classes de compatibilidade; caracterização; reversão; encerramento. |
| `references/fluxo-c-operar.md` | Fluxo C (C1–C11): verificar, auditar, atualizar, desativar, backup/restauração, retomada, novo projeto, promoção. |
| `references/fontes-verificadas.md` | Fatos voláteis conferidos com fonte e data (Claude Code, Codex, MCP, Agent Skills, CAG em 18/10/2026; sandbox, instalação nativa, manifesto assinado e WSL em 21/10/2026). |
| `references/livro/apendices.md` | Síntese dos Apêndices C–F (prompts, Windows, modelos de registro, limites). |
| `references/livro/cheatsheet.md` | Regras de decisão de consulta rápida. |
| `references/livro/correcoes-3.0.md` | Correções e acréscimos do documento 2.0 → 3.0, com situação de verificação. |
| `references/livro/glossario.md` | Glossário do livro (Apêndice A) adaptado. |
| `references/livro/indice-aulas.md` | Índice das 41 aulas com páginas e requisitos do Apêndice B. |
| `references/livro/m01-diagnostico.md` | Módulo 01 (A01–A04B, p8–27): diagnóstico, inventário e decisões de arquitetura. |
| `references/livro/m02-nucleo.md` | Módulo 02 (A05–A07, p28–39): ponto de retorno, núcleo, tarefas persistidas e modelo de projeto. |
| `references/livro/m03-execucao.md` | Módulo 03 (A08–A11E, p40–71): provedores, coordenação com retomada, agentes, ferramentas, hooks, MCP, skills e plugins. |
| `references/livro/m04-memoria.md` | Módulo 04 (A12–A14, p72–83): memória persistente e fronteiras de acesso. |
| `references/livro/m05-gold-rag.md` | Módulo 05 (A15–A18, p84–101): GOLD, RAG e fontes; dados GUIA-001/002/003 e gabarito. |
| `references/livro/m06-cag-consumo.md` | Módulo 06 (A19–A21, p102–114): CAG com estado KV, isolamento de caches e consumo. |
| `references/livro/m07-juridico.md` | Módulo 07 (A22–A25, p115–132): projeto jurídico de laboratório (caso Aurora — didático e fictício). |
| `references/livro/m08-software.md` | Módulo 08 (A26–A30, p133–158): engenharia reversa de software (CaixaSim — didático). |
| `references/livro/m09-m10-operacao.md` | Módulos 09–10 (A31–A36, p159–181): conversa, auditoria, atualização, substituição, restauração e fechamento da matriz. |
| `references/livro/padroes.md` | Padrões e antipadrões extraídos do livro. |
| `references/principios-e-evidencias.md` | Estados honestos, quatro níveis de evidência, rótulos de origem, simulação × real, 'não medido' ≠ 0. |
| `references/privacidade-sigilo.md` | Antes de dados reais: sigilo, LGPD, treino e retenção (fatos 3.0 não verificados rotulados). |
| `references/requisitos.md` | R01–R60 em forma compacta: evidência para aceitar, onde a skill atende, cenário. |
| `references/seguranca-isolamento.md` | Identidade fora do modelo, ACL, negar por padrão, barreira de decisões assinadas, injeção, controles preventivos (hooks e preparo do host), provas negativas. |
| `scripts/atualizar_fundacao.py` | Atualiza uma fundação para o kit da skill num só comando: checar (só lê), aplicar (backup antes, ensaio numa cópia restaurada, promoção, backup depois e registro) e desfazer. |
| `scripts/backup_sqlite.py` | Backup consistente de SQLite pela API de backup, com verificação de integridade. |
| `scripts/cag_kv_demo.py` | Demonstração do mecanismo CAG (prefill único, ramo KV por pergunta, frio × quente, invalidação); bloqueia sem modelo. |
| `scripts/caracterizar.py` | Testes de caracterização (golden master) antes × depois para o Fluxo B. |
| `scripts/inspecionar_ambiente.py` | Inventário do ambiente (SO, Python, SQLite/FTS5, CLIs, WSL) sem ler segredos; consulta a versão das CLIs (salvo --somente-localizar) e só grava com --saida, que recusa arquivo existente. |
| `scripts/instalar_kit.py` | Instala o kit de referência numa raiz, idempotente, preservando conflitos e registrando hashes. |
| `scripts/manifesto.py` | Manifesto de hashes (criar/verificar/comparar) para referência recuperável; segredos excluídos sem leitura. |
| `scripts/matriz.py` | Matriz de requisitos: iniciar, validar regras de estado/evidência e relatório ordenado por bloqueios. |
| `scripts/mcp_ensaio.py` | Ensaio MCP real-local: servidor da fundação em processo separado (stdio), descoberta, chamada autorizada, negativa entre projetos e encerramento. |
| `scripts/retomada.py` | Cria e valida o registro de retomada (campos mínimos). |
| `scripts/sinais_compatibilidade.py` | Sinais objetivos de compatibilidade (caminho absoluto, escape, credencial, rede, dependências) e classe sugerida. |
| `scripts/tests/` (17 arquivos) | Testes dos scripts da skill (instalação e atualização do kit, caracterização, manifesto, backup SQLite, matriz, retomada, inventário, hooks, conformidade com configuração local, referências das decisões e preparo do host em PowerShell e bash reais), em pastas descartáveis; rodar com python -B -m unittest discover -s scripts/tests -t scripts/tests. |
| `scripts/verificar_referencias.py` | Confere links e caminhos citados pela skill (integridade das referências). |
