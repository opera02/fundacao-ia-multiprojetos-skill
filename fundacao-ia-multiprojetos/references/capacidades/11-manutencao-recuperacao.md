# 11 — Manutenção e recuperação: dependências, atualização, troca, backup, restauração

Requisitos: R03, R44, R45, R46, R47, R48 (e R56 da 3.0). Aulas: A05 [Livro p28–31],
A33 [p167–169], A34 [p170–173], A35 [p174–177], Apêndice D [p199–203]; 3.0 §3.13–§3.14.
Ordem sugerida na 3.0: A35 (backup) antes de A33 (atualização) [3.0 R13.6].

## Dependências reproduzíveis (R03)
- Registre versão de Python, sistema, dependências e configuração; ambiente virtual é
  **recriável**, não copiável entre caminhos/sistemas; chame o interpretador da venv
  diretamente (sem alterar ExecutionPolicy) [Livro p167–168, p201]:
  `python -m venv .venv` → `.\.venv\Scripts\python.exe -m pip --version` (Windows) ·
  `.venv/bin/python` (WSL).
- Instalações repetíveis com versões fixadas e, quando apropriado, hashes; testes
  continuam necessários [Livro p168]. [3.0 R14.2] `uv` (`uv.lock`, `uv sync`, `uv run`)
  é opção recomendada; avalie no ambiente.
- Origem e licença de cada dependência conferidas na revisão instalada [Livro p25].
- Armadilhas Windows/WSL [3.0 R14.3; Livro p199]: projeto e banco no sistema de
  arquivos do ambiente principal (WSL: `~/fundacao`, não `/mnt/c`); nunca abrir o mesmo
  SQLite pelo Windows e pelo WSL; `.gitattributes` com `* text=auto eol=lf`;
  `PYTHONUTF8=1`; fora do OneDrive; alias da Store do `python` desligado; `.venv` não
  compartilhada entre Windows e Linux. Python: identifique o gerenciador antes de lançar
  `python` (pode instalar automaticamente se não houver runtime) [Verificado 2026-10-18].

