#!/usr/bin/env python3
"""Gera a matriz de rastreabilidade R01–R60 em três saídas a partir de uma fonte única:

  entrega/rastreabilidade/MATRIZ-RASTREABILIDADE.md   (completa, para auditoria)
  entrega/rastreabilidade/MATRIZ-RASTREABILIDADE.csv  (mesmos dados, planilha)
  <skill>/references/requisitos.md                    (versão compacta usada pela skill)

Uso: python gerar_rastreabilidade.py <pasta-entrega> <pasta-skill>
"""
import csv
import re
import sys
from pathlib import Path

K = "assets/fundacao-kit/tests/"
CAP = "references/capacidades/"

# id: (requisito, origem [aulas e páginas], interpretação, arquivos da skill, aceite,
#      cenários, dependências/limitações, adaptação pedagógica, natureza, estado nesta entrega)
R = {
"R01": ("Núcleo comum com responsabilidades e contratos definidos",
        "Ap. B p188; A04 'Arquitetura como distribuição de responsabilidades' p20–21; A06 'O núcleo e suas fronteiras' p32–33",
        "Núcleo independente de domínio com contratos explícitos (projeto, tarefa, componente, evidência, memória); nenhuma regra de domínio no núcleo; uma tarefa atravessa os componentes previstos.",
        "SKILL.md §3; references/principios-e-evidencias.md §6; references/fluxo-a-implantar.md A2/A5; assets/templates/CONTRATO.schema.json; assets/fundacao-kit/fundacao/core/",
        "Inventário, arquitetura e uma execução que atravessa projeto→tarefa→componente→evidência; busca por termos de domínio no núcleo = 0.",
        "CEN-01; CEN-12; E1",
        "Kit = composição didática Python+SQLite; outra stack deve cumprir os mesmos contratos e cenários.",
        "—", "Livro + decisão (kit)",
        "Procedimento escrito; kit executado em ambiente descartável"),
"R02": ("Projetos criados por um modelo reutilizável",
        "Ap. B p188; A06 p32; A07 'Modelo, instância e configuração' p36–38; A30 p154; A36 situação 4 p179",
        "Gerador com lista positiva, identidade estável, configuração validada, armazenamento próprio, criação atômica; repetição informa existência sem sobrescrever; modelo ≠ migração de instâncias.",
        "references/fluxo-a-implantar.md A6–A7; references/fluxo-c-operar.md C5; assets/fundacao-kit/fundacao/core/projects.py; assets/fundacao-kit/templates/project/",
        "Projeto vazio com identificador próprio, configuração válida e nenhuma cópia de dados de outro projeto; segunda criação preserva a existente.",
        "CEN-01; CEN-03; " + K + "test_nucleo_projetos.py (TestModeloDeProjeto); E1",
        "Identificadores canônicos [a-z0-9-]; nomes reservados do Windows recusados.",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R03": ("Dependências identificadas e reproduzíveis",
        "Ap. B p188; A03 p16–18; A04B 'Como pesquisar um repositório' p25; A07 p38; Ap. D p201",
        "Versões, origem e licença registradas; ambiente reconstruído a partir do conjunto aprovado (venv recriável; lock/hashes quando houver).",
        CAP + "11-manutencao-recuperacao.md §Dependências; references/fluxo-a-implantar.md A3; scripts/instalar_kit.py (kit_install.json com versões e hashes); scripts/inspecionar_ambiente.py",
        "Registro de versões/origem/licença + reconstrução em pasta nova com o conjunto aprovado e teste mínimo passando.",
        "CEN-01 (instalação idempotente com registro); CEN-12 (instalação limpa executa os testes)",
        "Kit só usa biblioteca padrão (reprodutível por construção); dependências externas exigem rede e autorização.",
        "—", "Livro + 3.0 (uv)", "Procedimento escrito; reconstrução do kit executada"),
"R04": ("Separação entre fundação, projeto e tarefa",
        "Ap. B p188; A06 'Testes que você deve compreender' p34; A14 derivados p81; A30 'Falhas, repetição e isolamento' p156",
        "Toda leitura/escrita passa pela autorização do serviço (identidade × ação × recurso: comum/projeto/caso); tarefas e artefatos derivados herdam o escopo; negativa antes da leitura.",
        "references/seguranca-isolamento.md; SKILL.md §3 regra 2–3; assets/fundacao-kit/fundacao/core/auth.py, tasks.py, memory.py, knowledge.py",
        "Tentativas entre os dois projetos e entre tarefas com permissões diferentes, incluindo derivados, negadas sem revelar conteúdo nem metadados (existência, nomes, contagens).",
        "CEN-07; " + K + "test_nucleo_projetos.py (TestFronteiras); test_memoria.py; test_conhecimento.py; test_metadados.py; test_cli_autorizacao.py; E1; E7",
        "Identidades simuladas provam a lógica da política; isolamento real exige contas/permissões do SO, sandbox e hooks preventivos.",
        "—", "Livro", "Procedimento escrito; lógica executada (isolamento real pendente no ambiente do usuário)"),
"R05": ("Escolha de orquestração fundamentada",
        "Ap. B p188; A04 'Matriz de decisão sem notas inventadas' p21; A04B p24–27; 3.0 R3.1–R3.2",
        "Comparação datada (fontes oficiais, versão, licença) e dois protótipos isolados com os mesmos comportamentos de referência (normal, falha após efeito, troca de adaptador, projeto sem acesso).",
        CAP + "01-orquestracao.md §Escolha; references/fluxo-a-implantar.md A3; assets/templates/DECISAO.md",
        "DECISAO-002 com matriz ponderada, fontes datadas, dois protótipos e o teste capaz de refutar a escolha.",
        "E1 (decisão registrada); protótipo 'núcleo próprio' coberto por " + K + "test_orquestracao.py, test_eventos_rotas.py, test_nucleo_projetos.py",
        "Protótipo de framework externo (LangGraph/DBOS etc.) exige instalação autorizada; sem ela, comparação documental + experimento pendente (regra do livro p26).",
        "—", "Livro + 3.0", "Procedimento escrito; segundo protótipo pendente (instalação)"),
"R06": ("Tarefas, estados, dependências e resultados coordenados",
        "Ap. B p188; A09 'Orquestração é coordenação com regras' p44–46; A10 p50",
        "Fluxo como dados; máquina de estados formal; dependências respeitadas; contratos de entrada/saída; transições registradas como eventos.",
        CAP + "01-orquestracao.md; assets/fundacao-kit/fundacao/core/tasks.py",
        "Fluxo executado em ordem correta com transições registradas; ciclos e dependências inexistentes rejeitados.",
        K + "test_orquestracao.py; CEN-06",
        "—", "—", "Livro + 3.0 (máquina formal)", "Procedimento escrito; kit executado"),
"R07": ("Pausa e decisão humana vinculadas ao trabalho certo",
        "Ap. B p188; A09 laboratório passo 7 p46; A23 revisão ética pendente p122; Ap. E §7 p208",
        "Etapa waiting_human com opções concretas; decisão vinculada ao hash do conteúdo apresentado e à identidade autenticada; conteúdo alterado invalida a aprovação; independentes seguem. Com dados reais, aceite, correção e rejeição da entrega exata valem com a assinatura ssh-keygen -Y do titular conferida contra a âncora fora do alcance do executor (1.6.0), e a tarefa só termina com o aceite válido, registrado e mais recente.",
        CAP + "01-orquestracao.md item 7; references/autonomia-e-escalonamento.md §5; references/seguranca-isolamento.md §2; assets/templates/APROVACAO.json; Coordinator.decide; fundacao/core/decisoes.py (decisao preparar|verificar|registrar|conferir-ancora; tarefa concluir); registry/politica-decisoes.json",
        "Execução para no ponto definido; aprovação válida segue; hash divergente recusado. Decisão sem assinatura, de outra chave, em outro namespace ou alterada é recusada; registrar de novo responde já registrada; tarefa concluída só pelo aceite válido.",
        K + "test_orquestracao.py (TestDecisaoHumana); " + K + "test_decisoes.py, test_decisoes_comando.py, "
        "test_decisoes_politica.py, test_decisoes_cli.py e test_decisoes_concluir.py (chave e âncora de ensaio); CEN-06",
        "Aprovador humano real depende de identidade autenticada no ambiente. A conferência da assinatura roda no executor: a prova independente é o titular repetir ssh-keygen -Y verify; a barreira protege as decisões, não isola projetos.",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R08": ("Falha, repetição e retomada controladas",
        "Ap. B p188; A09 'O que um checkpoint precisa guardar' p45–47; A35 p177",
        "Checkpoints com hashes; saída conferida pelo hash do banco antes de ser reaproveitada (sumiu ou mudou: etapa e derivadas refeitas); posse por geração, com arquivo próprio por execução; limite de tentativas; erros permanentes não repetidos; saída gravada sem confirmação reconciliada só se o banco a reservou para aquela geração e os bytes conferem (o recibo é registro, não prova); retomada pelo mesmo run_id sem repetir efeitos.",
        CAP + "01-orquestracao.md; references/fluxo-c-operar.md C4; scripts/retomada.py; assets/templates/RETOMADA.md",
        "Falha induzida, limite respeitado e retomada que não reexecuta etapa concluída (contagem de execuções = 1).",
        K + "test_orquestracao.py (TestRetomada); CEN-06; E6",
        "Execução única não é prometida para serviços externos sem chave de idempotência do destino. Migração: etapa deixada em `running` pelo kit anterior é refeita quando a posse vence — reconcilie efeitos externos antes de retomar.",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R09": ("Papéis com entradas, saídas, ferramentas e limites",
        "Ap. B p188; A10 'Delegação útil tem entrada e saída delimitadas' p48–49",
        "Pacote de delegação por papel (objetivo, arquivos permitidos, ferramentas, limites, prazo, orçamento, formato, regra para falta de evidência); a tarefa recebe só o contexto necessário.",
        CAP + "02-agentes-subagentes.md; StepContext do kit (só entradas declaradas e saídas das dependências)",
        "Definições dos papéis + demonstração de que um papel não recebe fontes/permissões fora do pacote.",
        "Cenário de aceite A10 (defeitos plantados) no ambiente do usuário; " + K + "test_orquestracao.py (entradas declaradas)",
        "Subagentes nativos (Claude Code/Codex) dependem do host e consomem a mesma cota.",
        "—", "Livro", "Procedimento escrito; demonstração com subagentes reais pendente"),
"R10": ("Delegação e paralelismo com independência real",
        "Ap. B p188; A10 laboratório passos 3 e 'Evidências positivas e negativas' p49–50",
        "Duas tarefas independentes executam em paralelo com limite de concorrência (prova por sobreposição de horários); a dependente aguarda o pré-requisito.",
        CAP + "02-agentes-subagentes.md; Coordinator.run(max_parallel=N) com evento step_timing",
        "Horários de início/fim com sobreposição real das independentes; consolidador inicia após ambas.",
        K + "test_orquestracao.py (TestParalelismo)",
        "Paralelismo de agentes de IA reais depende do host e do orçamento; o kit demonstra o mecanismo de coordenação.",
        "—", "Livro", "Procedimento escrito; mecanismo executado (kit)"),
"R11": ("Consolidação, revisão e tratamento de divergências",
        "Ap. B p189; A10 'Exemplo: a divergência que deve aparecer' p49–51; A23 p122",
        "Consolidado atribuído; revisor confere nas fontes originais; divergência resolvida por evidência, com registro de conflito/correção/decisão sem apagar a origem; rodada de correção limitada.",
        CAP + "02-agentes-subagentes.md; references/livro/m03-execucao.md (exemplo trabalhado)",
        "Revisor detecta os defeitos plantados (data de emissão × evento; afirmação sem fonte) e o consolidado registra a correção.",
        "Cenário de aceite A10 no ambiente do usuário; E2 (comparação antes/depois registrada)",
        "Exige agentes reais (LLM); não executado nesta entrega.",
        "Exercício 'três agentes concordam' → antipadrão/verificação", "Livro", "Procedimento escrito; execução pendente"),
"R12": ('Participação funcional de dois provedores autorizados',
        'Ap. B p189; A03 p16–17; A08 p40–43; A13; 3.0 §5.4 (+A12)',
        'Duas rotas reais distintas (ex.: Claude Code e Codex) pela fundação, cada uma com identidade do provedor, mecanismo permitido, resultado preservado; simulação separada.',
        'references/capacidades/03-provedores-modelos.md; assets/fundacao-kit/fundacao/adapters/cli.py; references/fontes-verificadas.md §1–2',
        'Duas respostas reais com palavra de controle, ligadas à tarefa e à rota; dois adaptadores para o mesmo serviço não contam.',
        'Ensaio real de 4 chamadas no ambiente do usuário; simulação rotulada em assets/fundacao-kit/tests/test_eventos_rotas.py',
        'Consome cota/créditos do titular; termos de uso (pessoal × produto) e conflito oficial sobre créditos do Max. Adaptadores CLI isolados (pasta vazia, prompt pela entrada padrão, ambiente mínimo sem FUNDACAO_* nem chaves de API, sem ferramentas/MCP/configuração do usuário; opções conferidas na documentação e no --help das versões instaladas em 18/10/2026; não executados com provedor): antes de liberar, provar com documento-canário de outro projeto.',
        '—',
        'Livro + 3.0',
        'Bloqueado nesta entrega: autorização para chamadas reais'),

"R13": ("Modelo e esforço selecionados por tarefa",
        "Ap. B p189; A08 p40; A21 'Onde economizar' p112; 3.0 R1.1",
        "Política de rotas por tipo de tarefa (route_policy.json) com justificativa, orçamento e comparação de qualidade nas tarefas representativas; tipo não declarado falha fechado.",
        CAP + "03-provedores-modelos.md §Seletor; " + CAP + "09-consumo-qualidade.md; assets/fundacao-kit/registry/route_policy.json; fundacao/core/routing.py",
        "Política aplicada (rota restrita ao titular; sigiloso só local) + comparação de qualidade com medidas comparáveis.",
        K + "test_eventos_rotas.py (TestRotas); comparação de qualidade no ambiente do usuário",
        "Comparação de modelos exige chamadas reais autorizadas.",
        "—", "Livro + 3.0", "Política executada (kit); comparação de qualidade pendente"),
"R14": ('Alternativa em caso de indisponibilidade',
        "Ap. B p189; A08 quadro de situações p40–41; A09 p47; A34 'Substituição por contrato' p171",
        'Falha da rota principal leva à próxima rota AUTORIZADA; cada tentativa registrada; sem repetição infinita; sem envio a destino não autorizado; caso contrário, bloqueio.',
        'references/capacidades/03-provedores-modelos.md; fundacao/core/routing.py',
        'Falha controlada do principal → alternativa autorizada executa, ou tarefa bloqueada sem repetição.',
        'assets/fundacao-kit/tests/test_eventos_rotas.py (TestRotas: alternativa e bloqueio)',
        'Demonstração com adaptadores simulados rotulados; com provedores reais, exige autorização.',
        '—',
        'Livro',
        'Parcial: mecanismo de alternativa executado só com simulação rotulada; com provedores reais depende do R12 (bloqueado)'),

"R15": ("Modalidade, continuidade e cobrança identificadas",
        "Ap. B p189; A03 'Três modalidades de trabalho' p16; A08 p40–41; A13; 3.0 R1.6 (+A12)",
        "Cada resultado registra rota (assinatura/créditos/API/local/simulado), modo de integração (programática × transferência manual) e consumo normalizado; ausente ou inválido (custo negativo, NaN ou infinito) = 'unknown'.",
        CAP + "03-provedores-modelos.md; fundacao/core/usage.py; fundacao/adapters/base.py (ProviderResult.route, simulated)",
        "Registro distingue integração programática de transferência manual e discrimina assinatura, créditos confirmados e API.",
        K + "test_eventos_rotas.py (TestConsumo)",
        "Confirmação de créditos/cobrança depende das telas da conta do titular.",
        "—", "Livro + 3.0", "Normalização executada; observação de cobrança pendente"),
"R16": ("Memória externa persiste entre sessões",
        "Ap. B p189; A12 'Laboratório: escrever, encerrar e retomar' p73–74",
        "Registro externo com ID, revisão e origem recuperado após encerrar a sessão/processo, por leitura real do serviço.",
        CAP + "04-memoria.md; fundacao/core/memory.py",
        "Gravar, encerrar, abrir nova sessão e recuperar o mesmo ID, revisão e origem.",
        K + "test_memoria.py (persiste em nova sessão); " + K + "test_nucleo_projetos.py (tarefa após reinício do processo)",
        "Leitura por provedor de IA em nova sessão exige integração (ver R17).",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R17": ('Continuidade entre provedores',
        'Ap. B p189; A13 p76–79; A08 laboratório passo 4 p41; 3.0: A12 p73',
        'Provedor B lê o estado persistido por A (artefato/memória com identificador), identifica pendências e prossegue sem reconstrução informal.',
        'references/capacidades/04-memoria.md; references/capacidades/03-provedores-modelos.md (continuidade); references/fluxo-c-operar.md C4',
        'Provedor B, em sessão nova, lê o estado persistido por A, identifica as pendências registradas e prossegue sem reconstrução informal do histórico (cita o identificador do artefato e as pendências).',
        'Ensaio real no ambiente do usuário',
        'Depende de R12 (dois provedores autorizados).',
        '—',
        'Livro + 3.0',
        'Bloqueado nesta entrega: depende de R12'),

"R18": ("Leitura e escrita respeitam identidade e escopo",
        "Ap. B p189; A12 p73–74; A13 p76–78; A14",
        "Identidade estabelecida fora do modelo; ACL aplicada antes de entregar conteúdo; texto pedindo outro projeto não concede acesso; escrita também autorizada.",
        "references/seguranca-isolamento.md; " + CAP + "04-memoria.md; fundacao/core/memory.py, auth.py",
        "Positivos e negativos com marcadores; nenhum marcador alheio em saída, contexto ou log; recurso alheio responde igual a inexistente.",
        K + "test_memoria.py; test_metadados.py; CEN-07; E7",
        "Identidades simuladas = lógica; isolamento real exige SO/sandbox.",
        "—", "Livro", "Lógica executada (kit)"),
"R19": ("Origem, versão, correção e concorrência controladas",
        "Ap. B p189; A12; A13; A14 'Duas IAs não podem corrigir às cegas' p81–82",
        "Histórico de revisões; correção vinculada à revisão anterior; revisão esperada detecta conflito; transação única (corrente + revisão + evento).",
        CAP + "04-memoria.md; fundacao/core/memory.py",
        "Histórico preservado; conflito detectado; falha antes do commit não grava metade.",
        K + "test_memoria.py (correção versionada, falha antes do commit)",
        "—", "—", "Livro", "Procedimento escrito; kit executado"),
"R20": ("Promoção para a base comum é aprovada e revogável",
        "Ap. B p189; A13 'Promover significa criar uma nova responsabilidade' p77–78; A14; A18",
        "Candidato depurado; aprovação ligada ao hash por papel de curadoria; publicação como novo registro; retirada da origem propaga à publicação.",
        CAP + "04-memoria.md item 8; references/fluxo-c-operar.md C7; MemoryService.request_promotion/decide_promotion/withdraw",
        "Aprovação do conteúdo exato; candidato alterado recusado; retirada da origem remove a publicação do consumo.",
        K + "test_memoria.py (promoção e retirada)",
        "Curador humano real depende de identidade autenticada.",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R21": ("Ingestão e preparação preservam a referência ao documento",
        "Ap. B p190; A16 'A unidade mínima de uma citação' p89–90",
        "Registro de origem (ID, versão, hash); texto preparado por página; trechos com ID determinístico, página/localizador, hash e receita.",
        CAP + "06-rag.md; fundacao/core/knowledge.py (register_source, prepare, index, split_pages)",
        "Documento conhecido vira trechos com identificador, versão, localizador e verificação do texto extraído.",
        K + "test_conhecimento.py",
        "Extração de formatos (PDF/OCR) é externa ao kit; texto vazio não conta como ingestão.",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R22": ("Recuperação seleciona contexto pertinente e autorizado",
        "Ap. B p190; A16 'Um índice que respeita o catálogo' p90–91; A17",
        "Busca FTS5 por projeto com autorização, estado aprovado e vigência aplicados no SQL antes do top-k; documentos de outro projeto ausentes de resultados e logs.",
        CAP + "06-rag.md; fundacao/core/knowledge.py (search)",
        "Consultas conhecidas retornam os trechos esperados; outro projeto não aparece.",
        K + "test_conhecimento.py; CEN-07",
        "Pertinência em corpus real exige gabarito maior (3.0: ≥ 50 perguntas).",
        "—", "Livro + 3.0", "Procedimento escrito; kit executado"),
"R23": ("Respostas apresentam referências verificáveis",
        "Ap. B p190; A17 'Fidelidade de citação e cobertura' p96; A23",
        "Cada afirmação relevante cita trecho existente, vigente e autorizado; suporte semântico revisado; sem citação não passa por denominador zero.",
        CAP + "06-rag.md §Avaliação; KnowledgeService.verify_citation",
        "Fidelidade e cobertura calculadas com denominadores; citação inexistente/retirada recusada.",
        K + "test_conhecimento.py (verify_citation); avaliação de respostas no ambiente do usuário",
        "Geração integrada exige provedor autorizado; sem ele, resposta extrativa rotulada.",
        "—", "Livro", "Verificação de existência executada; avaliação de respostas pendente"),
"R24": ("Atualização e exclusão atingem os derivados",
        "Ap. B p190; A18 'Seguir os derivados até o fim' p98–99; A20",
        "Grafo de dependências (consulta recursiva); retirada com marcador antes da limpeza; caches invalidados; tarefas em andamento revalidam.",
        CAP + "06-rag.md §Atualizar; " + CAP + "07-cag-caches.md §Invalidação; knowledge.withdraw/cleanup; cache.py",
        "Alteração/retirada invalida índice, contexto, memória derivada e caches identificados.",
        K + "test_conhecimento.py (retirada); test_cache_backup.py (TestCache)",
        "Armazenamentos externos sem eliminação imediata ficam como ação pendente registrada.",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R25": ("Recuperação e resposta são avaliadas separadamente",
        "Ap. B p190; A17 p94–97; A21",
        "Gabarito versionado com perguntas sem resposta, conflito e acesso negado; Recall@k/Precision@k na busca; fidelidade/cobertura/abstenção na resposta; erros por etapa.",
        CAP + "06-rag.md §Avaliação; references/livro/m05-gold-rag.md (gabarito Q01–Q08)",
        "Métricas separadas com denominadores e inspeção dos erros; conjunto reservado congelado.",
        K + "test_conhecimento.py (recall_at_k); rodada completa no ambiente do usuário",
        "Avaliação de respostas exige geração autorizada.",
        "—", "Livro + 3.0", "Métrica de busca executada; rodada completa pendente"),
"R26": ('Significado técnico e viabilidade do CAG demonstrados',
        "Ap. B p190; A19 'A definição técnica adotada' p102; 'Antes de executar: caber é uma condição concreta' p103",
        'Decisão que relaciona o mecanismo ao artigo arXiv 2412.15605 e ao kvcache.py; identifica modelo, contexto, memória (fórmula KV) e limitações reais.',
        'references/capacidades/07-cag-caches.md; scripts/cag_kv_demo.py (checagem de janela e estimativa KV); references/fontes-verificadas.md §5',
        'Registro de viabilidade com estimativa conferida contra o tamanho observado do cache.',
        'CEN-10 (fórmula = observado no modo sintético)',
        'Viabilidade com modelo real depende de pesos autorizados e hardware.',
        '—',
        'Livro',
        'Parcial: mecanismo e estimativa executados com modelo sintético; viabilidade com modelo real bloqueada (pesos não autorizados)'),

"R27": ("Reutilização real do contexto pré-processado funciona",
        "Ap. B p190; A19 'Laboratório: pré-processar uma vez' p104–105",
        "Prefill único; perguntas novas em ramificações do cache-base; execução fria × quente; restauração do estado-base; zero buscas por pergunta.",
        CAP + "07-cag-caches.md; scripts/cag_kv_demo.py",
        "Saídas quente × frio idênticas (gulosa), ramo KV usado, cache-base intacto, com modelo real e avaliação de respostas.",
        "CEN-10 (sintético); execução com modelo real no ambiente do usuário",
        "Modelo sintético prova o mecanismo, não a qualidade; download de pesos exige autorização.",
        "—", "Livro + 3.0", "Mecanismo executado (sintético); validação com modelo real bloqueada"),
"R28": ("Cache respeita isolamento e invalidação",
        "Ap. B p190; A20 p107–110",
        "Autorização atual antes de qualquer hit; chave com identidade, escopo e revisões; revogação vale antes do TTL; fonte retirada invalida; cache antigo de CAG recusado.",
        CAP + "07-cag-caches.md; fundacao/core/cache.py, revisions.py; scripts/cag_kv_demo.py --testar-invalidacao",
        "Hit/miss/inválido/negado registrados; revogação e retirada impedem reutilização; tentativa entre projetos negada.",
        K + "test_cache_backup.py (TestCache); CEN-07; CEN-10",
        "Cache de prefixo do provedor não tem limpeza manual (registrar limitação).",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R29": ("Curadoria usa critérios explícitos e reproduzíveis",
        "Ap. B p191; A15 'Uma rubrica que produz decisões' p85–86",
        "Rubrica de cinco critérios com evidência; preparação → verificação → revisão → decisão; rejeitado com motivo; quem prepara não aprova.",
        CAP + "05-gold.md; KnowledgeService.curate",
        "Exemplo reprovado (antes→após) com motivo e corrigido por nova transformação.",
        K + "test_conhecimento.py",
        "—", "—", "Livro", "Procedimento escrito; kit executado"),
"R30": ("Dados aprovados conservam origem e responsabilidade",
        "Ap. B p191; A15 'A ficha de admissão' p85",
        "Ficha com fonte, versão, localizador, escopo, responsável autenticado, hash do conteúdo aprovado, finalidade e revisão.",
        CAP + "05-gold.md; assets/templates/FONTE-PROVENIENCIA.json; source_version no kit",
        "Ficha permite reconstruir a admissão.",
        K + "test_conhecimento.py",
        "—", "—", "Livro + 3.0", "Procedimento escrito; kit executado"),
"R31": ("Correção e retirada chegam aos consumidores",
        "Ap. B p191; A18 p98–101; A20; A35 'A armadilha da fonte revogada' p175",
        "Alteração da fonte revela dependências; versão retirada não volta ao uso, inclusive após restaurar backup (registro de retiradas reaplicado).",
        CAP + "05-gold.md; " + CAP + "11-manutencao-recuperacao.md; fundacao/core/backup.py (restore)",
        "Retirada posterior ao snapshot reaplicada antes de liberar; sem registro, ou com registro de outra fundação, ilegível ou truncado, a restauração não é liberada.",
        K + "test_cache_backup.py (TestBackupRestauracao); test_restauracao.py; CEN-09",
        "Registro de retiradas precisa existir fora da máquina em produção (3.0 R13.1).",
        "—", "Livro", "Procedimento escrito; kit executado"),
"R32": ("Componentes possuem inventário, versão e escopo",
        "Ap. B p191; A11 'O que torna um componente reutilizável' p52–55; A34",
        "Registro com finalidade, origem, dependências, permissões, custo, responsável, projetos autorizados e procedimento de retorno; descoberta sem execução.",
        CAP + "08-ferramentas-hooks-mcp-skills-plugins.md §1; assets/templates/INVENTARIO-COMPONENTE.json; fundacao/core/components.py",
        "Inventário lista estado sem importar o componente; registro ligado a evidências.",
        K + "test_componentes.py",
        "—", "—", "Livro", "Procedimento escrito; kit executado"),
"R33": ("Hook executa apenas no evento e escopo previstos",
        "Ap. B p191; A11B p56–59; 3.0 R4.1–R4.6",
        "Hook preventivo (PreToolUse deny) e observador idempotente; dispara uma vez no evento autorizado; não dispara fora do escopo nem desativado; timeout registrado.",
        CAP + "08-ferramentas-hooks-mcp-skills-plugins.md §2; assets/hooks/guarda_caminho.py; references/fontes-verificadas.md §1",
        "Disparo real pelo produto, idempotência e desligamento comprovados.",
        "CEN-13 (lógica do hook com eventos simulados); disparo nativo no ambiente do usuário",
        "Instalar hook altera a configuração do host; correção: filtro Write(...) não é consultado.",
        "—", "Livro + 3.0 + verificação", "Lógica executada; disparo nativo pendente (configurar host)"),
"R34": ('MCP funciona como protocolo entre cliente e servidor',
        'Ap. B p191; A11C p60–63; 3.0 R4.7–R4.13',
        'Servidor oficial (SDK 2.x) com ferramenta ligada ao mesmo serviço e autorização; conexão real, descoberta, chamada, negativa, desligamento e encerramento observados.',
        'references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md §3; assets/fundacao-kit/fundacao/mcp_servidor.py; scripts/mcp_ensaio.py',
        'Troca real pelo protocolo com versão negociada registrada e negativa entre projetos pela rota MCP.',
        'CEN-15 (stdio, processo separado); assets/fundacao-kit/tests/test_mcp.py (em processo)',
        'SDK mcp presente neste ambiente (2.3.0); em outro ambiente, instalar exige autorização e venv isolada. Registrar o servidor no host altera a configuração do usuário (decisão dele).',
        '—',
        'Livro + 3.0 + verificação',
        'Parcial: executado real-local (SDK mcp 2.3.0, stdio, versão negociada 2026-07-28 registrada, descoberta, chamada, negativa entre projetos, encerramento); desligamento pelo host e registro no host pendentes'),




"R35": ("Skills comuns e específicas são descobertas e usadas",
        "Ap. B p191; A11D p64–67",
        "Skill comum com fonte canônica e skill específica do projeto; descoberta, invocação, não seleção fora do escopo, atualização comparada e desativação no host.",
        CAP + "08-ferramentas-hooks-mcp-skills-plugins.md §4; assets/templates/COMPATIBILIDADE-HOSTS.md",
        "Execução das duas skills em escopos adequados, versões identificadas, sem vazamento.",
        "Ensaio no ambiente do usuário; esta própria skill passou pela validação de formato (CEN-11)",
        "Descoberta/execução reais dependem do host.",
        "—", "Livro + verificação", "Procedimento escrito; execução pendente"),
"R36": ("Plugin é instalado, atualizado e desativado de modo verificável",
        "Ap. B p191; A11E p68–71; A34",
        "Catálogo local e plugin validados (claude plugin validate), instalados no escopo local, atualizados, desativados e removidos com evidência; acesso a dados continua autorizado pelo serviço.",
        CAP + "08-ferramentas-hooks-mcp-skills-plugins.md §5",
        "Listagem instalada, execução, versão carregada, desativação sem disparos/processos.",
        "Ensaio no ambiente do usuário",
        "Instalação altera a configuração do host; exige autorização.",
        "—", "Livro + verificação", "Procedimento escrito; execução pendente"),
"R37": ("Contexto é carregado conforme a necessidade",
        "Ap. B p191; A16; A21 'Onde economizar antes de acrescentar dependências' p112",
        "Seleção de trechos pela finalidade em vez de contexto integral, com referências preservadas; comparação integral × seleção.",
        CAP + "09-consumo-qualidade.md; " + CAP + "06-rag.md",
        "Comparação preserva respostas e referências relevantes com menos entrada.",
        "Rodada de comparação no ambiente do usuário",
        "Contagem exata de tokens depende do tokenizador/contadores do provedor.",
        "—", "Livro", "Procedimento escrito; comparação pendente"),
"R38": ("Reduções preservam significado e são reversíveis quando necessário",
        "Ap. B p191; A21 laboratório passo 4 p113",
        "Compressão protege números, datas, unidades, negações, exceções e identificadores; ligação ao original recuperável; teste detecta perda.",
        CAP + "09-consumo-qualidade.md",
        "Teste que recupera detalhe omitido do original e detecta perda de ressalva/número/condição.",
        "Ensaio no ambiente do usuário",
        "Ferramentas de compressão (ex.: Headroom) não verificadas.",
        "—", "Livro", "Procedimento escrito; execução pendente"),
"R39": ('Orçamento e limite de repetição produzem efeito',
        'Ap. B p192; A08 p41; A09 p45–47; A21',
        'Teto de chamadas e tempo por execução (prazo gravado na 1ª execução, conferido em cada débito e não renovado na retomada); custo só como Decimal finito ≥ 0 (inválido = não medido); tentativas máximas; regra de interrupção; evento registrado; chamada excedente não ocorre.',
        'references/capacidades/09-consumo-qualidade.md §Orçamento; Budget/StepContext.charge_call',
        'Tarefa que atingiria o limite é interrompida antes da chamada excedente.',
        'assets/fundacao-kit/tests/test_orquestracao.py (orçamento, tentativas); test_adaptadores_rotas.py (tetos por rota: custo, chamadas, custo não medido até reconciliar; tentativa que não saiu não conta)',
        '—',
        '—',
        'Livro',
        'Procedimento escrito; kit executado'),

"R40": ("Consumo, qualidade e tempo são comparados com método",
        "Ap. B p192; A21 p111–114",
        "Mesmas tarefas e configuração; execuções alternadas e repetidas; mediana e dispersão; medição × estimativa × faturamento; Headroom avaliado quando viável.",
        CAP + "09-consumo-qualidade.md; fundacao/core/usage.py",
        "Dados brutos, cálculos com denominadores e decisão manter/ajustar/retirar.",
        "Rodada no ambiente do usuário",
        "Exige chamadas reais e contadores.",
        "—", "Livro + 3.0", "Procedimento escrito; execução pendente"),
"R41": ("Uma execução pode ser reconstruída pelos registros",
        "Ap. B p192; A09; A32 'Logs, métricas e rastros' p163",
        "Identificadores ligam tarefa, execução, etapas, provedor, eventos, artefatos, falhas e consumo; trilha encadeada; acesso conforme o projeto.",
        CAP + "10-observabilidade-conversa.md; fundacao/core/events.py",
        "Reconstrução por run_id; adulteração de evento detectada.",
        K + "test_eventos_rotas.py (TestTrilha); CEN-06",
        "—", "—", "Livro + 3.0", "Procedimento escrito; kit executado"),
"R42": ("Testes detectam falhas por componente e por projeto",
        "Ap. B p192; A17; A25; A28; A30",
        "Casos positivos, negativos e de regressão cobrindo os dois projetos e suas fronteiras.",
        "assets/fundacao-kit/tests/ (238 testes); scripts/tests/ (62); evals/cenarios/run_cenarios.py",
        "Suíte executa em instalação limpa e falha diante de regressões.",
        "CEN-12; CEN-01 a CEN-16; regressão da auditoria final da 1.4.2: assets/fundacao-kit/tests/test_auditoria_final_1_4_2.py (AF-01, AF-09) e entrega/testes/test_auditoria_final_1_4_2.py (AF-02, AF-03, AF-04)",
        "CI em Windows e Ubuntu (R59) não configurado.",
        "—", "Livro", "Executado nesta entrega (Windows)"),
"R43": ('Diagnóstico e evidências são compreensíveis ao usuário',
        'Ap. B p192; A32; A36',
        'Relatório com esperado, observado, evidência, pendência e próximo passo, sem exigir leitura do log inteiro.',
        'assets/templates/RELATORIO-FINAL.md, EVIDENCIAS.md, AUDITORIA.md; scripts/matriz.py relatorio',
        "Usuário responde 'qual o estado real e o que falta' lendo o relatório.",
        'E1–E8 (critério de relatório nas avaliações)',
        'Compreensão final é avaliada pelo usuário.',
        '—',
        'Livro',
        'Depende do usuário: modelos de relatório e avaliações executados; a compreensão é avaliada pelo usuário'),

"R44": ("Existe um estado de referência recuperável",
        "Ap. B p192; A05 p28–31; A07",
        "Abrangência, identidade, preservação (Git + arquivos + backup SQLite + receita), restauração em pasta nova e prova negativa.",
        CAP + "11-manutencao-recuperacao.md; references/fluxo-a-implantar.md A4; scripts/manifesto.py, backup_sqlite.py",
        "Cópia, inventário e integridade conferidos antes da migração; diferenças provocadas detectadas.",
        "CEN-09; CEN-02 (origem inalterada); " + K + "test_cache_backup.py",
        "—", "—", "Livro", "Procedimento escrito; executado"),
"R45": ("Backup restaura a fundação em destino separado",
        "Ap. B p192; A07; A35 p174–177",
        "Restauração em destino novo com banco íntegro, dados esperados, permissões e registro de retiradas aplicado antes da abertura; a cópia leva kit, banco, projetos e os registros da fundação (`docs/`, `evidence/`, `ferramentas/`, `tests/`, `RETOMADA.md`; lista em `registry/backup_policy.json`) e é conferida por uma âncora guardada fora dela.",
        CAP + "11-manutencao-recuperacao.md; fundacao/core/backup.py",
        "Restauração liberada só após integridade (arquivos e banco conferidos contra o manifesto, e o manifesto contra a âncora `sha256_manifesto` ou o livro `state/copias.jsonl`), identidade do registro e reaplicação de retiradas, revogações e desativações (não liberada = código 3, sem copiar nada); ligação nas pastas copiadas não é seguida; restaurar sobre a origem é recusado; backup e restauração só pela administração; caminho com '#' e pasta de rede funcionam.",
        K + "test_cache_backup.py; test_cli_autorizacao.py; test_restauracao.py; test_backup_completo.py; CEN-09",
        "—", "—", "Livro", "Procedimento escrito; kit executado"),
"R46": ('Atualizações verificam compatibilidade',
        'Ap. B p192; A33 p167–169',
        'Atualização isolada, versões e migrações registradas (user_version), testes de contrato e retorno exercitado; modelo ≠ instância.',
        'references/capacidades/11-manutencao-recuperacao.md; references/fluxo-c-operar.md C6; scripts/atualizar_fundacao.py (`checar`; `aplicar`: backup antes, ensaio numa cópia restaurada, promoção, backup depois e registro; `desfazer`)',
        'Comparação antes/depois nos quatro contratos e retorno em ambiente isolado.',
        'assets/fundacao-kit/tests/test_nucleo_projetos.py (drift do modelo); ensaio de atualização no ambiente do usuário; CEN-16 (atualização do kit: conflito preservado, substituição com retorno, versão instalada); scripts/tests/test_atualizar_fundacao.py (versão antiga × alteração local, regressão no ensaio sem tocar a raiz, `desfazer`); assets/fundacao-kit/tests/test_auditoria_1_5_0_dados.py (banco da 1.4.1 aberto pelo kit novo)',
        '—',
        '—',
        'Livro + 3.0',
        'Parcial: atualização do kit executada (conflito, substituição com cópia de retorno, versão registrada) e drift do modelo; atualização de componente com consumidores reais pendente'),


"R47": ("Desativação e substituição são efetivas",
        "Ap. B p192; A34 p170–173",
        "Desligado não inicia ações nem consome; todas as rotas inventariadas verificadas; substituto cumpre o contrato com política equivalente.",
        CAP + "08-ferramentas-hooks-mcp-skills-plugins.md §1; references/fluxo-c-operar.md C8",
        "Zero despachos do desligado; substituição sem mudar regras dos projetos.",
        K + "test_componentes.py (desabilitado); test_eventos_rotas.py (alternativa)",
        "Rotas do host (hooks/plugins/agendadores) verificadas no ambiente do usuário.",
        "—", "Livro", "Mecanismo executado (kit); rotas do host pendentes"),
"R48": ("Recuperação retoma o trabalho sem repetir efeitos",
        "Ap. B p192; A35 'Exercício resolvido' p177",
        "Retomada do estado validado com revalidação de aprovações e reconciliação de efeitos externos já realizados.",
        CAP + "11-manutencao-recuperacao.md §Retomar; Coordinator.resume",
        "Etapa com recibo de efeito não é reexecutada após retomada/restauração.",
        K + "test_orquestracao.py (reconciliação); CEN-06",
        "—", "—", "Livro", "Procedimento escrito; kit executado"),
"R49": ("Um ponto principal recebe pedidos em linguagem natural",
        "Ap. B p193; A31 p159–162",
        "Entrada por conversa lista projetos permitidos, fixa projeto e versões na criação da tarefa e apresenta plano com escopo e resultado esperado.",
        CAP + "10-observabilidade-conversa.md; assets/templates/CONTRATO.schema.json; CLI do kit como entrada mínima",
        "Usuário escolhe projeto permitido, formula tarefa e recebe plano rastreável.",
        "Ensaio no ambiente do usuário",
        "Interface de conversa não faz parte do kit (trilha avançada na 3.0).",
        "—", "Livro", "Procedimento escrito; implementação pendente"),
"R50": ("Projetos, tarefas, resultados e pendências são visíveis",
        "Ap. B p193; A31; A32 'Um painel que ajuda a decidir' p163–164",
        "Visão resumida que corresponde ao estado persistido, abre evidências e mostra bloqueios.",
        CAP + "10-observabilidade-conversa.md; `python -m fundacao status`; scripts/matriz.py relatorio",
        "Visão bate com os registros brutos; bloqueios compreensíveis.",
        "CEN-01 (status); CEN-14 (relatório da matriz)",
        "Painel completo é trilha avançada.",
        "—", "Livro", "Visão mínima executada; painel pendente"),
"R51": ("O usuário administra a fundação com os materiais da skill",
        "Ap. B p193; A30; A36 'Duas avaliações independentes' p178–180",
        "Demonstração observada do usuário orientando tarefa, avaliando entrega, pedindo correção e criando outro projeto; registro descritivo do que foi demonstrado.",
        CAP + "10-observabilidade-conversa.md §R51; references/fluxo-c-operar.md C11",
        "Registro de decisões do usuário baseado em interação real.",
        "Ensaio com o usuário (por natureza)",
        "Não pode ser demonstrado pela IA sozinha.",
        "'Registro de aprendizagem' e 'tutor' → registro de decisões/entendimento do usuário e relatório ao usuário; 'materiais do curso' → 'materiais da skill'",
        "Livro (adaptado)", "Procedimento escrito; depende do usuário"),
"R52": ('Escrita fora do projeto bloqueada antes da execução',
        'Proposta 3.0 §5.4 (limiar: 0 em 10 tentativas, inclusive Edit e MCP)',
        'Hook PreToolUse que nega escrita fora de projects/<projeto autenticado>/ e ferramentas MCP de escrita não listadas; falha fechada sem projeto.',
        'assets/hooks/guarda_caminho.py; assets/host/windows/preparar-maquina.ps1 (instala os hooks e as negações na raiz); references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md §2; references/seguranca-isolamento.md',
        "0 permissões indevidas em 10 tentativas (Write, Edit, '..', MCP).",
        'CEN-13 (lógica do guarda de escrita e do guarda de identidade, matcher documentado, falha fechada); instalação no host testada em scripts/tests/test_host_windows.py e test_host_wsl.py; disparo nativo pendente',
        'Shell exige sandbox (WSL2); hook não é fronteira completa.',
        '—',
        '3.0',
        'Lógica executada; integração nativa pendente'),

"R53": ("Nenhum segredo legível pelo agente",
        "Proposta 3.0 §5.4 (varredura limpa; .env negado)",
        "permissions.deny para segredos; manifestos e backups excluem segredos; varredura antes de commit.",
        "references/seguranca-isolamento.md §5; scripts/manifesto.py (exclusão de segredos); fundacao/core/backup.py; assets/host/windows/settings.json e assets/host/wsl/settings.wsl.json (negações de segredos e de state/)",
        "Varredura limpa e leitura de .env negada pelo host.",
        "CEN-02 (manifesto exclui .env); perfis do host conferidos em scripts/tests/test_host_perfis.py; negação no host pendente",
        "Negação efetiva depende da configuração do host.",
        "—", "3.0", "Exclusão executada; negação no host pendente"),
"R54": ("Componentes externos fixados por versão e hash",
        "Proposta 3.0 §5.4 (100%)",
        "Registro de componentes com versão e hash; instalação do kit registra hashes; revisão de diff a cada atualização.",
        "assets/templates/INVENTARIO-COMPONENTE.json (pinned_hash); scripts/instalar_kit.py; dependência opcional `mcp`: requisitos com hashes e `--require-hashes` (references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md §3)",
        "Todos os componentes externos com versão e hash conferidos.",
        "CEN-01 (kit_install.json)",
        "Componentes de terceiros dependem do ambiente do usuário.",
        "—", "3.0", "Parcial (kit)"),
"R55": ("Treinamento desligado nas contas usadas, com evidência",
        "Proposta 3.0 §5.4 (evidência ≤ 90 dias)",
        "Titular desliga o uso de dados para treino nas contas e registra evidência datada.",
        "references/privacidade-sigilo.md; assets/templates/CHECKLIST-DADOS-REAIS.md",
        "Evidência datada nas contas usadas.",
        "Ação do titular",
        "Fatos sobre planos não verificados nesta skill.",
        "—", "3.0", "Depende do titular"),
"R56": ('Eliminação propagada a índice, cache, memória e backup',
        'Proposta 3.0 §5.4',
        'Retirada por marcador propagada a trechos, caches, memória derivada e reaplicada em restauração (com evento na trilha restaurada).',
        'references/capacidades/06-rag.md; references/capacidades/11-manutencao-recuperacao.md; knowledge.withdraw; memory.withdraw; backup.restore',
        'Teste de retirada passa em todos os locais inventariados.',
        'assets/fundacao-kit/tests/test_conhecimento.py; test_memoria.py; test_cache_backup.py; test_restauracao.py; CEN-09',
        'Eliminação física em armazenamentos externos fora do controle da fundação.',
        '—',
        '3.0',
        'Parcial: retirada executada e reaplicada em índice, cache, memória e restauração (kit, testada); eliminação física em armazenamentos externos pendente no ambiente do usuário'),


"R57": ("Eventos com trace_id, ts, schema_version e cadeia íntegra",
        "Proposta 3.0 §5.4",
        "Eventos com run_id/task_id, ts UTC, schema_version e prev_hash; verificação da cadeia.",
        CAP + "10-observabilidade-conversa.md; fundacao/core/events.py",
        "Verificação da cadeia sem quebras; adulteração detectada.",
        K + "test_eventos_rotas.py (TestTrilha)",
        "Ancoragem externa (commit assinado/carimbo) não implementada.",
        "—", "3.0", "Executado (kit)"),
"R58": ("Regressão automatizada",
        "Proposta 3.0 §5.4 (CI verde; n ≥ 5)",
        "Suíte de regressão executada a cada mudança; avaliações com repetições.",
        "assets/fundacao-kit/tests/; evals/",
        "CI verde e repetições por caso.",
        "CEN-12 (execução local); CI pública da cópia no GitHub (workflow `validar`, 5 rodadas por plataforma, desde a 1.7.0)",
        "O resultado da CI do commit publicado é conferido na liberação; repetições de avaliações com IA dependem de orçamento.",
        "—", "3.0", "Suíte local executada; CI pública configurada (resultado do commit publicado conferido na liberação)"),
"R59": ("Aceite em Windows e Ubuntu",
        "Proposta 3.0 §5.4 (100%)",
        "Mesma suíte em Windows e Ubuntu/WSL.",
        "assets/fundacao-kit/tests/",
        "100% nos dois sistemas.",
        "CEN-12 (Windows); CI pública (Windows e Ubuntu, desde a 1.7.0)",
        "Ubuntu pela CI pública, conferida na liberação; o WSL do titular continua fora dela.",
        "—", "3.0", "Windows executado aqui; Ubuntu pela CI pública (conferida na liberação)"),
"R60": ("Citações verificadas; número CNJ com dígito verificador válido",
        "Proposta 3.0 §5.4; R15.2",
        "Verificador determinístico de citações jurídicas (artigo na cópia oficial datada, trecho confere, DV do número CNJ módulo 97); jurisprudência sem fonte oficial = pendente.",
        "references/livro/m07-juridico.md (orientação)",
        "0 falhas no verificador.",
        "Implementação no projeto jurídico do usuário",
        "Não implementado no kit; exige fontes oficiais datadas.",
        "—", "3.0", "Procedimento descrito; implementação pendente"),
}

