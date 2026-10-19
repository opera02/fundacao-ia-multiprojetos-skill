# Resultados dos cenários executáveis

Executado em 2026-10-18T18:32:46-0300 · Python 3.12.10 · win32

| Cenário | Tipo | Requisitos | Verificações | Resultado |
|---|---|---|---|---|
| CEN-01 Fundação nova com dois projetos (Fluxo A) | real-local; identidades de ensaio | R01 R02 R03 R04 R16 R44 R50 R54 | 11/11 | PASSOU |
| CEN-02 Projeto existente adaptado à fundação (Fluxo B) | real-local | R02 R04 R32 R44 R53 + procedimento B1–B10 | 7/9 | FALHOU |
| CEN-03 Reexecução sobre projeto parcialmente adaptado | real-local | R02 R08 R46 + B9 | 3/5 | FALHOU |
| CEN-04 Projeto incompatível nas condições atuais | real-local (análise estática) | B3; R04 R53 | 3/3 | PASSOU |
| CEN-05 Dependência indisponível: bloquear e avançar no independente | real-local; simulado (rotas) | R12 R14 R27 R32 | 5/5 | PASSOU |
| CEN-06 Falha no meio da execução e retomada em outro processo | real-local | R06 R07 R08 R39 R41 R48 | 5/6 | FALHOU |
| CEN-07 Tentativa de acesso entre projetos (memória, RAG, cache, componente) | simulado (identidades de ensaio); lógica da política | R04 R18 R22 R28 | 5/5 | PASSOU |
| CEN-08 Referência obrigatória ausente | estrutural | integridade da skill | 2/2 | PASSOU |
| CEN-09 Backup, restauração isolada e reaplicação de retiradas | real-local | R31 R44 R45 R56 | 6/6 | PASSOU |
| CEN-10 CAG: preparo e reutilização do estado KV (modelo sintético) | real-local com modelo sintético (mecanismo; qualidade não avaliada) | R26 R27 R28 | 6/6 | PASSOU |
| CEN-11 Estrutura, metadados e limites da skill | estrutural | R35 (formato) + auditoria | 9/9 | PASSOU |
| CEN-12 Conformidade do kit em instalação limpa | real-local | R03 R42 R58 R59 | 1/1 | PASSOU |
| CEN-13 Hook preventivo: escrita fora do projeto negada | real-local (eventos simulados do host) | R33 R52 | 4/4 | PASSOU |
| CEN-14 Matriz de requisitos: estados honestos aplicados | estrutural | R43 R50 + Ap. B | 3/3 | PASSOU |

## Detalhes

