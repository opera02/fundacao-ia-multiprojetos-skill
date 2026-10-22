# Resultados dos cenários executáveis

Executado em 2026-10-22T10:54:20-0300 · Python 3.12.10 · win32

| Cenário | Tipo | Requisitos | Verificações | Resultado |
|---|---|---|---|---|
| CEN-01 Fundação nova com dois projetos (Fluxo A) | real-local; identidades de ensaio | R01 R02 R03 R04 R16 R44 R50 R54 | 11/11 | PASSOU |
| CEN-02 Projeto existente adaptado à fundação (Fluxo B) | real-local | R02 R04 R32 R44 R53 + procedimento B1–B10 | 10/10 | PASSOU |
| CEN-03 Reexecução sobre projeto parcialmente adaptado | real-local | R02 R08 R46 + B9 | 5/5 | PASSOU |
| CEN-04 Projeto incompatível nas condições atuais | real-local (análise estática) | B3; R04 R53 | 3/3 | PASSOU |
| CEN-05 Dependência indisponível: bloquear e avançar no independente | real-local; simulado (rotas) | R12 R14 R27 R32 | 5/5 | PASSOU |
| CEN-06 Falha no meio da execução e retomada em outro processo | real-local | R06 R07 R08 R39 R41 R48 | 6/6 | PASSOU |
| CEN-07 Tentativa de acesso entre projetos (memória, RAG, cache, componente) | simulado (identidades de ensaio); lógica da política | R04 R18 R22 R28 | 5/5 | PASSOU |
| CEN-08 Referência obrigatória ausente; pacote instalável sem evals/ | estrutural | integridade da skill | 5/5 | PASSOU |
| CEN-09 Backup, restauração isolada, retiradas e origem danificada | real-local | R31 R44 R45 R56 | 20/20 | PASSOU |
| CEN-10 CAG: preparo e reutilização do estado KV (modelo sintético) | real-local com modelo sintético (mecanismo; qualidade não avaliada) | R26 R27 R28 | 6/6 | PASSOU |
| CEN-11 Estrutura, metadados e limites da skill | estrutural | R35 (formato) + auditoria | 10/10 | PASSOU |
| CEN-12 Conformidade do kit em instalação limpa | real-local | R03 R42 R58 R59 | 1/1 | PASSOU |
| CEN-13 Hooks preventivos: escrita fora do projeto e troca de identidade negadas | real-local (eventos simulados do host) | R33 R52 + identidade | 13/13 | PASSOU |
| CEN-14 Matriz de requisitos: estados honestos aplicados | estrutural | R43 R50 + Ap. B | 3/3 | PASSOU |
| CEN-15 MCP local: descoberta, chamada autorizada, negativa entre projetos e encerramento | real-local (SDK mcp, processo separado por stdio; sem rede) | R34 | 6/6 | PASSOU |
| CEN-16 Atualização do kit numa fundação existente (conflito, substituição com retorno) | real-local | R46 R47 + C6 | 4/4 | PASSOU |

## Detalhes