# Faixa de páginas de cada aula, conforme o sumário impresso (p5–7). Usada para completar
# citações de aula sem página (a seção específica, quando conhecida, já está no texto).
PAGINAS_AULA = {
    "A01": (8, 11), "A02": (12, 15), "A03": (16, 19), "A04": (20, 23), "A04B": (24, 27), "A05": (28, 31),
    "A06": (32, 35), "A07": (36, 39), "A08": (40, 43), "A09": (44, 47), "A10": (48, 51), "A11": (52, 55),
    "A11B": (56, 59), "A11C": (60, 63), "A11D": (64, 67), "A11E": (68, 71), "A12": (72, 75), "A13": (76, 79),
    "A14": (80, 83), "A15": (84, 88), "A16": (89, 93), "A17": (94, 97), "A18": (98, 101), "A19": (102, 106),
    "A20": (107, 110), "A21": (111, 114), "A22": (115, 118), "A23": (119, 123), "A24": (124, 127),
    "A25": (128, 132), "A26": (133, 138), "A27": (139, 143), "A28": (144, 148), "A29": (149, 153),
    "A30": (154, 158), "A31": (159, 162), "A32": (163, 166), "A33": (167, 169), "A34": (170, 173),
    "A35": (174, 177), "A36": (178, 181),
}


