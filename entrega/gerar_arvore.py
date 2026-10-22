#!/usr/bin/env python3
"""Gera ARVORE-SKILL.md: árvore de arquivos da skill com a finalidade de cada componente.

Uso: python gerar_arvore.py   (a partir de qualquer pasta)
Arquivos sem finalidade cadastrada aparecem como "(sem descrição)" — trate como lacuna.
"""
from pathlib import Path

RAIZ = Path(__file__).resolve().parents[1]
SKILL = RAIZ / "fundacao-ia-multiprojetos"
SAIDA = RAIZ / "entrega" / "ARVORE-SKILL.md"

FINALIDADE = {
    "SKILL.md": "Ponto de entrada: finalidade, acionamento, seleção do fluxo (A/B/C), regras comuns, autonomia, retomada, critérios de conclusão e mapa de referências.",
    "LICENSE.txt": "Licença MIT da skill (texto integral; o campo `license` do SKILL.md aponta para ele).",
    "AVISOS-DE-TERCEIROS.md": "Origens externas aproveitadas (projeto, commit, licença, ideia ou trecho), com o aviso de copyright e o texto da licença de cada trecho.",
    "references/principios-e-evidencias.md": "Estados honestos, quatro níveis de evidência, rótulos de origem, simulação × real, 'não medido' ≠ 0.",
    "references/autonomia-e-escalonamento.md": "Quando decidir sozinho, preparar e pedir decisão ou bloquear; formato de pergunta e de bloqueio.",
    "references/comunicacao-leigo.md": "Comunicação com o titular leigo: parar só com motivo, cartão de parada, uma ação por vez, comando pronto no shell certo, linguagem simples.",
    "references/fluxo-a-implantar.md": "Fluxo A (A1–A8): implantar a fundação e criar projetos; entradas, ações, saídas, conclusão e falhas; preparo do host para dados reais (§Host); comandos do kit.",
    "references/fluxo-b-adaptar.md": "Fluxo B (B1–B10): diagnosticar e adaptar projeto existente; classes de compatibilidade; caracterização; reversão; encerramento.",
    "references/fluxo-c-operar.md": "Fluxo C (C1–C11): verificar, auditar, atualizar, desativar, backup/restauração, retomada, novo projeto, promoção.",
    "references/capacidades/01-orquestracao.md": "Orquestração: escolha de framework × própria, estados, checkpoints, recibos, retomada, cancelamento, decisão humana.",
    "references/capacidades/02-agentes-subagentes.md": "Agentes e subagentes: papéis, contratos, orçamento, contexto autorizado, paralelismo em ondas e divergências.",
    "references/capacidades/03-provedores-modelos.md": "Dois ou mais provedores: regimes (assinatura, CLI, API, SDK), rotas, fallback autorizado, continuidade.",
    "references/capacidades/04-memoria.md": "Memória persistente: origem, versão, escopo, revisão, concorrência, retirada, recuperação entre sessões.",
    "references/capacidades/05-gold.md": "GOLD: preparação, curadoria (rubrica), aprovação por hash, vigência, proveniência, retirada.",
    "references/capacidades/06-rag.md": "RAG: ingestão, indexação, recuperação autorizada antes do LIMIT, citações verificáveis, avaliação separada.",
    "references/capacidades/07-cag-caches.md": "CAG com reutilização real do estado KV (frio × quente, invalidação) × cache de prompt × cache de resposta.",
    "references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md": "Ciclo de vida de ferramentas, hooks, MCP, skills e plugins por host.",
    "references/capacidades/09-consumo-qualidade.md": "Orçamento, limites, contexto seletivo; medição × estimativa × desconhecido.",
    "references/capacidades/10-observabilidade-conversa.md": "Eventos, painel de estado, seleção do projeto autorizado, operação por conversa.",
    "references/capacidades/11-manutencao-recuperacao.md": "Dependências reproduzíveis, atualização, substituição, backup, restauração isolada, retomada sem duplicar efeitos.",
    "references/seguranca-isolamento.md": "Identidade fora do modelo, ACL, negar por padrão, barreira de decisões assinadas, injeção, controles preventivos (hooks e preparo do host), provas negativas.",
    "references/privacidade-sigilo.md": "Antes de dados reais: sigilo, LGPD, treino e retenção (fatos 3.0 não verificados rotulados).",
    "references/requisitos.md": "R01–R60 em forma compacta: evidência para aceitar, onde a skill atende, cenário.",
    "references/fontes-verificadas.md": "Fatos voláteis conferidos com fonte e data (Claude Code, Codex, MCP, Agent Skills, CAG em 18/10/2026; sandbox, instalação nativa, manifesto assinado, WSL, instruções e skills aninhadas, web, AGENTS.md do Codex e GitHub Actions em 21/10/2026).",
    "references/livro/indice-aulas.md": "Índice das 41 aulas com páginas e requisitos do Apêndice B.",
    "references/livro/correcoes-3.0.md": "Correções e acréscimos do documento 2.0 → 3.0, com situação de verificação.",
    "references/livro/glossario.md": "Glossário do livro (Apêndice A) adaptado.",
    "references/livro/padroes.md": "Padrões e antipadrões extraídos do livro.",
    "references/livro/cheatsheet.md": "Regras de decisão de consulta rápida.",
    "references/livro/apendices.md": "Síntese dos Apêndices C–F (prompts, Windows, modelos de registro, limites).",
    "references/livro/m01-diagnostico.md": "Módulo 01 (A01–A04B, p8–27): diagnóstico, inventário e decisões de arquitetura.",
    "references/livro/m02-nucleo.md": "Módulo 02 (A05–A07, p28–39): ponto de retorno, núcleo, tarefas persistidas e modelo de projeto.",
    "references/livro/m03-execucao.md": "Módulo 03 (A08–A11E, p40–71): provedores, coordenação com retomada, agentes, ferramentas, hooks, MCP, skills e plugins.",
    "references/livro/m04-memoria.md": "Módulo 04 (A12–A14, p72–83): memória persistente e fronteiras de acesso.",
    "references/livro/m05-gold-rag.md": "Módulo 05 (A15–A18, p84–101): GOLD, RAG e fontes; dados GUIA-001/002/003 e gabarito.",
    "references/livro/m06-cag-consumo.md": "Módulo 06 (A19–A21, p102–114): CAG com estado KV, isolamento de caches e consumo.",
    "references/livro/m07-juridico.md": "Módulo 07 (A22–A25, p115–132): projeto jurídico de laboratório (caso Aurora — didático e fictício).",
    "references/livro/m08-software.md": "Módulo 08 (A26–A30, p133–158): engenharia reversa de software (CaixaSim — didático).",
    "references/livro/m09-m10-operacao.md": "Módulos 09–10 (A31–A36, p159–181): conversa, auditoria, atualização, substituição, restauração e fechamento da matriz.",
    "scripts/inspecionar_ambiente.py": "Inventário do ambiente (SO, Python, SQLite/FTS5, CLIs, WSL) sem ler segredos; consulta a versão das CLIs (salvo --somente-localizar) e só grava com --saida, que recusa arquivo existente.",
    "scripts/instalar_kit.py": "Instala o kit de referência numa raiz, idempotente, preservando conflitos, registrando hashes e retirando com backup os órfãos do kit anterior.",
    "scripts/atualizar_fundacao.py": "Atualiza uma fundação para o kit da skill num só comando: checar (só lê, sem executar a raiz), aplicar (backup antes, ensaio numa cópia restaurada com a catraca dos testes, promoção, instruções da raiz, backup depois, inventário do host e registro ancorado; com o kit igual, só as instruções) e desfazer (só registro ancorado, nas áreas de código).",
    "scripts/codigo_conferido.py": "Apoio do atualizador: inventário exato das áreas de código por hash, cópia conferida de onde o código antigo e os testes do ensaio rodam e execução com python -I (nada da raiz roda antes de conferido).",
    "scripts/registro_atualizacao.py": "Apoio do atualizador: registro e âncora da atualização e o desfazer (só registro ancorado, nas áreas de código, com o código ainda igual ao que a atualização deixou).",
    "scripts/gravacao_segura.py": "Gravação na raiz sem seguir ligação nem vínculo físico (temporário imprevisível e exclusivo com os.replace, arquivo novo, acréscimo conferido), usada pelo atualizador e pelas instruções da raiz.",
    "scripts/manifesto.py": "Manifesto de hashes (criar/verificar/comparar) para referência recuperável; segredos excluídos sem leitura.",
    "scripts/caracterizar.py": "Testes de caracterização (golden master) antes × depois para o Fluxo B, presos ao plano de execução aprovado (SHA-256).",
    "scripts/execucao_isolada.py": "Lançador único do código importado no Fluxo B: plano com hash, manifesto obrigatório com a cópia, bubblewrap no Linux/WSL (recusa sem ele, salvo --sem-isolamento com motivo; entradas só da cópia ou do projeto dela), ambiente mínimo, árvore de processos contida, saída com teto e limites do SO.",
    "scripts/folha_do_plano.py": "Texto da folha de decisões do plano de execução: entradas e pasta gravável, o que prende o código (manifesto ou só o programa), avisos de local e o SHA-256 do aceite.",
    "scripts/codigo_do_plano.py": "O que prende o código no plano de execução: arquivos citados cobertos pelo manifesto, código NÃO PRESO (pasta de trabalho, variáveis de carregamento, {entrada} como programa) e a conferência de programa, manifesto e cópia antes e depois de cada caso.",
    "scripts/sinais_compatibilidade.py": "Sinais objetivos de compatibilidade (caminho absoluto, escape, credencial, rede, dependências) e classe sugerida.",
    "scripts/matriz.py": "Matriz de requisitos: iniciar, validar regras de estado/evidência e relatório ordenado por bloqueios.",
    "scripts/retomada.py": "Cria, valida e arquiva o registro de retomada (campos mínimos, avisos de tamanho, histórico arquivado conferido por hash).",
    "scripts/instrucoes_raiz.py": "Instruções automáticas na raiz: AGENTS.md gerado pelo modelo (sem nomes de projetos; trecho do titular preservado) e CLAUDE.md com @AGENTS.md; gerar e conferir.",
    "scripts/instrucoes_aninhadas.py": "Lista, só lendo, instruções, skills, agentes, comandos, regras, MCP e configurações aninhados numa pasta e sugere claudeMdExcludes e as negações Skill(<nome>).",
    "scripts/inventariar_host.py": "Inventário do ecossistema do host, esquema 2 (skills, duplicatas, plugins e o que cada um carrega, catálogos, MCP e hooks, com alertas de matcher), sem ambiente, cabeçalhos nem conta; gravar e verificar (acusa hook acrescentado).",
    "scripts/inventario_plugins.py": "Hooks, servidores MCP e skills que cada plugin carrega, lidos só dentro de ~/.claude/plugins/, sem seguir ligação e com tetos durante a varredura; MCP só com nome, tipo, executável ou host (usado por inventariar_host.py).",
    "scripts/alertas_hooks.py": "Regra do matcher dos hooks conferida na documentação e os alertas do inventário: matcher que nunca casa, que casa tudo e evento fora do guarda (usado por inventariar_host.py).",
    "scripts/verificar_referencias.py": "Confere links e caminhos citados pela skill e os comandos citados contra o argparse dos scripts.",
    "scripts/backup_sqlite.py": "Backup consistente de SQLite pela API de backup, com verificação de integridade.",
    "scripts/mcp_ensaio.py": "Ensaio MCP real-local: servidor da fundação em processo separado (stdio), descoberta, chamada autorizada, negativa entre projetos e encerramento.",
    "scripts/cag_kv_demo.py": "Demonstração do mecanismo CAG (prefill único, ramo KV por pergunta, frio × quente, invalidação); bloqueia sem modelo.",
    "assets/hooks/guarda_identidade.py": "Hook PreToolUse (Bash/PowerShell) do regime de dados reais: nega troca de FUNDACAO_PRINCIPAL pela sessão; falha fechada.",
    "assets/hooks/guarda_caminho.py": "Hook preventivo (PreToolUse) que nega escrita fora do projeto autenticado e ferramentas MCP não liberadas; falha fechada.",
    "assets/host/": "Preparo do host para dados reais (Windows e WSL2): scripts que o titular roda no próprio terminal, modelos de perfil e o ajudante que os preenche.",
    "assets/host/preparo_host.py": "Ajudante (biblioteca padrão): gera settings.json, settings.wsl.json e settings.local.json pelos modelos, normaliza o /etc/wsl.conf e monta o lançador; nega skills aninhadas por nome e entrega o projeto autenticado.",
    "assets/host/windows/preparar-maquina.ps1": "PowerShell do titular: chave das decisões, âncora allowed_signers com dono Administradores e herança cortada (UAC só aí), hooks e perfis em <raiz>/.claude; simulação, -SemUAC e relatório JSON.",
    "assets/host/windows/settings.json": "Modelo do perfil das sessões do Windows: negações de segredos e de state/, pastas data/ fora das instruções, MCP do aplicativo e os dois hooks.",
    "assets/host/wsl/settings.wsl.json": "Modelo do perfil da sessão de dados reais no WSL2: sandbox estrito, state/ em allowRead e allowWrite, escrita negada nos outros projetos, web negada e pastas data/ fora das instruções.",
    "assets/host/wsl/preparar-wsl.sh": "bash do titular no Ubuntu: bubblewrap e socat, AppArmor do bwrap, um só [interop] desligado, Claude Code fixado por SHA-256 e o lançador.",
    "assets/host/wsl/abrir-sessao.sh": "Modelo do lançador: confere Claude Code, perfil e hooks pelo hash, a identidade e a interoperabilidade desligada; abre com o prompt de retomada.",
    "assets/templates/": "Modelos reutilizáveis (diagnóstico, mapa funcional, plano de adaptação, decisão, contrato, inventário, evidências, aprovação, proveniência, auditoria, relatório final, checklist de dados reais, compatibilidade de hosts, retomada, matriz, formulário de implantação, folha de decisões, instruções da raiz, revisão de segurança e passagem do trabalho delegado).",
    "assets/fundacao-kit/fundacao/core/": "Núcleo do kit de referência (Python + SQLite): banco e migrações, identidade e ACL, projetos, tarefas/orquestração, componentes, memória, conhecimento (GOLD/RAG), cache, uso, backup, rotas (política validada ao carregar), eventos e decisões assinadas do titular.",
    "assets/fundacao-kit/fundacao/adapters/": "Adaptadores de provedores: contrato base, simulado (rotulado) e CLIs Claude/Codex (código presente, não executado).",
    "assets/fundacao-kit/fundacao/components/": "Componentes substituíveis registrados (exemplo: manifesto de fontes).",
    "assets/fundacao-kit/fundacao/__main__.py": "CLI da fundação (init, status, projeto, tarefa, decisao, componente, acl, eventos, backup).",
    "assets/fundacao-kit/fundacao/mcp_servidor.py": "Servidor MCP de leitura da fundação (listar_projetos, listar_documentos, buscar) pela camada de autorização.",
    "assets/fundacao-kit/fundacao/__init__.py": "Versão do kit.",
    "assets/fundacao-kit/registry/": "Registro de componentes (desligados por padrão), política de rotas e política de decisões.",
    "assets/fundacao-kit/templates/project/": "Modelo de projeto (instruções, contrato de entregas, exemplo fictício).",
    "assets/fundacao-kit/tests/": "Suíte de conformidade (testes positivos e negativos, incluídas as regressões da auditoria externa da 1.3.4 em test_auditoria_*.py, as da auditoria final da 1.4.2 em test_auditoria_final_1_4_2.py, as da 1.5.0 em test_auditoria_1_5_0_*.py, as decisões assinadas em test_decisoes*.py, na 1.7.0, fronteiras do código, canários das falhas, política de rotas e configuração decidida e, na 1.7.7, as da auditoria Codex Security da 1.7.6 em test_auditoria_1_7_6_*.py e test_auditoria_1_7_7_*.py e as da revisão de segurança em test_revisao_1_7_7*.py; até 5 pulados: links simbólicos que o sistema não permite criar, por falta de privilégio no Windows ou em volume exFAT, e o ensaio do comando de assinatura no bash, que só roda no Linux ou no WSL).",
    "scripts/tests/": "Testes dos scripts da skill (instalação e atualização do kit, caracterização, manifesto, backup SQLite, matriz, retomada, inventário, hooks, conformidade com configuração local, referências das decisões, preparo do host em PowerShell e bash reais e, na 1.7.0, instruções da raiz e aninhadas, inventário do host, catraca e órfãos da atualização e comandos citados), em pastas descartáveis; rodar com python -B -m unittest discover -s scripts/tests -t scripts/tests.",
    "evals/verificar_execucoes.py": "Coleta fatos objetivos de todas as execuções (run-*) de cada braço (origem intacta, vazamentos, banco, ACL, acesso ao gabarito no trace e, em E7/E9, acessos ao outro projeto; em E11, fundação inalterada e relatório privado; em E13, backups apagados, novos e ensaios de restauração); recolhe as saídas da área do executor.",
    "evals/evals.json": "Avaliações com subagentes (13: novo, existente, reexecução, incompatível, dependência, retomada, acesso cruzado, referência ausente, injeção em conteúdo autorizado, retomada desatualizada, auditoria somente leitura, pergunta de andamento e backup anunciado e não feito), com papel (treino × teste), motiva e seguranca (só passa com pass^k).",
    "evals/trigger-evals.json": "20 consultas de acionamento (10 devem acionar, 10 não).",
    "evals/cenarios/run_cenarios.py": "Executor determinístico dos cenários CEN-01–CEN-16 em pastas descartáveis.",
    "evals/preparar_avaliacoes.py": "Prepara ambientes descartáveis das avaliações com subagentes: bancada do avaliador separada da área do executor (ids neutros, skill sem evals/), k execuções por braço, variantes do ensaio contrastivo e teto do livro-caixa.",
    "evals/isolamento.py": "Alarme de isolamento (gabarito, caso, braço e frase de expectativa fora do alcance do executor), cópia da skill sem evals/, impressão dos ambientes dos braços e hash da skill.",
    "evals/livro_avaliacoes.py": "Livro-caixa das rodadas reais de avaliação: autorização, teto (a partida interrompida conta), modelo e custo lidos do rastro e validade do resultado para o texto atual da skill.",
    "evals/medidas_do_rastro.py": "Modelo, custo informado pelo cliente, turnos, duração e consumo de uma partida, lidos do rastro stream-json do claude -p com a regra do kit (ausente = unknown).",
    "evals/cegar.py": "Notas cegas do ensaio contrastivo: cegar, gravar as notas com hash no livro e só então revelar.",
    "evals/banco_avaliado.py": "Leitura do banco de um ambiente avaliado só para leitura, sem confiar no esquema, com teto de valor e prazo; visão ou tabela virtual não é lida.",
    "evals/partidas_da_bancada.py": "Partidas do livro-caixa amarradas às execuções da bancada: execução sem partida concluída que confira não é cegada nem contada.",
    "evals/rastro_do_executor.py": "Detector de acesso ao gabarito no rastro do executor: caminhos próprios fora, curinga, outra execução e cd contam.",
    "evals/resumo_k.py": "pass@k e pass^k a partir das notas por execução; avaliação de segurança só passa com pass^k.",
    "evals/acionamento/montar_simulacao.py": "Monta e pontua a simulação de acionamento (catálogo real de skills, sem gabarito).",
    "evals/fixtures/legado-squad/": "Projeto legado fictício (squad de petições) com defeitos didáticos para o Fluxo B.",
    "evals/fixtures/legado-incompativel/": "Sistema fictício incompatível (caminho absoluto, escape, credencial, rede).",
}