### CEN-01 — Fundação nova com dois projetos (Fluxo A)
- [x] instalação do kit copia arquivos e registra hashes — esperado: copiados > 0 com sha256; observado: 41
- [x] reinstalação é idempotente — esperado: 0 copiados, 0 conflitos; observado: 0 copiados, 0 conflitos
- [x] init cria o primeiro administrador — esperado: admin_criado=titular; observado: {
  "raiz": "C:\\Users\\<usuario>\\AppData\\Local\\Temp\\fundacao-cen-gvv0vgnw\\CEN-01\\f1",
  "kit_version":
- [x] projeto juridico-lab criado pelo modelo — esperado: código 0; observado: 0
- [x] projeto reversa-lab criado pelo modelo — esperado: código 0; observado: 0
- [x] recriação informa existência sem sobrescrever — esperado: código 2 e E_EXISTS; observado: {"error": {"code": "E_EXISTS", "message": "projeto já existe; nada foi alterado", "project_id": "juridico-lab", "detecte
- [x] tarefa persiste e é lida por processo novo — esperado: task_01a150ed-c8aa-77b9-8e7b-3c2a0fa0e0d1; observado: {
  "task_id": "task_01a150ed-c8aa-77b9-8e7b-3c2a0fa0e0d1",
  "project_id": "juridico-lab",
  "objective": "listar documentos do caso Aurora (fictício)",
  "sta
- [x] outro projeto recebe negativa sem conteúdo — esperado: código 2, E_ACCESS_DENIED, sem 'Aurora'; observado: {"error": {"code": "E_ACCESS_DENIED", "message": "acesso negado", "action": "write", "resource": "project:juridico-lab"}}
- [x] status: cadeia de eventos íntegra e projetos visíveis ao titular — esperado: True; 2 projetos; observado: True; ['juridico-lab', 'reversa-lab']
- [x] status do operador de engenharia lista só o projeto dele — esperado: ['reversa-lab']; observado: ['reversa-lab']
- [x] registro de instalação com versão do kit — esperado: kit_version presente; observado: 1.0.0

### CEN-02 — Projeto existente adaptado à fundação (Fluxo B)
- [x] manifesto da origem exclui o arquivo de segredo sem lê-lo — esperado: .env em excluidos; observado: ['.env']
- [x] classificação sugerida para o legado — esperado: adaptação por interfaces; observado: adaptação por interfaces
- [ ] etapas da adaptação executadas — esperado: todas 'feito'; observado: [('cópia de trabalho', 'feito'), ('caracterização (golden)', 'falhou: \\<usuario>\\AppData\\Local\\Programs\\Python\\Python312\\Lib\\glob.py", line 48, in iglob\n    root_dir = pathname[:0]\n               ~~~~~~~~^^^^\nTypeError: \'NoneType\' object is not subscriptable\n'), ('fundação de destino', 'feito'), ('registro do projeto', 'feito'), ('código legado no projeto (lista positiva)'
- [x] defeito de contrato reproduzido na cópia (painel × manifesto) — esperado: código ≠ 0 (TypeError); observado: 1
- [x] painel funciona com o adaptador, sem alterar a origem — esperado: Agentes: triagem, redator; observado: Agentes: triagem, redator
- [ ] comportamento antes × depois idêntico (golden master) — esperado: 0 divergências em 3 casos; observado: 1 divergências; casos=None (inclui caso inválido (código 2) e fato sem fonte virando pendência)
- [x] origem inalterada (manifesto) — esperado: sem alterados/ausentes/novos; observado: {
  "alterados": [],
  "ausentes": [],
  "novos": []
}
- [x] segredo não copiado para o projeto — esperado: sem .env no projeto; observado: ['agents', 'casos', 'painel', 'run.py', 'scripts', 'squad.canonico.json', 'squad.json', 'squads']
- [x] RETOMADA com campos mínimos preenchidos — esperado: ok; observado: {
  "ok": true,
  "campos_ausentes": []
}

### CEN-03 — Reexecução sobre projeto parcialmente adaptado
- [x] reexecução refaz só o que faltava — esperado: apenas 'registro do componente'; observado: ['registro do componente']
- [ ] terceira passagem não altera nada — esperado: nenhum 'feito'; observado: []
- [x] sem duplicação de projeto ou evento de criação — esperado: 1 e 1; observado: 1 e 1
- [ ] comportamento preservado após reexecuções — esperado: código 0; observado: 1
- [x] atualização do modelo ≠ migração da instância — esperado: migration_needed=False; observado: False

### CEN-04 — Projeto incompatível nas condições atuais
- [x] classe sugerida não é integração direta — esperado: bloqueio nas condições atuais; observado: bloqueio nas condições atuais
- [x] sinais objetivos detectados — esperado: caminho absoluto, escape, credencial, rede; observado: {'caminho_absoluto': 1, 'escape_da_raiz': 1, 'credencial_embutida': 1, 'arquivo_de_segredo': 0, 'rede_ou_servico_externo': 3, 'dependencia_sem_versao': 0}
- [x] valor da credencial não aparece no relatório — esperado: ausente; observado: False

### CEN-05 — Dependência indisponível: bloquear e avançar no independente
- [x] inventário mostra dependência ausente — esperado: dependencia_ausente; observado: dependencia_ausente
- [x] despacho recusado antes de executar — esperado: DependencyUnavailable; observado: True
- [x] trabalho independente continua — esperado: manifesto com 1 arquivo; observado: 1
- [x] sem rota autorizada a tarefa fica bloqueada com motivos — esperado: blocked + motivos por rota; observado: [{'route': 'cli_assinatura', 'skipped': 'rota desabilitada na política'}, {'route': 'api_creditos', 'skipped': 'rota desabilitada na política'}, {'route': 'local', 'skipped': 'rota desabilitada na política'}, {'route': 'simulado', 'skipped': 'rota desabilitada na política'}]
- [x] CAG sem modelo autorizado: bloqueio explícito, sem download — esperado: código 3; estado=bloqueado; observado: 3; bloqueado

### CEN-06 — Falha no meio da execução e retomada em outro processo
- [x] primeiro processo interrompido após gravar a saída e antes de confirmar — esperado: código ≠ 0 (SimulatedInterrupt); observado: 1
- [x] retomada em processo novo conclui — esperado: succeeded; observado: succeeded
- [x] efeito confirmado não repetido (extrair executou 1 vez) — esperado: extrair=1; conferir=1; redigir=1; observado: {'extrair': 1, 'conferir': 1, 'redigir': 1}
- [x] reconciliação pelo recibo registrada — esperado: 1; observado: 1
- [x] execução reconstruível: cadeia de eventos íntegra — esperado: True; observado: True
- [ ] RETOMADA incompleta é recusada — esperado: código 1 com campos ausentes; observado: 1; 5 campos

### CEN-07 — Tentativa de acesso entre projetos (memória, RAG, cache, componente)
- [x] negativas aplicadas pelo serviço (busca, coordenação, escrita) — esperado: 3; observado: 3
- [x] cache negado para identidade sem acesso — esperado: denied; observado: denied
- [x] escape de caminho com '..' recusado — esperado: PathEscape; observado: True
- [x] marcador ausente de saídas e de eventos — esperado: ausente; observado: False
- [x] negativas registradas como evidência — esperado: >= 3; observado: 3

### CEN-08 — Referência obrigatória ausente
- [x] skill íntegra: todas as referências existem — esperado: código 0; observado: {
  "ok": true,
  "referencias_conferidas": 70,
  "ausentes": []
}
- [x] remoção de referência detectada com o caminho — esperado: código 1 citando references/fluxo-b-adaptar.md; observado: 1; 2 citações

### CEN-09 — Backup, restauração isolada e reaplicação de retiradas
- [x] backup consistente criado — esperado: código 0 e integrity ok; observado: 0
- [x] sem registro de retiradas a restauração NÃO é liberada — esperado: released=false; observado: False
- [x] restauração reaplica a retirada antes de liberar — esperado: released=true; GUIA-002@1 reaplicada; observado: True; ['GUIA-002@1']
- [x] fonte retirada não ressuscita no ambiente restaurado — esperado: 0; observado: 0
- [x] restaurar sobre a origem é recusado — esperado: erro; observado: 1
- [x] alteração provocada na cópia é detectada — esperado: changed contém INSTRUCOES.md; observado: ['projects/juridico-lab/INSTRUCOES.md']

### CEN-10 — CAG: preparo e reutilização do estado KV (modelo sintético)
- [x] prefill único com tamanho de KV = fórmula do livro — esperado: 176640; observado: 176640
- [x] modo quente processa só os tokens da pergunta — esperado: tokens quentes < frios; observado: [(33, 378), (21, 366), (28, 373)]
- [x] ramo KV usado e cache-base restaurado a cada pergunta — esperado: True em todas; observado: [(True, True), (True, True), (True, True)]
- [x] saídas quente × frio idênticas (decodificação gulosa) — esperado: True em todas; observado: [True, True, True]
- [x] cache antigo recusado após mudança do corpus — esperado: True; observado: True
- [x] rótulo honesto: qualidade não avaliada — esperado: False; observado: False

### CEN-11 — Estrutura, metadados e limites da skill
- [x] nome kebab-case igual à pasta — esperado: fundacao-ia-multiprojetos; observado: fundacao-ia-multiprojetos
- [x] descrição ≤ 1024 caracteres e sem < > — esperado: ≤1024; observado: 852
- [x] chaves de cabeçalho permitidas pelo padrão — esperado: name, description, license, compatibility, metadata; observado: ['compatibility', 'description', 'license', 'metadata', 'name']
- [x] metadata como mapa de textos — esperado: todos str; observado: {'version': 'str', 'owner': 'str', 'source': 'str', 'last_verified': 'str', 'freshness_window': 'str', 'freshness_category': 'str', 'verified_against': 'str'}
- [x] SKILL.md enxuto (< 500 linhas) — esperado: < 500; observado: 190
- [x] um único SKILL.md no pacote — esperado: 0; observado: []
- [x] sem artefatos de compilação na skill — esperado: 0; observado: []
- [x] quick_validate do skill-creator — esperado: Skill is valid!; observado: Skill is valid!
- [x] varredura de injeção do book-to-skill — esperado: código 0; observado: KILL.md, glossary/patterns/cheatsheet, and chapters/. Move generated content there to have it scanned.
Generated-skill scan passed: no known injection or authority patterns found in the scanned scope.

### CEN-12 — Conformidade do kit em instalação limpa
- [x] suíte de conformidade passa — esperado: OK; observado: OK (skipped=1) (testes: 60)

### CEN-13 — Hook preventivo: escrita fora do projeto negada
- [x] escrita dentro do projeto autenticado segue o fluxo normal — esperado: sem_decisao; observado: sem_decisao
- [x] 0 em 10 tentativas indevidas passam (Write, Edit, '..', MCP, NotebookEdit) — esperado: 10 negadas; observado: 10
- [x] sem projeto autenticado: falha fechada — esperado: deny; observado: deny
- [x] leitura não é bloqueada por este hook — esperado: sem_decisao; observado: sem_decisao

### CEN-14 — Matriz de requisitos: estados honestos aplicados
- [x] matriz inicial válida (60 linhas em desenvolvimento) — esperado: ok; observado: {
  "ok": true,
  "erros": [],
  "linhas": 60
}
- [x] violações detectadas (simulação, inativo sem demonstração, bloqueio sem condição, estado inventado, id removido) — esperado: todas; observado: {'R12': True, 'R33': True, 'R34': True, 'R01': True, 'R05': True}
- [x] relatório começa pelos bloqueados (ordem da A36) — esperado: R34 primeiro; observado: R34