# Adaptação pedagógica por requisito: como a atividade de aprendizagem do livro virou
# procedimento, critério de aceite ou cenário desta skill (a finalidade é preservada).
ADAPTACAO = {
    'R01': "Laboratórios de arquitetura (A04) e de núcleo (A06) → etapas A2/A5 com critério de conclusão; a 'matriz de decisão' vira DECISAO.md; aceite por CEN-01/CEN-12.",
    'R02': 'Laboratório do modelo de projeto (A07) → gerador com lista positiva e criação atômica; o exercício de recriar vira teste de repetição (CEN-01/CEN-03).',
    'R03': 'Atividade de pesquisar repositórios (A04B) e inventário de versões (A03) → registro de versões/hashes na instalação (kit_install.json) e recriação limpa (CEN-12).',
    'R04': 'Exercícios de fronteira (A06, A14, A30) → provas negativas automatizadas com marcadores-canário e sondagem de metadados (CEN-07, test_metadados).',
    'R05': 'Comparação de abordagens com protótipos (A04, A04B) → etapa A3 com protótipo discriminante e decisão datada; a escolha do kit fica registrada como decisão substituível.',
    'R06': 'Laboratório de coordenação (A09) → máquina de estados testada (test_orquestracao) e cenário de falha/retomada (CEN-06).',
    'R07': 'Passo 7 do laboratório A09 e revisão ética da A23 → decisão humana ligada ao hash do conteúdo apresentado (TestDecisaoHumana).',
    'R08': "'O que um checkpoint precisa guardar' (A09) e exercício resolvido da A35 → recibo + reconciliação em processo novo (CEN-06, E6).",
    'R09': 'Pacote de delegação da A10 → contrato de papel em capacidades/02; o laboratório com defeitos plantados vira cenário de aceite no ambiente do usuário.',
    'R10': 'Passo 3 do laboratório A10 (paralelismo) → execução paralela só de etapas independentes, com horários registrados (TestParalelismo).',
    'R11': "Exercício 'três agentes concordam' → antipadrão e critério de aceite (revisor confere nas fontes); a atividade vira caso de verificação.",
    'R12': "Ensaio de duas rotas da A08 (4 chamadas) → procedimento com teto e comando pronto; mantido bloqueado até autorização (não simulado como 'real').",
    'R13': 'Quadro de escolha de modelo/esforço (A08, A21) → política de rotas por tipo de tarefa testada; a comparação de qualidade fica como rodada no ambiente do usuário.',
    'R14': 'Quadro de situações de falha (A08) → alternativa autorizada e bloqueio sem repetição testados com simulador rotulado; a prova com provedores reais depende do R12.',
    'R15': "'Três modalidades de trabalho' (A03) → registro que separa assinatura, CLI, API e SDK e normalização de consumo; a conferência de cobrança fica com o titular.",
    'R16': "Laboratório 'escrever, encerrar e retomar' (A12) → teste de persistência em processo novo (test_memoria).",
    'R17': 'Passo 4 do laboratório A08 e A13 → ensaio A→B com artefato persistido e pendências identificadas; bloqueado até haver dois provedores autorizados.',
    'R18': 'Exercícios de identidade e escopo (A12, A13) → negativas pelo serviço com identidade fora do modelo e sondagem indistinguível (test_memoria, test_metadados).',
    'R19': "'Duas IAs não podem corrigir às cegas' (A14) → revisão esperada que detecta conflito e histórico preservado (RevisionConflict).",
    'R20': 'Promoção da A13 → pedido, decisão por curador distinto e retirada que propaga; o exercício de revogação vira teste.',
    'R21': "'A unidade mínima de uma citação' (A16) → trechos com página, hash e receita (test_conhecimento).",
    'R22': "'Um índice que respeita o catálogo' (A16) → filtro de autorização antes do LIMIT e prova entre projetos (test_conhecimento, CEN-07).",
    'R23': "'Fidelidade de citação' (A17) → verificação de citação que recusa trecho retirado, alheio ou inexistente.",
    'R24': "'Seguir os derivados até o fim' (A18) → retirada com propagação por dependências e limpeza retomável.",
    'R25': 'Avaliação separada da A17 (gabarito Q01–Q08) → recall@k da recuperação separado da resposta; a rodada com provedor fica no ambiente do usuário.',
    'R26': "'A definição técnica adotada' e 'caber é uma condição' (A19) → fórmula do KV conferida no modo sintético; viabilidade com modelo real depende de pesos autorizados.",
    'R27': "Laboratório 'pré-processar uma vez' (A19) → demonstração frio × quente com prova de que o prefixo não é recalculado (CEN-10); qualidade não avaliada.",
    'R28': 'Laboratório de isolamento de caches (A20) → chave por identidade e revisões, negativa e invalidação testadas.',
    'R29': "'Uma rubrica que produz decisões' (A15) → rubrica de cinco critérios obrigatória na curadoria.",
    'R30': "'A ficha de admissão' (A15) → registro de origem, versão, hash e responsável; quem prepara não aprova.",
    'R31': 'Correção e retirada (A18, A20) → reaplicação de retiradas na restauração e invalidação de caches (CEN-09).',
    'R32': "'O que torna um componente reutilizável' (A11) → registro com versão, escopo e saúde, descoberta sem importar código.",
    'R33': 'Laboratório de hooks (A11B) → lógica do hook preventivo testada com eventos simulados; o disparo nativo no host fica para a instalação autorizada.',
    'R34': 'Laboratório MCP (A11C) → servidor de leitura da fundação ensaiado por stdio com o SDK oficial (CEN-15); o registro no host fica para a decisão do usuário.',
    'R35': 'Laboratório de skills (A11D) → esta própria skill (estrutura validada, acionamento simulado); skills de projeto seguem o mesmo procedimento.',
    'R36': 'Laboratório de plugins (A11E) → procedimento com validação, instalação, atualização e desativação; execução pendente por alterar o host.',
    'R37': "'Onde economizar' (A21) → carregamento sob demanda das referências desta skill e contexto mínimo por tarefa; medição no ambiente do usuário.",
    'R38': 'Passo 4 do laboratório A21 → redução com verificação de significado; ensaio no ambiente do usuário.',
    'R39': 'Orçamento da A08/A09 → teto de chamadas por execução e tetos por rota testados (test_orquestracao, test_adaptadores_rotas).',
    'R40': 'Comparação de consumo da A21 → método com medição × estimativa × desconhecido; rodada no ambiente do usuário.',
    'R41': "'Logs, métricas e rastros' (A32) → eventos encadeados que reconstroem a execução (TestTrilha).",
    'R42': 'Exercícios de teste (A17, A25) → suíte de conformidade e cenários executáveis (CEN-01–CEN-16).',
    'R43': 'Relatórios das aulas A32/A36 → modelos de relatório e avaliações; a compreensão final é julgada pelo usuário.',
    'R44': 'Laboratório de ponto de retorno (A05) → manifesto, backup consistente e restauração ensaiada com prova negativa (CEN-09).',
    'R45': 'Restauração da A35 → destino separado, autorização pela cópia e liberação só após reaplicar retiradas (CEN-09, test_restauracao).',
    'R46': 'Atualização da A33 → comparação de versões, drift do modelo e atualização do kit com retorno (CEN-16).',
    'R47': 'Habilitar/desabilitar/substituir (A34) → desativação efetiva testada (nenhum despacho quando desligado).',
    'R48': 'Exercício resolvido da A35 → retomada sem repetir efeito confirmado (CEN-06).',
    'R49': 'Entrada por conversa (A31) → procedimento em capacidades/10; ensaio no ambiente do usuário.',
    'R50': "'Um painel que ajuda a decidir' (A32) → status recortado pela identidade e relatório da matriz.",
    'R51': "'Registro de aprendizagem' e 'tutor' → registro de decisões e guia de operação; a avaliação independente é do usuário.",
    'R52': 'Proposta 3.0 → hook preventivo de escrita e de troca de identidade, com lógica testada (CEN-13).',
    'R53': 'Proposta 3.0 → manifesto que exclui segredos sem lê-los e regra de negação de leitura no host.',
    'R54': 'Proposta 3.0 → versões e hashes do kit registrados na instalação.',
    'R55': 'Proposta 3.0 → ação do titular nas contas; a skill registra a evidência exigida.',
    'R56': 'Proposta 3.0 → retirada propagada a índice, cache, memória e restauração, com testes.',
    'R57': 'Proposta 3.0 → eventos com esquema, horário e cadeia de hashes verificável.',
    'R58': 'Proposta 3.0 → regressão automatizada local (suíte e cenários).',
    'R59': 'Proposta 3.0 → aceite em Windows executado; Ubuntu pendente.',
    'R60': 'Proposta 3.0 → verificação de citações e número CNJ no projeto jurídico do usuário.',
}