## Atualizar com compatibilidade e retorno (R46) [Livro A33]
Quatro contratos a comparar: entrada/saída · estado persistido · segurança · operação.
Seis etapas (preparar, ler, isolar, comparar, decidir, promover/retornar) — ver
`references/fluxo-c-operar.md` C6. Nem toda diferença é regressão (correção pode
rejeitar entrada antes aceita indevidamente); regra nova = especificação explícita,
não "melhoria técnica". Migrações: `PRAGMA user_version` + scripts numerados,
*expand/contract*, limites do `ALTER TABLE`; retorno pode exigir restaurar cópia e
reconciliar operações posteriores [Livro p168; 3.0 R13.4]. Atualização que retoma
tarefas concluídas como pendentes é **reprovada**, mesmo com cálculos certos [Livro p169].
Kit [Decisão; auditoria Codex Security da 1.7.6, #8 e #10]: o `scripts/atualizar_fundacao.py` não executa nada da
raiz antes de conferi-la — inventário exato, por hash, das áreas de código; executável desconhecido recusa — e roda o
código antigo e os testes do ensaio de cópias conferidas (`scripts/codigo_conferido.py`). O `desfazer`
(`scripts/registro_atualizacao.py`) só aceita registro ancorado em `registry/atualizacoes.jsonl`, só mexe nas áreas de
código do kit, só se o código ainda é o que a atualização deixou, e devolve também o registro da instalação. Com o kit
igual, só as instruções da raiz são regeneradas, se a skill mudou o texto (C6). Revisão de segurança da 1.7.7: a
promoção apaga o `__pycache__` das áreas de código, e nada é gravado através de ligação ou vínculo físico (C6).

## Habilitar, desabilitar e substituir (R47) [Livro A34]
Ver `references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md` §1 e `references/fluxo-c-operar.md` C8. Ciclo didático:
`{"installed": true, "enabled": false, "health": "nao_consultada", "new_jobs": "blocked",
"running_jobs": "drain", "replaced_by": null}` [Livro p171]. Teste de saúde com
propósito, frequência e custo compreendidos (não chamar modelo caro a cada atualização
de painel) [Livro p170]. Negativas para usuário comum dão o mínimo para continuar;
causa detalhada fica no relatório administrativo [Livro p172]. [3.0 R13.6] Interruptor
por projeto e global; deprecação em 3 passos.

## Backup e restauração (R44, R45, R31, R56)
- Conjunto de recuperação: código e dependências (versão + ambiente recriável) ·
  estado e memória (snapshot consistente + histórico) · fontes e permissões (arquivos e
  políticas vigentes) · derivados (cópia validada **ou** reconstrução) [Livro p174].
- SQLite: `Connection.backup()` ou `VACUUM INTO`; nunca copiar sem o `-wal`;
  `PRAGMA integrity_check` [Livro p174; 3.0 R13.2]. Credenciais seguem seu próprio
  mecanismo e não entram no pacote [Livro p174].
- RPO (perda máxima tolerada) e RTO (tempo para recuperar) definidos antes; depois,
  medidos (exemplo hipotético: snapshot 10h, falha 10h20, utilizável 11h05 → janela
  de perda 20 min, recuperação 45 min) [Livro p174].
- **Armadilha da fonte revogada:** backup das 10h contém documento retirado às 10h15;
  restaurar e reindexar sem reaplicar a retirada o ressuscita [Livro p175]. Registro de
  retiradas protegido e **fora** do backup; sem ele, a restauração não está pronta. Toda
  retirada entra no registro (fontes **e memórias**, com os derivados) e também toda
  **revogação de acesso**; a cópia anota a **identidade** do registro (criada pelo `init`) e
  até onde ele ia. A restauração lê e valida o registro **antes** de copiar qualquer coisa e
  recusa registro inexistente, ilegível, de outra fundação (identidade diferente) ou que não
  alcança aquele ponto [Decisão; achados da auditoria e da reverificação].
- **Reaplicação antes de liberar:** fontes (com limpeza dos derivados), memórias (com os
  derivados registrados), revogações de acesso e desativações de componente **posteriores** à
  cópia (as anteriores já estão na cópia; reaplicá-las desfaria uma nova concessão ou
  habilitação legítima). Concessões e habilitações posteriores à cópia **não** são reaplicadas:
  o resultado erra para menos acesso e menos capacidade, e refazê-las é decisão da
  administração. Alterações em arquivos depois da cópia (ex.: `registry/route_policy.json`)
  também não: a resposta da restauração traz essa lista em `nao_reaplicado` — confira à mão. Cada reaplicação vira evento `restore_reapplied` na trilha restaurada,
  mais um `restore_completed`; o destino segue com o mesmo registro (`state/retiradas.jsonl`).
  Até liberar, a raiz (montada no preparo, abaixo) carrega `state/restauracao-nao-liberada.json`, e
  a CLI e o servidor MCP recusam usar essa raiz; o destino só a recebe liberada.
- **Sem lacuna entre o banco e o registro** [Decisão; auditoria externa da 1.3.4]: cada decisão
  protegida grava a intenção de exportação na mesma transação (outbox) e a exporta em seguida,
  de forma idempotente (linha já gravada não se repete) e com `fsync`; falha ou queda depois do
  commit fica pendente e é exportada na próxima decisão, no `init` ou ao abrir a fundação; o
  backup recusa enquanto houver pendência não gravável. Fundação de kit anterior: o `init`
  recompõe pela trilha de eventos revogações e desativações que nunca chegaram ao registro.
  O registro protegido, o livro de cópias e a exportação de eventos (`eventos exportar`) só
  acrescentam por `publicacao.anexar`: ligação ou vínculo físico no lugar do arquivo recusa sem
  gravar no arquivo de fora — a decisão fica pendente na fila; o `backup criar` devolve a âncora
  e avisa que não a anotou [revisão de segurança da 1.7.7, R177-KIT-04].
- **Ponto de corte coerente na restauração:** o registro é relido depois da reaplicação e o que
  entrou nele no intervalo também é reaplicado; o registro do destino recebe exatamente o conteúdo
  reaplicado (`corte_do_registro`), nunca uma cópia posterior do arquivo vivo; registro reescrito
  ou em mudança contínua impede a liberação.
- **Cópia de kit anterior à 1.3.0** (sem identidade anotada) e sem retiradas: nada prova que
  o registro é desta fundação, e a restauração não libera; depois de conferir o registro à
  mão, a administração pode usar `--aceitar-registro-nao-comprovado` (a ressalva fica na
  resposta e na trilha). Fundação atualizada para a 1.3.0: rode `init` (cria a identidade e
  preenche as retiradas que estão no banco e faltam no registro) e faça um backup novo.
- **Conferir a cópia inteira:** a verificação compara cada arquivo com o hash do manifesto e o
  **banco** com o SHA-256 gravado (cópias da 1.3.1 em diante) e com o resumo lógico (contagem
  por tabela, `user_version`): banco trocado (mesmo íntegro) ou tabela esvaziada não confere, e
  a restauração não libera; arquivo acrescentado à cópia que o manifesto não lista (até código
  em `fundacao/`) também não confere. Cópia anterior à 1.3.1 não tem o hash: é conferida só por
  integridade e contagens, e a resposta avisa (`aviso`/`aviso_copia`) — faça um backup novo
  depois de atualizar. A cópia do banco sai do modo WAL e é lida de forma imutável (só o
  arquivo do banco, o mesmo que a restauração copia): conferir não cria `-wal`/`-shm`, nem em
  cópia antiga. Manifesto e banco ficam na mesma pasta: quem reescreve os dois forja a cópia —
  por isso a âncora externa (abaixo), e a política 3-2-1-1-0 continua pedindo uma cópia imutável.
  `backup verificar` que não confere sai com código 3; manifesto com estrutura inválida, com erro
  JSON e código 2.
- **Âncora externa da cópia** [Decisão; varredura da 1.4.5, #8; auditoria Codex Security da 1.7.6,
  #2]: o `backup criar` devolve `sha256_manifesto` (o SHA-256 do `manifest.json`, que confere cada
  arquivo e o banco) e o anota no livro de cópias `state/copias.jsonl` — ao lado do registro
  protegido e fora da cópia. Guarde o código fora da pasta da cópia (anotação, gerenciador de
  senhas, outro disco) e o livro junto do registro protegido. A restauração confere o manifesto pela
  âncora: `--sha256-manifesto` informado (diferente = não libera, nada copiado) ou o livro ao lado de
  `--retiradas`. Sem âncora, **não** libera — nem com o código da cópia igual ao do kit: uma cópia
  forjada traz banco e permissões coerentes com o próprio manifesto. Só libera com
  `--aceitar-copia-sem-ancora "<motivo>"`, decisão do administrador depois de conferir de onde veio a
  cópia, que fica na resposta (`ressalva_ancora`, com o motivo), na trilha (`restore_completed`) e no
  aviso `W_COPIA_SEM_ANCORA` do stderr; a resposta da recusa diz se o código difere do kit
  (`codigo_diferente`). `backup verificar` mostra a situação (`ancora`), pela âncora informada ou
  pelo livro da raiz onde roda.
- **Limite do livro de cópias** [Decisão; revisão de segurança da 1.7.7, R177-KIT-01]: o livro só vale
  tanto quanto `state/` está protegido. No perfil de dados reais do WSL, a sessão grava `state/` e a
  pasta de backups, e quem grava as duas troca a cópia e anota a âncora nova no livro — o livro não
  distingue isso. Por isso a âncora vinda do livro sai com `aviso_ancora` (na restauração liberada,
  também `W_ANCORA_DO_LIVRO` no stderr) e `ancora.fonte` diz de onde ela veio (`livro de cópias` ou
  `sha256 informado`). Depois de suspeita de comprometimento, restaure só com o `sha256_manifesto`
  guardado fora (`--sha256-manifesto`). Livro e registro dentro da própria cópia (`--origem`) não
  valem: são tratados como ausentes, com o motivo na resposta (`livro_recusado`; o do registro, na
  recusa). Assinar as entradas do livro fica como proposta.
- **Quem verifica e restaura** [Decisão; auditoria Codex Security da 1.7.6, #2]: a administração da
  fundação, decidida por uma política confiável — nunca só pelo banco de uma cópia não autenticada.
  Com a fundação viva (banco legível na raiz), vale a política dela, a atual: quem perdeu a
  administração depois da cópia não restaura, e administração forjada na cópia não conta. Sem ela
  (origem perdida ou danificada), vale a política da cópia, só depois de a âncora conferir o
  manifesto e o banco conferir com o hash dele, numa cópia privada do banco. Sem fundação viva e sem
  âncora, ninguém é autorizado (código 2): na recuperação de desastre, a prova é o
  `sha256_manifesto` guardado fora da cópia (ou o livro guardado junto do registro). Perdidos os dois,
  resta a decisão sem prova: o titular cria uma fundação nova (`init --admin`), restaura a partir dela
  (`--raiz`) com `--aceitar-copia-sem-ancora "<motivo>"` e confere a raiz restaurada antes de usá-la.
  A raiz que é a própria cópia — igual a `--origem`, dentro dela ou com o `manifest.json` de uma cópia
  — não vale como fundação viva, e a resposta mostra a raiz resolvida (`autorizacao.raiz`; sem
  fundação viva, também `autorizacao.sem_fundacao_viva`, o motivo). Rodando fora da raiz, a negativa
  diz por que a raiz não valeu e lembra o `--raiz` [revisão de segurança da 1.7.7, R177-KIT-02].
  Também não vale a raiz com o banco da cópia (`state/` ligado ao dela ou vínculo físico com o banco
  dela) nem com ligação no caminho do banco, como no `backup criar`: informe o caminho real [segunda
  passada da revisão, variante do R177-KIT-02].
  **Limite:** outra pasta com um banco forjado ainda passa por fundação viva; a raiz é a que o
  lançador entrega — confira `autorizacao.raiz`.
- **Preparo privado** [Decisão; auditoria Codex Security da 1.7.6, #12]: a conferência e a cópia
  ficam presas ao mesmo objeto do disco, não ao nome. A restauração traz a cópia para uma pasta de
  preparo criada ao lado do destino, com exclusividade, abrindo cada arquivo sem seguir ligação e
  conferindo que é o objeto listado antes de ler; a verificação, o banco e a reaplicação usam só o
  preparo. Logo antes da promoção, a raiz preparada é conferida de novo (arquivos contra o manifesto;
  `state/` contra o que a reaplicação deixou), e a promoção é uma renomeação atômica, que não grava
  através de ligação no destino. O destino só recebe a raiz liberada; preparo não liberado é apagado.
  Ligação no caminho da cópia ou do destino (ou num ancestral) recusa: informe o caminho real. O
  backup também monta a cópia num preparo ao lado do destino e a promove inteira (cópia pela metade
  não aparece; no Linux, a pasta nasce só para esta conta); arquivo trocado por ligação depois da
  listagem fica fora, em `ligacoes_nao_seguidas`. **Limite:** na mesma conta do sistema, quem troca
  e destroca uma pasta no instante exato da listagem, ou um ancestral do destino durante a escrita,
  ainda redireciona a operação (no Windows, o Python não abre sem seguir ligação); a reconferência
  recusa o resultado, mas o que já foi escrito do outro lado fica lá. No Windows, o preparo — e o
  destino, depois da promoção — herda as permissões da **pasta de cima do destino**: restaure (e
  guarde cópias) dentro de uma pasta que só o titular altera; é ela que conta, não o destino. Destino
  vazio criado antes é trocado pela pasta preparada, e as permissões próprias dele não ficam: a
  resposta avisa (`aviso_permissoes` na restauração, `aviso` no backup) [revisão de segurança da
  1.7.7, R177-KIT-05].
- **Backup completo** [Decisão; implantação real de 2026-10-19/20]: além do kit (`fundacao/`,
  `registry/`, `templates/`, `projects/`) e do banco, a cópia leva por padrão os registros da
  fundação — `docs/`, `evidence/`, `ferramentas/`, `tests/` e `RETOMADA.md`; troque a lista em
  `registry/backup_policy.json` (`{"incluir": [...]}`). Caminho inválido na política (absoluto,
  com `..`, em `state/` ou `.git`) ou destino dentro de uma pasta copiada recusam antes de
  copiar; segredos continuam fora.
- **Ligações** [Decisão; varredura da 1.4.5, #24]: ligação (link simbólico ou junção) em
  `fundacao/`, `registry/`, `templates/`, `projects/` ou nos registros não é seguida: fica em
  `ligacoes_nao_seguidas`, com aviso, e o conteúdo dela não entra na cópia; ligação dentro da
  cópia não confere (restauração não liberada). A verificação no lugar lista `files/` antes de ler,
  sem seguir ligação, e só calcula o hash do arquivo comum listado, aberto preso ao objeto da
  listagem: nada é lido através de junção dentro da cópia — a ligação vai para `ligacoes`, e os
  arquivos do manifesto atrás dela, para `missing` [revisão de segurança da 1.7.7, R177-KIT-03].
- **Pasta de rede (UNC):** serve para guardar e conferir cópias e como origem da restauração.
  A fundação que será usada deve ser restaurada em disco local — o SQLite em WAL não deve
  operar num compartilhamento de rede; com destino em rede, a restauração avisa
  (`aviso_destino`).
- **Kit da cópia:** o backup inclui o código do kit (`fundacao/`), e a raiz restaurada roda o
  kit que veio na cópia. Se ele for diferente do kit que restaura, a resposta traz
  `kit_da_copia` e `acao_necessaria`: antes de usar a raiz restaurada, atualize o kit nela
  (`instalar_kit.py --destino <destino> --atualizar`) e rode `init` — um kit antigo recusa tipos
  de linha mais novos do registro protegido. O kit 1.3.2 em diante aceita tipo desconhecido
  ao contar e preencher o registro, e só o recusa na restauração, que não saberia reaplicá-lo.
- **Origem danificada:** a autorização vem da cópia ancorada (somente leitura, ver "Quem verifica e
  restaura"), não do banco que se quer recuperar; nada é criado nem migrado na origem.
- Restauração completa: cópia consistente → destino isolado → recriar e abrir estado →
  integridade (arquivos e contratos) → reconciliar revogações e efeitos posteriores →
  testar permissões e resultados → promover no escopo autorizado [Livro p175].
- [3.0 R13.1, R13.3] Política 3-2-1-1-0 (restic/Kopia criptografado; teste mensal) e
  cenário "agente apagou dados e backups locais".

## Retomar sem repetir efeitos (R48) [Livro p175–177]
Depois de restaurar, tarefa reaparece pendente mas há confirmação posterior de que o
efeito ocorreu: **reconcilie** com a confirmação e a versão do artefato antes de
executar; a ausência no snapshot é lacuna temporal, não prova de que a ação não ocorreu.
Use identificador e política de idempotência. Revalide aprovações (hash) na retomada.

## Verificação
| Caso | Esperado |
|---|---|
| Restauração em pasta nova | arquivos abrem, dados lógicos conferem, banco íntegro |
| Alteração/remoção provocada na cópia de teste | detectadas pelo manifesto; `verificar` sai com código 3 |
| Banco da cópia trocado (mesmo íntegro) ou tabela esvaziada, em cópia da 1.3.1 em diante | não confere (hash e contagens); restauração não liberada |
| O mesmo em cópia anterior à 1.3.1 (sem hash no manifesto) | só as contagens são conferidas: tabela esvaziada não confere; troca com as mesmas contagens passa, com aviso — faça um backup novo |
| Arquivo acrescentado à cópia, fora do manifesto (até código em `fundacao/`) | não confere (`extras`); restauração não liberada — confira o que é e faça uma cópia nova (não apague às cegas) |
| `Thumbs.db`, `desktop.ini` ou `.DS_Store` criados pelo sistema na cópia | não barram (`ignorados_do_so`) e não são restaurados |
| Manifesto com estrutura inválida | erro JSON, código 2 |
| Código ou banco da cópia trocados e manifesto recalculado | âncora errada ou cópia fora do livro de cópias: restauração não liberada, nada copiado |
| Restauração sem âncora (sem livro, sem `--sha256-manifesto`) | não liberada, nem com o código do kit; com `--aceitar-copia-sem-ancora "<motivo>"`: liberada, com `ressalva_ancora` na resposta e na trilha |
| Cópia forjada coerente (administração forjada no banco, manifesto recalculado, código do kit) | a fundação viva decide quem verifica e restaura (a ACL da cópia não conta); sem âncora, não liberada |
| Cópia alterada e âncora nova acrescentada ao livro (quem grava `state/` e a pasta de backups) | pelo livro, liberada com `aviso_ancora` (limite declarado); com o `sha256_manifesto` guardado fora, divergente: não liberada |
| Registro ou livro de cópias dentro da própria cópia (`--origem`) | não valem: ausentes, com o motivo; sem fundação viva, ninguém é autorizado |
| Administrador revogado depois da cópia | não verifica nem restaura (vale a política viva) |
| `--raiz` igual à cópia, dentro dela ou com o `manifest.json` de uma cópia (ou rodando de dentro da cópia) | não vale como fundação viva: sem âncora, ninguém é autorizado; `autorizacao.raiz` mostra a raiz resolvida |
| `--raiz` nova com `state/` ligado ao da cópia, banco com vínculo físico ao dela ou ligação no caminho do banco | não vale como fundação viva: sem âncora, ninguém é autorizado (a ACL forjada na cópia não decide) |
| `verificar` ou `restaurar` rodando fora da raiz | negado (código 2), com o motivo e o lembrete do `--raiz` |
| Pasta da cópia, `files/`, `state/` ou destino trocados por ligação durante a restauração; ligação num ancestral | nada lido nem gravado do outro lado; destino ocupado ou ligado: não liberada |
| Raiz preparada alterada antes da promoção | não liberada; o destino não recebe nada |
| Destino vazio criado antes (backup ou restauração) | trocado pela pasta preparada, com aviso: as permissões dele não ficam; proteja a pasta de cima |
| Junção ou link em pasta copiada; ligação dentro da cópia | fora da cópia, em `ligacoes_nao_seguidas`, com aviso; dentro da cópia: não confere, restauração não liberada |
| Junção dentro de `files/` na verificação no lugar (`backup verificar`) | nada lido do outro lado: a ligação em `ligacoes`, os arquivos do manifesto atrás dela em `missing`; não confere |
| Vínculo físico ou ligação em `state/copias.jsonl`, `state/retiradas.jsonl` ou no destino de `eventos exportar` | nada gravado no arquivo de fora: o backup sai com a âncora e o aviso; a revogação fica na fila; a exportação recusa sem marcar eventos |
| `docs/`, `evidence/`, `ferramentas/`, `tests/`, `RETOMADA.md` na raiz | entram na cópia e voltam na restauração; política inválida recusa antes de copiar |
| Cópia com kit diferente do que restaura | liberada com `acao_necessaria` (atualizar o kit na raiz restaurada) |
| Componente desligado depois da cópia | continua desligado no restaurado |
| Cópia em pasta de rede (UNC) | criada, verificada e restaurada; destino em rede vem com `aviso_destino` |
| Retirada posterior ao snapshot | reaplicada antes da liberação; busca negativa |
| Sem registro de retiradas, caminho errado ou registro que não alcança a cópia | restauração **não** liberada (código 3) |
| Registro de outra fundação, arquivo vazio qualquer ou registro ilegível | **não** liberada (código 3) e nada copiado para o destino |
| Acesso revogado depois da cópia | revogação reaplicada; a identidade não volta a ver o projeto |
| Reaplicação | eventos `restore_reapplied` na trilha restaurada, cadeia íntegra |
| Cópia em pasta com `#` no nome (ex.: "Processo #12") | criada, verificada e restaurada |
| Memória eliminada depois da cópia | reaplicada antes da liberação; consulta não a devolve |
| Banco de origem corrompido ou ausente | restauração autorizada pela cópia ancorada (livro ou `--sha256-manifesto`); sem âncora, ninguém; origem intocada |
| Restaurar sobre a origem / sobrescrever referência anterior | recusado |
| Atualização com retorno | retorno em ambiente isolado preserva leitura do estado |

## Com o kit e scripts
`fundacao/core/backup.py` (`create_backup`, `verify_backup`, `restore` com reaplicação),
`fundacao/core/ancora_copia.py` (âncora e quem verifica ou restaura), `fundacao/core/preparo.py`
(preparo privado), `scripts/manifesto.py`, `scripts/backup_sqlite.py`, `scripts/instalar_kit.py --atualizar`
(atualização com cópia de retorno), `scripts/atualizar_fundacao.py` (`checar`, `aplicar`, `desfazer`; testes em
`scripts/tests/test_atualizar_fundacao*.py`, `scripts/tests/test_auditoria_1_7_6_atualizador.py` e
`scripts/tests/test_revisao_seguranca_177_atualizador.py`). Testes do kit:
`tests/test_cache_backup.py::TestBackupRestauracao`,
`tests/test_restauracao.py`, `tests/test_auditoria_1_5_0_backup.py` (âncora e ligações),
`tests/test_auditoria_1_7_7_ancora.py` (autorização e liberação sem âncora),
`tests/test_auditoria_1_7_7_preparo.py` (trocas por ligação e preparo alterado),
`tests/test_revisao_1_7_7_kit.py` (livro e raiz que são a própria cópia, aviso do livro, verificação sem ler através
de ligação, anexos de `state/` sem seguir ligação e destino criado antes),
`tests/test_backup_completo.py`, `tests/test_restauracao_revisoes.py`; cenários
CEN-09 e CEN-16. `scripts/backup_sqlite.py` e a CLI
montam a URI do SQLite com `Path.as_uri()` (codifica `#`, `%` e espaços; sem isso, `#` vira
fragmento e o SQLite abriria outro arquivo).