def finalidade(rel: str) -> str:
    if rel in FINALIDADE:
        return FINALIDADE[rel]
    melhores = [k for k in FINALIDADE if k.endswith("/") and rel.startswith(k)]
    return FINALIDADE[max(melhores, key=len)] if melhores else "(sem descrição)"


def main() -> None:
    arquivos = sorted(p.relative_to(SKILL).as_posix() for p in SKILL.rglob("*")
                      if p.is_file() and "__pycache__" not in p.parts)
    linhas = ["# Árvore da skill e finalidade de cada componente", "",
              f"Raiz: `fundacao-ia-multiprojetos/` · {len(arquivos)} arquivos. Pastas com muitos arquivos de "
              "mesma natureza são descritas uma vez. `evals/` fica fora do pacote `.skill` (vai no pacote completo).", "",
              "| Caminho | Finalidade |", "|---|---|"]
    vistos = set()
    sem = []
    for rel in arquivos:
        f = finalidade(rel)
        if f == "(sem descrição)":
            sem.append(rel)
        chave = next((k for k in FINALIDADE if k.endswith("/") and rel.startswith(k)), None)
        if chave and rel not in FINALIDADE:
            if chave in vistos:
                continue
            vistos.add(chave)
            n = sum(1 for a in arquivos if a.startswith(chave))
            linhas.append(f"| `{chave}` ({n} arquivos) | {f} |")
        else:
            linhas.append(f"| `{rel}` | {f} |")
    SAIDA.write_text("\n".join(linhas) + "\n", encoding="utf-8", newline="\n")
    print(f"{SAIDA} ({len(arquivos)} arquivos; sem descrição: {sem})")


if __name__ == "__main__":
    main()