def completar_paginas(origem: str) -> str:
    """Acrescenta a faixa de páginas da aula às citações 'Axx' que não trazem página."""
    partes = []
    for seg in origem.split(";"):
        m = re.match(r"^(\s*)(A\d\d[A-E]?)\b(.*)$", seg)
        if m and m.group(2) in PAGINAS_AULA and not re.search(r"\bp\.?\s?\d", m.group(3)):
            lo, hi = PAGINAS_AULA[m.group(2)]
            seg = f"{m.group(1)}{m.group(2)} p{lo}–{hi}{m.group(3)}"
        partes.append(seg)
    return ";".join(partes)


# Regressões da auditoria externa da 1.3.4 (falham na 1.3.4, passam na 1.4.0), por requisito.
A = K + "test_auditoria_autorizacao.py"
M = K + "test_auditoria_aprovacao_retirada.py"
B = K + "test_auditoria_recuperacao_orcamento.py"
AUDITORIA_134 = {
    "R04": f"{A} (F01–F04)",
    "R06": f"{A} (F02, F03)",
    "R07": f"{A} (F02: decisão só em execução do próprio projeto)",
    "R08": f"{A} (F03: revogação durante a etapa, retomada sem efeito repetido)",
    "R18": f"{A} (F03, F04)",
    "R20": f"{M} (F06)",
    "R24": f"{M} (F07)",
    "R28": f"{M} (F05, F09)",
    "R29": f"{M} (F08)",
    "R30": f"{M} (F08)",
    "R31": f"{M} (F07, F09); {B} (F11, F12)",
    "R32": f"{A} (F01); " + K + "test_auditoria_n1_skill_de_host.py (N1)",
    "R34": f"{A} (F04: catálogo MCP pelo SDK real)",
    "R35": K + "test_auditoria_n1_skill_de_host.py (N1); entrega/MATRIZ-HOSTS-E-VERIFICACOES.md (F20)",
    "R39": f"{B} (F10)",
    "R40": "entrega/testes/test_avaliacoes.py e entrega/avaliacoes/reanalise_pareada.py (F19)",
    "R42": "scripts/tests/ (F04, F13–F16) e entrega/testes/ (F17–F19)",
    "R43": "scripts/tests/test_matriz.py (F16)",
    "R44": f"{B} (F11); scripts/tests/test_manifesto.py (F14)",
    "R45": f"{B} (F11, F12)",
    "R46": "scripts/tests/test_instalar_kit.py (F15); scripts/tests/test_caracterizar.py (F13)",
    "R47": f"{A} (F01); " + K + "test_auditoria_n1_skill_de_host.py (N1)",
    "R48": f"{B} (F12)",
    "R50": "scripts/tests/test_matriz.py (F16)",
    "R52": f"{A} (F04: saída por ligação); scripts/tests/test_instalar_kit.py (F04)",
    "R54": f"{A} (F01: hash do código aprovado na habilitação)",
    "R56": f"{M} (F07); {B} (F11)",
    "R59": "entrega/testes/test_instalar_skill.py (F17: junção sem os.path.isjunction, simulada)",
}

