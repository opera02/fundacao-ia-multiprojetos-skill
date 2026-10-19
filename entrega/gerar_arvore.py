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
    "references/principios-e-evidencias.md": "Estados honestos, quatro níveis de evidência, rótulos de origem, simulação × real, 'não medido' ≠ 0.",
    "references/autonomia-e-escalonamento.md": "Quando decidir sozinho, preparar e pedir decisão ou bloquear; formato de pergunta e de bloqueio.",
    "references/fluxo-a-implantar.md": "Fluxo A (A1–A8): implantar a fundação e criar projetos; entradas, ações, saídas, conclusão e falhas; comandos do kit.",
    "references/fluxo-b-adaptar.md": "Fluxo B (B1–B10): diagnosticar e adaptar projeto existente; classes de compatibilidade; caracterização; reversão; encerramento.",
    "references/fluxo-c-operar.md": "Fluxo C (C1–C11): verificar, auditar, atualizar, desativar, backup/restauração, retomada, novo projeto, promoção.",
    "references/capacidades/01-orquestracao.md": "Orquestração: escolha de framework × própria, estados, checkpoints, recibos, retomada, cancelamento, decisão humana.",
    "references/capacidades/02-agentes-subagentes.md": "Agentes e subagentes: papéis, contratos, orçamento, contexto autorizado, paralelismo e divergências.",
    "references/capacidades/03-provedores-modelos.md": "Dois ou mais provedores: regimes (assinatura, CLI, API, SDK), rotas, fallback autorizado, continuidade.",
    "references/capacidades/04-memoria.md": "Memória persistente: origem, versão, escopo, revisão, concorrência, retirada, recuperação entre sessões.",
    "references/capacidades/05-gold.md": "GOLD: preparação, curadoria (rubrica), aprovação por hash, vigência, proveniência, retirada.",
    "references/capacidades/06-rag.md": "RAG: ingestão, indexação, recuperação autorizada antes do LIMIT, citações verificáveis, avaliação separada.",
    "references/capacidades/07-cag-caches.md": "CAG com reutilização real do estado KV (frio × quente, invalidação) × cache de prompt × cache de resposta.",
    "references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md": "Ciclo de vida de ferramentas, hooks, MCP, skills e plugins por host.",
    "references/capacidades/09-consumo-qualidade.md": "Orçamento, limites, contexto seletivo; medição × estimativa × desconhecido.",
    "references/capacidades/10-observabilidade-conversa.md": "Eventos, painel de estado, seleção do projeto autorizado, operação por conversa.",
    "references/capacidades/11-manutencao-recuperacao.md": "Dependências reproduzíveis, atualização, substituição, backup, restauração isolada, retomada sem duplicar efeitos.",
    "references/seguranca-isolamento.md": "Identidade fora do modelo, ACL, negar por padrão, injeção, controles preventivos (hooks), provas negativas.",
    "references/privacidade-sigilo.md": "Antes de dados reais: sigilo, LGPD, treino e retenção (fatos 3.0 não verificados rotulados).",
    "references/requisitos.md": "R01–R60 em forma compacta: evidência para aceitar, onde a skill atende, cenário.",
    "references/fontes-verificadas.md": "Fatos voláteis conferidos em 18/10/2026 com fonte (Claude Code, Codex, MCP, Agent Skills, CAG).",
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
    "scripts/inspecionar_ambiente.py": "Inventário somente leitura do ambiente (SO, Python, SQLite/FTS5, CLIs, WSL) sem ler segredos.",
    "scripts/instalar_kit.py": "Instala o kit de referência numa raiz, idempotente, preservando conflitos e registrando hashes.",
    "scripts/manifesto.py": "Manifesto de hashes (criar/verificar/comparar) para referência recuperável; segredos excluídos sem leitura.",
    "scripts/caracterizar.py": "Testes de caracterização (golden master) antes × depois para o Fluxo B.",
    "scripts/sinais_compatibilidade.py": "Sinais objetivos de compatibilidade (caminho absoluto, escape, credencial, rede, dependências) e classe sugerida.",
    "scripts/matriz.py": "Matriz de requisitos: iniciar, validar regras de estado/evidência e relatório ordenado por bloqueios.",
    "scripts/retomada.py": "Cria e valida o registro de retomada (campos mínimos).",
    "scripts/verificar_referencias.py": "Confere links e caminhos citados pela skill (integridade das referências).",
    "scripts/backup_sqlite.py": "Backup consistente de SQLite pela API de backup, com verificação de integridade.",
    "scripts/mcp_ensaio.py": "Ensaio MCP real-local: servidor da fundação em processo separado (stdio), descoberta, chamada autorizada, negativa entre projetos e encerramento.",
    "scripts/cag_kv_demo.py": "Demonstração do mecanismo CAG (prefill único, ramo KV por pergunta, frio × quente, invalidação); bloqueia sem modelo.",
    "assets/hooks/guarda_identidade.py": "Hook PreToolUse (Bash/PowerShell) do regime de dados reais: nega troca de FUNDACAO_PRINCIPAL pela sessão; falha fechada.",
    "assets/hooks/guarda_caminho.py": "Hook preventivo (PreToolUse) que nega escrita fora do projeto autenticado e ferramentas MCP não liberadas; falha fechada.",
    "assets/templates/": "Modelos reutilizáveis (diagnóstico, mapa funcional, plano de adaptação, decisão, contrato, inventário, evidências, aprovação, proveniência, auditoria, relatório final, checklist de dados reais, compatibilidade de hosts, retomada, matriz).",
    "assets/fundacao-kit/fundacao/core/": "Núcleo do kit de referência (Python + SQLite): banco e migrações, identidade e ACL, projetos, tarefas/orquestração, componentes, memória, conhecimento (GOLD/RAG), cache, uso, backup, rotas, eventos.",
    "assets/fundacao-kit/fundacao/adapters/": "Adaptadores de provedores: contrato base, simulado (rotulado) e CLIs Claude/Codex (código presente, não executado).",
    "assets/fundacao-kit/fundacao/components/": "Componentes substituíveis registrados (exemplo: manifesto de fontes).",
    "assets/fundacao-kit/fundacao/__main__.py": "CLI da fundação (init, status, projeto, tarefa, componente, acl, eventos, backup).",
    "assets/fundacao-kit/fundacao/mcp_servidor.py": "Servidor MCP de leitura da fundação (listar_projetos, listar_documentos, buscar) pela camada de autorização.",
    "assets/fundacao-kit/fundacao/__init__.py": "Versão do kit.",
    "assets/fundacao-kit/registry/": "Registro de componentes (desligados por padrão) e política de rotas.",
    "assets/fundacao-kit/templates/project/": "Modelo de projeto (instruções, contrato de entregas, exemplo fictício).",
    "assets/fundacao-kit/tests/": "Suíte de conformidade (166 testes positivos e negativos, incluídas as regressões da auditoria externa da 1.3.4 em test_auditoria_*.py e as da auditoria final da 1.4.2 em test_auditoria_final_1_4_2.py; até 3 pulados quando o sistema não permite criar links simbólicos: falta de privilégio no Windows ou volume exFAT).",
    "scripts/tests/": "Testes dos scripts da skill (instalador do kit, caracterização, manifesto e matriz), em pastas descartáveis; rodar com python -B -m unittest discover -s scripts/tests -t scripts/tests.",
    "evals/verificar_execucoes.py": "Coleta fatos objetivos das execuções (origem intacta, vazamentos, banco, ACL e, em E7/E9, acessos ao outro projeto no trace de ferramentas).",
    "evals/evals.json": "Avaliações com subagentes (9: novo, existente, reexecução, incompatível, dependência, retomada, acesso cruzado, referência ausente, injeção em conteúdo autorizado).",
    "evals/trigger-evals.json": "20 consultas de acionamento (10 devem acionar, 10 não).",
    "evals/cenarios/run_cenarios.py": "Executor determinístico dos cenários CEN-01–CEN-16 em pastas descartáveis.",
    "evals/preparar_avaliacoes.py": "Prepara ambientes descartáveis das avaliações com subagentes.",
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