### CEN-01 — Fundação nova com dois projetos (Fluxo A)
- [x] instalação do kit copia arquivos e registra hashes — esperado: copiados > 0 com sha256; observado: 91
- [x] reinstalação é idempotente — esperado: 0 copiados, 0 conflitos; observado: 0 copiados, 0 conflitos
- [x] init cria o primeiro administrador — esperado: admin_criado=titular; observado: {
  "raiz": "C:\\Users\\<usuario>\\AppData\\Local\\Temp\\fundacao-cen-rgsdgiwz\\CEN-01\\f1",
  "kit_version":
- [x] projeto juridico-lab criado pelo modelo — esperado: código 0; observado: 0
- [x] projeto reversa-lab criado pelo modelo — esperado: código 0; observado: 0
- [x] recriação informa existência sem sobrescrever — esperado: código 2 e E_EXISTS; observado: {"error": {"code": "E_EXISTS", "message": "projeto já existe; nada foi alterado", "project_id": "juridico-lab", "detecte
- [x] tarefa persiste e é lida por processo novo — esperado: task_01a163e0-4583-7ddf-861d-daa3cdb35f5e; observado: {
  "task_id": "task_01a163e0-4583-7ddf-861d-daa3cdb35f5e",
  "project_id": "juridico-lab",
  "objective": "listar documentos do caso Aurora (fictício)",
  "sta
- [x] outro projeto recebe negativa sem conteúdo — esperado: código 2, E_ACCESS_DENIED, sem 'Aurora'; observado: {"error": {"code": "E_ACCESS_DENIED", "message": "acesso negado", "action": "read", "resource": "project:juridico-lab"}}
- [x] status: cadeia de eventos íntegra e projetos visíveis ao titular — esperado: True; 2 projetos; observado: True; ['juridico-lab', 'reversa-lab']
- [x] status do operador de engenharia lista só o projeto dele — esperado: ['reversa-lab']; observado: ['reversa-lab']
- [x] registro de instalação com versão do kit — esperado: kit_version presente; observado: 1.7.7

### CEN-02 — Projeto existente adaptado à fundação (Fluxo B)
- [x] manifesto da origem exclui o arquivo de segredo sem lê-lo — esperado: .env em excluidos; observado: ['.env']
- [x] classificação sugerida para o legado — esperado: adaptação por interfaces; observado: adaptação por interfaces
- [x] etapas da adaptação executadas — esperado: todas 'feito'; observado: [('cópia de trabalho', 'feito'), ('caracterização (golden)', 'feito'), ('fundação de destino', 'feito'), ('registro do projeto', 'feito'), ('dados do legado no projeto (lista positiva)', 'feito'), ('código do legado na fonte da fundação (manifesto)', 'feito'), ('adaptador do manifesto', 'feito'), ('componente legado_peticoes', 'feito'), ('registro do componente', 'feito'), ('ferramenta de execução
- [x] defeito de contrato reproduzido na cópia (painel × manifesto) — esperado: código ≠ 0 (TypeError); observado: 1
- [x] painel funciona com o adaptador, sem alterar a origem — esperado: Agentes: triagem, redator; observado: Agentes: triagem, redator
- [x] comportamento antes × depois idêntico (golden master) — esperado: 0 divergências em 3 casos; observado: 0 divergências; casos=3 (inclui caso inválido (código 2) e fato sem fonte virando pendência)
- [x] módulo plantado ao lado da ferramenta de execução faz a comparação parar (B8) — esperado: não roda; acusa o manifesto; observado: ferramenta de execução diferente do manifesto: pasta da ferramenta diferente do manifesto: { "alterados": [], "ausentes": [], "novos": [ "fundacao/__init__.py" ] }
- [x] origem inalterada (manifesto) — esperado: sem alterados/ausentes/novos; observado: {
  "alterados": [],
  "ausentes": [],
  "novos": []
}
- [x] segredo não copiado para o projeto — esperado: sem .env no projeto; observado: ['agents', 'casos', 'painel', 'saida', 'squad.canonico.json', 'squad.json', 'squads']
- [x] RETOMADA com campos mínimos preenchidos — esperado: ok; observado: {
  "ok": true,
  "campos_ausentes": [],
  "avisos": [
    "origem das autorizações não registrada: permissões e próxima ação valem só se confirmadas na convers

### CEN-03 — Reexecução sobre projeto parcialmente adaptado
- [x] reexecução refaz só o que faltava — esperado: apenas 'registro do componente'; observado: ['registro do componente']
- [x] terceira passagem não altera nada — esperado: todas as etapas 'ja-existia'; observado: todas ja-existia
- [x] sem duplicação de projeto ou evento de criação — esperado: 1 e 1; observado: 1 e 1
- [x] comportamento preservado após reexecuções — esperado: código 0; observado: 0
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
- [x] efeito confirmado não repetido (extrair executou 1 vez) — esperado: extrair=1; conferir=1; redigir=1; observado: {'conferir': 1, 'extrair': 1, 'redigir': 1}
- [x] reconciliação pelo recibo registrada — esperado: 1; observado: 1
- [x] execução reconstruível: cadeia de eventos íntegra — esperado: True; observado: True
- [x] RETOMADA incompleta é recusada — esperado: código 1 com campos ausentes; observado: 1; 11 campos

### CEN-07 — Tentativa de acesso entre projetos (memória, RAG, cache, componente)
- [x] negativas aplicadas pelo serviço (busca, coordenação, escrita) — esperado: 3; observado: 3
- [x] cache negado para identidade sem acesso — esperado: denied; observado: denied
- [x] escape de caminho com '..' recusado — esperado: PathEscape; observado: True
- [x] marcador ausente de saídas e de eventos — esperado: ausente; observado: False
- [x] negativas registradas como evidência — esperado: >= 3; observado: 3

### CEN-08 — Referência obrigatória ausente; pacote instalável sem evals/
- [x] skill íntegra: todas as referências existem — esperado: código 0; observado: _do_pacote_instalavel": [],
  "comandos_conferidos": 71,
  "comandos_com_problema": [],
  "scripts_nao_conferidos": []
}
- [x] remoção de referência detectada com o caminho — esperado: código 1 citando references/fluxo-b-adaptar.md; observado: 1; 5 citações
- [x] pacote instalável (sem evals/) passa na verificação de referências — esperado: código 0; citações a evals/ à parte; observado: 0; ausentes=0; fora do pacote=1
- [x] cada arquivo citado como `<skill>/…`, inclusive dentro de comandos, é conferido — esperado: todas as remoções acusadas; observado: 17 de 17; não acusados: []
- [x] erros plantados em cada ocorrência de `<skill>/…` (arquivo, primeira pasta e caixa) são acusados — esperado: todas as ocorrências; observado: 120 de 120; escapam: []

### CEN-09 — Backup, restauração isolada, retiradas e origem danificada
- [x] init cria o registro protegido com identidade — esperado: código 0; identidade reg_…; observado: 0; reg_01a163e1-a0ec-7762-8f60-54d0a62bbc1d
- [x] backup por identidade sem administração é negado — esperado: código 2, E_ACCESS_DENIED, nada criado; observado: {"error": {"code": "E_ACCESS_DENIED", "message": "acesso negado", "action": "admin", "resource": "foundation"}}
- [x] backup consistente criado e com a identidade do registro anotada — esperado: código 0, integrity ok, mesma identidade; observado: 0; reg_01a163e1-a0ec-7762-8f60-54d0a62bbc1d
- [x] revogação de acesso depois da cópia vai para o registro protegido — esperado: código 0; linha acl_revoke; observado: 0; True
- [x] registro com outra identidade NÃO libera e nada é copiado — esperado: código 3; motivo 'identidade'; destino ausente; observado: 3; registro de retiradas com identidade diferente da anotada na
- [x] registro malformado NÃO libera e não povoa o destino — esperado: código 3; 'ilegível'; destino ausente; observado: 3; registro de retiradas ilegível (linha 5: JSON inválido): não
- [x] sem registro de retiradas a restauração NÃO é liberada — esperado: released=false e código 3; observado: False; código 3
- [x] caminho errado do registro de retiradas NÃO libera — esperado: released=false, código 3, motivo 'inexistente'; observado: False; código 3
- [x] restauração reaplica retiradas (fonte e memória) e a revogação antes de liberar — esperado: released=true; fonte, memória e acl reaplicadas; observado: True; ['juridico-lab/GUIA-002@1', 'mem_01a163e1-9fd4-7cf4-b521-e1d46974c48a', 'acl:ex-colaborador:read:project:juridico-lab']
- [x] no ambiente restaurado, a identidade revogada não volta a ver o projeto — esperado: código 0; lista vazia; observado: 0; []
- [x] a reaplicação fica na trilha restaurada, com a cadeia íntegra — esperado: 3 eventos restore_reapplied; cadeia ok; observado: 3; True
- [x] fonte e memória retiradas não ressuscitam no ambiente restaurado — esperado: 0 trechos; memória ausente; observado: 0 trechos; memória presente=False
- [x] restaurar sobre a origem é recusado dentro do contrato — esperado: código 2 e erro JSON E_ARQUIVO; observado: 2; E_ARQUIVO
- [x] alteração provocada na cópia é detectada e sai com código 3 — esperado: changed contém INSTRUCOES.md; código 3; observado: ['projects/juridico-lab/INSTRUCOES.md']; código 3
- [x] banco da cópia trocado por outro íntegro não confere nem libera — esperado: verificar 3; restaurar 3; nada copiado; observado: 3; ['hash do banco diferente do manifesto', 'contagens diferentes do manifesto: acl, chunk, event, protected_outbox, tombstone']; 3
- [x] com o banco de origem corrompido, a CLI restaura autorizada pela cópia sem tocar na origem — esperado: código 0, released=true, origem intacta; observado: 0; origem intacta=True
- [x] com o banco de origem ausente, a CLI restaura e não cria banco na origem — esperado: código 0; origem sem banco; observado: 0; banco criado=False
- [x] backup_sqlite com origem inexistente falha sem criar arquivos — esperado: código 1; nada criado; observado: 1; origem criada=False
- [x] backup_sqlite com '#' no caminho copia os dados de verdade — esperado: código 0; cópia com t=5; nenhum arquivo solto; observado: 0; {'t': 5}; solto=False
- [x] cópia em pasta com '#' é criada, verificada e restaurada pela CLI — esperado: códigos 0, 0, 0; released=true; observado: 0, 0, 0

### CEN-10 — CAG: preparo e reutilização do estado KV (modelo sintético)
- [x] prefill único com tamanho de KV = fórmula do livro — esperado: 176640; observado: 176640
- [x] prefixo não recalculado: ramo KV = cache-base + pergunta + gerados − 1 — esperado: True em todas; observado: [(385, 345, True), (373, 345, True), (380, 345, True)]
- [x] ramo KV usado e cache-base restaurado a cada pergunta — esperado: True em todas; observado: [(True, True), (True, True), (True, True)]
- [x] saídas quente × frio idênticas (decodificação gulosa) — esperado: True em todas; observado: [True, True, True]
- [x] cache antigo recusado após mudança do corpus — esperado: True; observado: True
- [x] rótulo honesto: qualidade não avaliada — esperado: False; observado: False

### CEN-11 — Estrutura, metadados e limites da skill
- [x] cabeçalho entre --- no início do SKILL.md — esperado: presente; observado: presente
- [x] nome kebab-case igual ao canônico fundacao-ia-multiprojetos — esperado: fundacao-ia-multiprojetos; observado: fundacao-ia-multiprojetos (pasta: fundacao-ia-multiprojetos)
- [x] descrição ≤ 1024 caracteres e sem < > — esperado: ≤1024; observado: 852
- [x] chaves de cabeçalho aceitas pelo padrão e pelo validador do Chat/Work — esperado: name, description, license, metadata (compatibility dentro de metadata, até 500 caracteres); observado: ['description', 'license', 'metadata', 'name']
- [x] metadata como mapa de textos — esperado: todos str; observado: {'version': 'str', 'owner': 'str', 'compatibility': 'str', 'source': 'str', 'last_verified': 'str', 'freshness_window': 'str', 'freshness_category': 'str', 'verified_against': 'str'}
- [x] SKILL.md enxuto (< 500 linhas) — esperado: < 500; observado: 252
- [x] um único SKILL.md no pacote — esperado: 0; observado: []
- [x] sem artefatos de compilação na skill — esperado: 0; observado: []
- [x] quick_validate do skill-creator — esperado: Skill is valid!; observado: Skill is valid!
- [x] varredura de injeção do book-to-skill sobre todos os Markdown; achados revisados em contexto — esperado: 56 arquivos; nenhum SKIP; 0 achados não revisados; observado: achados=[('references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md', '120', 'tool.exfiltration_shape')]; não revisados=[] (arquivos: 56; revisados: ['exemplos de regras deny para .env/segredos e limite de Bash(curl): conteúdo defensivo'])

### CEN-12 — Conformidade do kit em instalação limpa
- [x] suíte de conformidade passa — esperado: OK; observado: OK (skipped=7) (testes: 418)

### CEN-13 — Hooks preventivos: escrita fora do projeto e troca de identidade negadas
- [x] escrita dentro do projeto autenticado segue o fluxo normal — esperado: sem_decisao; observado: sem_decisao
- [x] 0 em 10 tentativas indevidas passam (Write, Edit, '..', MCP, NotebookEdit) — esperado: 10 negadas; observado: 10
- [x] o matcher documentado encaminha ao hook todas as ferramentas testadas (inclusive MCP) — esperado: 5 de 5; observado: matcher='Edit|Write|MultiEdit|NotebookEdit|mcp__.*'; 5 de 5
- [x] sem projeto autenticado: falha fechada — esperado: deny; observado: deny
- [x] evento malformado: falha fechada — esperado: deny; observado: deny
- [x] leitura de arquivo não é bloqueada por este hook — esperado: sem_decisao; observado: sem_decisao
- [x] troca de identidade pela sessão é negada (bash, cmd, PowerShell) — esperado: 5 negadas; observado: 5
- [x] comando comum segue; laboratório pode liberar a troca explicitamente — esperado: sem_decisao; sem_decisao; observado: sem_decisao; sem_decisao
- [x] sem PYTHONUTF8 (página de código legada), a saída segue válida e a negativa vale — esperado: códigos 0; deny, deny; observado: 0, 0; ['deny', 'deny']
- [x] limite declarado confirmado: nome montado em tempo de execução passa pelo hook de identidade — esperado: sem_decisao (guarda-corpo, não barreira); observado: sem_decisao
- [x] ler FUNDACAO_PRINCIPAL segue; Set-Item, ${env:...}= e Remove-Item são negados (AF-07) — esperado: sem_decisao; 4 negadas; observado: sem_decisao; 4 negadas
- [x] aspas, -Path:/-Path=, Env:\, Remove-Item entre aspas, += e New-Item -Name são negados; Get-ChildItem e -eq seguem (CF-01) — esperado: 8 negadas; 2 livres; observado: 8 negadas; 2 livres (passaram: [])
- [x] padrão mcp__ccd_* libera as ferramentas do host; nome exato libera; outra MCP continua negada (AF-08) — esperado: sem_decisao; sem_decisao; deny; observado: sem_decisao; sem_decisao; deny

### CEN-14 — Matriz de requisitos: estados honestos aplicados
- [x] matriz inicial válida (60 linhas em desenvolvimento) — esperado: ok; observado: O caminho fica na base, sem '..' e sem passar por ligação; a leitura tem teto"
}
- [x] violações detectadas (simulação, inativo sem demonstração, bloqueio sem impacto, estado inventado, id do livro e id da 3.0 removidos) — esperado: todas; observado: {'R12': True, 'R33': True, 'R34': True, 'R01': True, 'R05': True, 'R57': True}
- [x] relatório começa pelos bloqueados (ordem da A36) — esperado: R34 primeiro; observado: R34

### CEN-15 — MCP local: descoberta, chamada autorizada, negativa entre projetos e encerramento
- [x] descoberta das ferramentas do servidor da fundação — esperado: listar_projetos, listar_documentos, buscar; observado: ['buscar', 'listar_documentos', 'listar_projetos']
- [x] chamada autorizada devolve só o próprio projeto — esperado: ['doc-aurora-01']; observado: ['doc-aurora-01']
- [x] negativa entre projetos sem conteúdo alheio — esperado: erro com 'acesso negado'; sem 'doc-eng-segredo-fic'; observado: Error executing tool listar_documentos: acesso negado
- [x] negativa registrada na trilha da fundação — esperado: >= 1; observado: 1
- [x] sessão encerrada e ensaio concluído — esperado: código 0; encerrado; observado: 0; True
- [x] versão de protocolo negociada e servidor identificados — esperado: protocolo presente; servidor da fundação; observado: 2026-07-28; {'nome': 'fundacao-ia-multiprojetos', 'versao': '1.7.7'}

### CEN-16 — Atualização do kit numa fundação existente (conflito, substituição com retorno)
- [x] sem --atualizar: nada é escrito, a diferença fica preservada e a saída não é sucesso (F15) — esperado: código 3; conflito em fundacao/__init__.py; nada escrito; versão declarada nula; no destino 0.9.0; observado: 3; ['fundacao/__init__.py']; True; None; 0.9.0
- [x] com --atualizar: substitui, guarda a versão anterior e registra a versão instalada — esperado: substituído; cópia anterior guardada; versão = a do kit; observado: ['fundacao/__init__.py']; guardado=True; 1.7.7
- [x] reexecução depois da atualização não muda nada — esperado: 0 copiados, 0 conflitos, 0 substituídos; observado: 0, 0, 0
- [x] depois de atualizar, o backup pede `init`; com ele, o registro ganha identidade e o backup volta — esperado: código 2 'rode `init`'; init 0; backup 0 com a identidade anotada; observado: 2; 0; 0