# Regressões do relatório técnico sobre a 1.4.0 (falham na 1.4.0, passam na 1.4.1), por requisito.
RELATORIO_TECNICO_140 = {
    "R35": "evals/cenarios/run_cenarios.py, CEN-11 (PRM-02: cabeçalho aceito pelo validador do Chat/Work)",
    "R42": "entrega/testes/test_relatorio_tecnico_1_4_0.py (COD-02, COD-03, COD-05)",
}

# Regressões da auditoria sobre a 1.4.1 (falham na 1.4.1, passam na 1.4.2), por requisito.
AUDITORIA_141 = {
    "R42": "entrega/testes/test_auditoria_1_4_1.py (SEC-02, OPS-01; controle do SEC-01)",
    "R46": "entrega/testes/test_auditoria_1_4_1.py (OPS-01: atualização da skill por renomeação, com retorno à versão "
           "anterior se algo falhar; a 1.4.3 descreve a troca como duas renomeações com uma marca entre elas)",
}

COLS = ["ID", "Requisito", "Origem (aula, seção, página)", "Interpretação operacional",
        "Arquivo/procedimento da skill", "Critério de aceitação", "Cenário de avaliação",
        "Dependências, condições e limitações", "Adaptação pedagógica", "Natureza", "Estado nesta entrega"]


def md_escape(text: str) -> str:
    return text.replace("|", "\\|").replace("\n", " ")


# Conferência independente da 1.4.3 (CONFERENCIA-1.4.3.md §7): regressões CF-01 a CF-04 da 1.4.4.
CONFERENCIA_143 = {
    "R42": "entrega/testes/test_conferencia_1_4_3.py (CF-01 hook de identidade, CF-02 ligação pendurada, "
           "CF-03 BOM no SKILL.md, CF-04 marca de troca ilegível)",
}

# Regressões da 1.5.0, por requisito: auditoria técnica sobre a 1.4.1 (A01–A19,
# auditoria/AUDITORIA-TECNICA-1.4.1-A01-A19.md) e revisão de segurança (varredura) da 1.4.5 (#1–#25,
# auditoria/SCAN-SEGURANCA-1.4.5/). Falham na 1.4.5 e passam na 1.5.0, salvo os controles de compatibilidade.
EX = K + "test_auditoria_1_5_0_execucao.py"
DA = K + "test_auditoria_1_5_0_dados.py"
AUDITORIA_TECNICA_141 = {
    "R03": "scripts/tests/test_inspecionar_ambiente.py (A18: `--saida` recusa arquivo existente)",
    "R07": f"{DA} (A11: chaves que colidem depois da NFC são recusadas)",
    "R08": f"{EX} (A04: saída conferida pelo hash do banco; A05: posse por geração); "
           "scripts/tests/test_retomada.py (A17: validação estrutural, não autorização)",
    "R19": f"{DA} (A10: aprovação concorrente obsoleta recusada)",
    "R28": f"{DA} (A09: aprovar, publicar ou retirar memória invalida o cache)",
    "R32": f"{EX} (A06: prazo encerra a árvore de processos; A08: descoberta sem importar o pacote pai)",
    "R39": f"{EX} (A07: prazo gravado na 1ª execução, conferido em cada débito, não renovado na retomada)",
    "R44": "scripts/tests/test_auditoria_1_5_0_manifesto_backup.py (A12–A15: manifesto sem seguir ligação nem "
           "listar a si mesmo; backup_sqlite no mesmo snapshot, com contagens exatas)",
    "R46": "entrega/testes/test_auditoria_1_5_0_instalacao.py (A01, A02); "
           "scripts/tests/test_auditoria_1_5_0_instalar_kit.py (A03); "
           "scripts/tests/test_auditoria_1_5_0_manifesto_backup.py (A16: caracterização guarda a saída parcial)",
}
REVISAO_SEGURANCA_145 = {
    "R04": f"{EX} e test_auditoria_1_5_0_dados.py (#11: autorização conferida de novo dentro de cada transação)",
    "R07": f"{EX} (#11: aprovador revogado no meio não decide)",
    "R08": f"{EX} (#14: recibo forjado não confirma etapa); scripts/tests/test_retomada.py (#10)",
    "R12": f"{EX} (#9: Codex CLI sem `isolamento_leitura` não inicia processo)",
    "R15": f"{EX} (#17: custo negativo, NaN ou infinito = não medido)",
    "R18": f"{DA} (#15: histórico de memória de caso exige auditoria no caso)",
    "R20": f"{DA} (#19: promoção pendente sem vínculo com a revisão da origem não publica)",
    "R24": f"{DA} (#7: retirada não sai do escopo de quem retira, salvo a publicação aprovada)",
    "R28": f"{DA} (#21, #23); test_restauracao_revisoes.py (#21 reaplicado na restauração)",
    "R30": f"{DA} (#18: identificador de fonte preso a um escopo)",
    "R31": f"{DA} (#12: versão de fonte inteira a partir de 1; registro protegido sem linha inválida)",
    "R32": f"{EX} (#25)",
    "R39": f"{EX} (#17: custo inválido não reduz nem anula `max_usd`)",
    "R42": "entrega/testes/test_auditoria_1_5_0_avaliacoes.py (#5, #6, #16, #22: harness das avaliações)",
    "R45": K + "test_auditoria_1_5_0_backup.py (#8: âncora externa da cópia; #24: ligação não seguida)",
    "R46": "entrega/testes/test_auditoria_1_5_0_instalacao.py (#1: empacotador recusa ligações; #2: `instalar` e "
           "`atualizar` exigem `--sha256`; #3: instala os mesmos bytes conferidos)",
    "R52": "scripts/tests/test_hooks.py (#13: ligação ou junção na pasta do projeto, em projects/ e no destino)",
}

# Análise do vibe-coding-toolkit (21/10/2026), adotada na 1.7.0: propostas 1 a 15.
ANALISE_VCT_170 = {
    "R01": K + "test_fronteiras_codigo.py (fronteiras do código e teto de tamanho, como teste)",
    "R08": "scripts/tests/test_retomada_arquivar.py (RETOMADA enxuta, histórico arquivado e conferido); "
           + K + "test_canarios_falhas.py (erro de etapa gravado só como tipo, tamanho e hash)",
    "R10": "scripts/tests/test_referencias_propostas_vct.py (paralelismo em ondas: arquivos, dependências e recursos)",
    "R13": K + "test_politica_rotas.py (política de rotas validada ao carregar); "
           + K + "test_configuracao_decidida.py (rota sigilosa local só com decisão registrada)",
    "R35": "scripts/tests/test_instrucoes_aninhadas.py (instruções e skills aninhadas inventariadas antes da leitura); "
           "scripts/tests/test_host_vct.py (skill aninhada negada por nome)",
    "R37": "scripts/tests/test_instrucoes_raiz.py e test_atualizar_fundacao_instrucoes.py (AGENTS.md gerado e "
           "CLAUDE.md na raiz; as chamadas aos provedores não os carregam)",
    "R42": "entrega/testes/test_avaliacoes_vct.py (E10–E12); scripts/tests/test_atualizar_fundacao_catraca.py "
           "(teste sumido ou passado a pulado é regressão)",
    "R45": K + "test_backup_completo.py (AGENTS.md e CLAUDE.md da raiz sempre na cópia)",
    "R46": "scripts/tests/test_instalar_kit_orfaos.py e test_atualizar_fundacao_catraca.py (órfãos guardados e "
           "devolvidos); scripts/tests/test_atualizar_fundacao_instrucoes.py; scripts/tests/test_revisao_seguranca_170.py "
           "(VCT170-01, 02 e 04: caminho forjado ou atrás de junção no registro de instalação e no do desfazer)",
    "R51": "scripts/tests/test_verificar_referencias_comandos.py (comandos citados conferidos contra o argparse)",
    "R52": "scripts/tests/test_host_vct.py (projeto autenticado entregue pelo lançador; pastas data/ fora das instruções); "
           "scripts/tests/test_host_wsl.py (lançador recusa projeto divergente do settings.local.json)",
    "R53": "scripts/tests/test_pacote_sem_segredo_aparente.py (a varredura de segredos da transferência sobre o pacote "
           "inteiro); scripts/tests/test_host_vct.py (web negada no perfil de dados reais); " + K
           + "test_canarios_falhas.py (canários fora dos registros de falha)",
    "R54": "scripts/tests/test_inventariar_host.py (inventário do ecossistema do host, conferido na atualização); "
           "scripts/tests/test_revisao_seguranca_170.py (VCT170-03: sem caminho de projeto nem argumentos); "
           "entrega/testes/test_ci_publica.py (ações da CI fixadas por SHA)",
    "R58": "entrega/testes/test_ci_publica.py (cinco verificações, duas plataformas, cinco rodadas); "
           "entrega/testes/test_cenarios_bloqueio.py (cenário bloqueado por dependência opcional, nunca aprovado; CEN-11 sem PyYAML)",
    "R59": "entrega/testes/test_ligacao_por_caminho_alternativo.py (perfil aberto por um caminho que não é o final, como o nome curto da CI: a ligação pendurada é reconhecida)",
}

# Avaliações E10 e E11 (21/10/2026; skill 1.7.1, kit 1.7.0), corrigidas na 1.7.4.
AVALIACAO_E10_E11_174 = {
    "R07": K + "test_avaliacao_e11_aspas.py (F-01: comando do titular no PowerShell não fecha a cadeia com aspa "
           "tipográfica nem aceita assinante com quebra de linha); " + K + "test_avaliacao_e11_ordem_decisoes.py "
           "(F-02 e revisão da 1.7.4, E11R-04 a E11R-06: decisão encadeada à vigente e ao evento que a registrou, no "
           "conteúdo assinado, conferida e gravada numa só transação)",
    "R08": "scripts/tests/test_regra_retomada_desatualizada.py (E10: RETOMADA que afirma conclusão falsa; fechar "
           "cobre terminar o mesmo trabalho; identidade de laboratório sem declaração)",
    "R13": K + "test_avaliacao_e11_rota_sigilosa.py (F-05 e revisão da 1.7.4, E11R-01 a E11R-03: desvio da rota "
           "sigilosa só com aceite assinado, vigente na tarefa e sobre os mesmos bytes que valem; sem ele, sem efeito "
           "ao carregar); scripts/tests/test_conformidade_configuracao_local.py (o checar da atualização avisa)",
    "R39": K + "test_avaliacao_e11_falha_cli.py (F-04: falha da CLI com processo iniciado conta no teto)",
    "R45": K + "test_avaliacao_e11_restauracao.py (F-03: id de componente fora do formato não libera nem escreve fora "
           "do destino)",
}


def main() -> int:
    entrega, skill = Path(sys.argv[1]), Path(sys.argv[2])
    for rid in list(R):
        row = list(R[rid])
        row[1] = completar_paginas(row[1])
        if row[7].strip() in ("", "—") and rid in ADAPTACAO:
            row[7] = ADAPTACAO[rid]
        if rid in AUDITORIA_134:
            row[5] = f"{row[5]}; regressão da auditoria externa: {AUDITORIA_134[rid]}"
        if rid in RELATORIO_TECNICO_140:
            row[5] = f"{row[5]}; regressão do relatório técnico da 1.4.0: {RELATORIO_TECNICO_140[rid]}"
        if rid in AUDITORIA_141:
            row[5] = f"{row[5]}; regressão da auditoria sobre a 1.4.1: {AUDITORIA_141[rid]}"
        if rid in CONFERENCIA_143:
            row[5] = f"{row[5]}; regressão da conferência da 1.4.3: {CONFERENCIA_143[rid]}"
        if rid in AUDITORIA_TECNICA_141:
            row[5] = f"{row[5]}; regressão da auditoria técnica sobre a 1.4.1: {AUDITORIA_TECNICA_141[rid]}"
        if rid in REVISAO_SEGURANCA_145:
            row[5] = f"{row[5]}; regressão da revisão de segurança da 1.4.5: {REVISAO_SEGURANCA_145[rid]}"
        if rid in ANALISE_VCT_170:
            row[5] = f"{row[5]}; 1.7.0 (análise do vibe-coding-toolkit): {ANALISE_VCT_170[rid]}"
        if rid in AVALIACAO_E10_E11_174:
            row[5] = f"{row[5]}; 1.7.4 (avaliações E10 e E11): {AVALIACAO_E10_E11_174[rid]}"
        R[rid] = tuple(row)
    out_dir = entrega / "rastreabilidade"
    out_dir.mkdir(parents=True, exist_ok=True)
    with (out_dir / "MATRIZ-RASTREABILIDADE.csv").open("w", encoding="utf-8", newline="") as fh:
        w = csv.writer(fh, lineterminator="\n")
        w.writerow(COLS)
        for rid, row in R.items():
            w.writerow([rid, *row])
    lines = [
        "# Matriz de rastreabilidade — R01–R51 (Apêndice B) e R52–R60 (proposta 3.0)", "",
        "Gerada por `gerar_rastreabilidade.py` (fonte única; a versão compacta usada pela skill está em",
        "`fundacao-ia-multiprojetos/references/requisitos.md`). Identificadores do livro preservados.",
        "Natureza: **Livro** = extraído do livro 2.0; **3.0** = proposta de correção; **decisão** = escolha",
        "de projeto da skill; **verificação** = fato conferido em documentação oficial em 18/10/2026.",
        "Estado nesta entrega descreve a **skill** (procedimento, kit e testes em ambiente descartável),",
        "não a fundação do usuário — que só avança com evidências no ambiente dele.", "",
        "| " + " | ".join(COLS) + " |", "|" + "---|" * len(COLS),
    ]
    for rid, row in R.items():
        lines.append("| " + " | ".join(md_escape(x) for x in (rid, *row)) + " |")
    def category(state: str) -> str:
        low = state.lower()
        if "execut" in low and ("bloquead" in low or "pendente" in low):
            return "Parcial: mecanismo executado aqui; parte depende do ambiente do usuário"
        if "bloquead" in low:
            return "Bloqueado nesta entrega (autorização, instalação ou dependência)"
        if "depende do" in low:
            return "Depende do titular/usuário (por natureza)"
        if "pendente" in low and any(w in low for w in ("execut", "parcial", "lógica", "mecanismo", "visão", "exclusão", "política", "normalização", "verificação de existência", "métrica")):
            return "Parcial: mecanismo executado aqui; parte depende do ambiente do usuário"
        if "pendente" in low:
            return "Procedimento escrito; execução pendente no ambiente do usuário"
        if "parcial" in low:
            return "Parcial: mecanismo executado aqui; parte depende do ambiente do usuário"
        return "Procedimento escrito e mecanismo executado em ambiente descartável"
    groups: dict[str, list[str]] = {}
    for rid, row in R.items():
        groups.setdefault(category(row[-1]), []).append(rid)
    lines += ["", "## Resumo por estado nesta entrega", ""]
    for cat, ids in sorted(groups.items(), key=lambda kv: -len(kv[1])):
        lines.append(f"- **{cat}** ({len(ids)}): {', '.join(ids)}")
    (out_dir / "MATRIZ-RASTREABILIDADE.md").write_text("\n".join(lines) + "\n", encoding="utf-8", newline="\n")

    compact = [
        "# Requisitos R01–R60: o que demonstrar e onde está o procedimento", "",
        "Base: Apêndice B do livro (R01–R51, p187–193) e proposta 3.0 (R52–R60). Use com",
        "`scripts/matriz.py` (registro de estado) e `references/principios-e-evidencias.md` (estados honestos).",
        "A matriz completa de rastreabilidade (origem, interpretação, limitações, adaptação pedagógica)",
        "acompanha o pacote de entrega e não faz parte da skill instalada. Citações a `evals/` valem",
        "para o pacote completo (o `.skill` instalável não leva essa pasta).", "",
        "| ID | Requisito | Procedimento | Aceite | Cenário/teste |", "|---|---|---|---|---|",
    ]
    for rid, row in R.items():
        req, origem, interp, arquivos, aceite, cen, *_ = row
        compact.append("| " + " | ".join(md_escape(x) for x in (rid, req, arquivos, aceite, cen)) + " |")
    compact += ["", "Notas: R12, R15 e R17 também se ligam à A12 (proposta 3.0). Requisitos que dependem de",
                "acesso, cota, hardware ou decisão do titular permanecem `bloqueado` com condição de resolução",
                "até a evidência existir; nenhum some da matriz."]
    (skill / "references" / "requisitos.md").write_text("\n".join(compact) + "\n", encoding="utf-8", newline="\n")
    print(f"{len(R)} requisitos gerados")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
