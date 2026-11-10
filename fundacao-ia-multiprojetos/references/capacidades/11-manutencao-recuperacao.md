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
  SQLite pelo Windows e pelo WSL (na 1.7.10, conferido pela trava do banco, `state/banco.trava`, no sentido
  Windows ← Ubuntu: com o marcador do outro lado, o kit, o atualizador e o `scripts/backup_sqlite.py` recusam abrir o
  banco; `../seguranca-isolamento.md` §8.2); `.gitattributes` com `* text=auto eol=lf`;
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
promoção apaga o `__pycache__` das áreas de código, e nada é gravado através de ligação ou vínculo físico (C6). Na
1.7.10, o `checar`, o `aplicar` e o `desfazer` conferem a trava do banco pelo kit da skill antes de abrir o banco: com
o marcador do outro lado (vivo, velho ou ilegível), param na etapa `banco`, sem abrir nada; com o velho ou o ilegível,
o motivo traz o comando do titular (`banco destravar --confirmar`).

## Habilitar, desabilitar e substituir (R47) [Livro A34]
Ver `references/capacidades/08-ferramentas-hooks-mcp-skills-plugins.md` §1 e `references/fluxo-c-operar.md` C8. Ciclo didático:
`{"installed": true, "enabled": false, "health": "nao_consultada", "new_jobs": "blocked",
"running_jobs": "drain", "replaced_by": null}` [Livro p171]. Teste de saúde com
propósito, frequência e custo compreendidos (não chamar modelo caro a cada atualização
de painel) [Livro p170]. Negativas para usuário comum dão o mínimo para continuar;
causa detalhada fica no relatório administrativo [Livro p172]. [3.0 R13.6] Interruptor
por projeto e global; deprecação em 3 passos.

## Versão em uso do projeto (1.7.10)
[Decisão; 1.7.10.] O que roda fora da proteção do sandbox — as tarefas agendadas e os servidores de um projeto — roda
de `<raiz>/em-uso/<p>/atual/`, separada da pasta que a IA edita (`scripts/versao_em_uso.py`):
- **propor** (a IA, na sessão): a lista dos arquivos da pasta de trabalho, com o SHA-256 de cada um, sem seguir
  ligação e sem nome forte nem pasta de segredo (segredo não vai pela proposta). A proposta fica em `outputs/` do
  projeto, para o aceite assinado do titular;
- **promover** (o titular, no terminal dele, fora do Claude): só com o aceite assinado sobre essa proposta e esse
  SHA-256, conferido pelo kit da raiz com a identidade do terminal dele. Um aceite vale para uma promoção só: o
  registro guarda a proposta e a decisão usadas, e o aceite já usado recusa. A proposta vale para a troca a partir
  da versão em uso de quando foi feita: promoção ou volta registrada depois recusa ("a versão em uso mudou depois da
  proposta"), e a sessão propõe de novo [revisão de segurança, KIT-F1]. Copia só os arquivos listados, pela cópia
  conferida da skill (`scripts/copia_segura.py`: sem seguir ligação, com o SHA-256 da proposta). A versão nova é
  montada ao lado, no mesmo volume, e entra no lugar de `atual` por renomeação; a anterior vai para `anteriores/`.
  Recusa passageira do Windows na renomeação ganha nova tentativa, com as mesmas esperas do kit; se a nova não entra,
  a anterior volta;
- **pedir-volta** (a IA, na sessão): grava em `outputs/` do projeto o pedido de volta
  (`fundacao.versao_em_uso.volta/1`): a anterior pedida (`--para <nome em anteriores/>`; sem ela, a mais recente), o
  motivo nas palavras do titular e a data. É a entrega do aceite, como a proposta; o pedido não lê `em-uso/`;
- **voltar** (o titular, no terminal dele, fora do Claude): `--pedido`, `--pedido-sha256` e `--decisao`. Só com o
  aceite assinado sobre esse pedido e esse SHA-256, conferido pelo kit da raiz como no `promover`, com a identidade do
  terminal dele; um aceite vale para uma volta só (o registro guarda o pedido e a decisão usados). A anterior é
  conferida contra o manifesto dela e precisa ter entrado em uso por uma promoção do registro; a que estava em uso vai
  para `anteriores/`. Sem `--para`, vale a anterior mais recente. Com ou sem `--para`, o pedido vale só para a volta a
  partir da versão em uso de quando foi feito: promoção ou volta registrada depois dele recusa (peça outra volta). Sem
  `--para`, a data mais de 5 minutos à frente do relógio de quem roda o `voltar` também recusa (com `--para`, a data
  não conta);
- **conferir**: o envoltório das tarefas e dos servidores roda antes de executar; arquivo alterado, ausente, a mais ou
  ligação dá código 1. `__pycache__`, `.git` e os caches de ferramenta em `atual/` contam como a mais, com uma dica: as
  tarefas Python rodam com `python -B`. `.venv`, `venv` e `node_modules` não são conferidas, e o conferir o diz
  (`nao_conferido` e "não conferido: <pasta>", também no stderr) em vez de um ok calado: código posto ali roda sem
  acusação [revisão de segurança, KIT-F5].

Cada promoção e cada volta vão para `em-uso/<p>/registro.jsonl`; registro que existe e não se lê recusa o
`promover`, o `voltar` e o `conferir`, em vez de valer como vazio. Uma troca por vez (`em-uso/<p>/.trava`). As
ferramentas de arquivo da sessão gravam só no projeto (`guarda_caminho.py`), e, no Ubuntu, os comandos só onde o
sandbox confina: com a raiz em `/mnt/e`, um comando da sessão alcança `em-uso/` por fora. A assinatura autoriza a
troca, mas não protege a pasta (isolamento lógico, `../seguranca-isolamento.md` §8). A cópia de segurança leva
`em-uso/` (política da raiz, abaixo). O corte de um projeto para a fundação segue o roteiro
`assets/templates/ROTEIRO-CORTE.md`, com os comandos prontos do `promover` e do `voltar` (passos 8.3 e 8.5).

## Backup e restauração (R44, R45, R31, R56)
- Conjunto de recuperação: código e dependências (versão + ambiente recriável) ·
  estado e memória (snapshot consistente + histórico) · fontes e permissões (arquivos e
  políticas vigentes) · derivados (cópia validada **ou** reconstrução) [Livro p174].
- SQLite: `Connection.backup()` ou `VACUUM INTO`; nunca copiar sem o `-wal`;
  `PRAGMA integrity_check` [Livro p174; 3.0 R13.2]. Credenciais seguem seu próprio
  mecanismo e não entram no pacote [Livro p174]. **No kit não é assim** [Decisão; 1.7.10]: o `.env` fica fora, mas o
  arquivo com cara de segredo (nome forte ou pasta de segredo da regra única) entra como está, sem ser lido, e é
  contado em `segredos_incluidos`; o manifesto diz isso e diz que a cópia não é cifrada. Guarde a cópia como guarda a
  fundação. Tirar os segredos da cópia ou cifrá-la é decisão do titular; desde a 1.7.11, com a chave da cópia
  instalada, ela sai cifrada (§ "Cópia cifrada", abaixo).
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
- **Backup completo** [Decisão; implantação real de 2026-10-19/20; 1.7.10]: além do kit (`fundacao/`,
  `registry/`, `templates/`, `projects/`, `AGENTS.md` e `CLAUDE.md`) e do banco, a cópia leva por padrão os registros
  da fundação — `docs/`, `evidence/`, `ferramentas/`, `tests/` e `RETOMADA.md`; troque a lista em
  `registry/backup_policy.json` (`{"incluir": [...]}`). Caminho inválido na política (absoluto,
  com `..`, em `state/` ou `.git`) recusa antes de copiar; a política compara `state/` e `.git` sem caixa e pelo
  caminho resolvido (`State`, `STATE`, `state.`, `state `, `.` e ligação no meio também recusam), e o motivo vai no
  erro. O `backup criar` e o `backup restaurar` recusam destino dentro da raiz (inclusive `<raiz>/copias` e
  `<raiz>/projects/<p>/outputs/x`): guarde e restaure fora dela, de preferência em outro disco. No desastre (banco
  perdido), rode o `backup restaurar` com `--raiz` na raiz danificada, para o kit poder recusar destino dentro dela
  [revisão de segurança, KIT-F2 e KIT-F7]. Ficam fora as pastas reconstruíveis (`__pycache__`, `.venv`,
  `node_modules` e, desde a 1.7.10, `.cache`, onde o perfil do Ubuntu põe os caches de npm, pip e uv) e o `.env`; o
  `.git` só entra dentro dos projetos (abaixo).
  **Política da raiz na 1.7.10:** o `scripts/atualizar_fundacao.py aplicar`, antes da cópia DEPOIS, acrescenta à lista
  `incluir` as áreas `em-uso` (de onde rodam as tarefas fora da sessão) e `.claude/projetos` (o espelho por projeto e a
  caixa de entrada das fichas de aberturas assinadas, que não se reconstroem). Só acrescenta, preserva o resto e não
  repete; sem o arquivo, ele nasce com a lista padrão mais essas duas; política estragada ou com ligação no caminho
  fica como está, e o resumo diz o que acrescentar à mão. O `desfazer` não a volta: a lista maior vale também para o
  kit anterior.
- **O `.git` dos projetos** [Decisão; 1.7.10]: entra só dentro de `projects/<projeto>/`, fora de `data/` e de pastas
  reconstruíveis, por cópia crua (o kit nunca executa git). Ficam fora os hooks (código que rodaria depois, também os
  dos submódulos), os `*.lock` e cada arquivo comum fora de `objects/` que traga credencial em URL de remoto, cabeçalho
  de autenticação (`http.extraheader`) ou programa configurado (`core.fsmonitor` que não seja booleano,
  `core.hooksPath`, `core.sshCommand`, `credential.helper`, filtros `clean` e `smudge`, `include` e `includeIf` e
  afins); um `config` acima de 1 MiB fica fora sem conferir. O manifesto conta os levados, os excluídos (com o motivo)
  e os que mudaram durante a cópia (repositório vivo), sem conteúdo.
- **Situação da cópia e aviso semanal** [Decisão; 1.7.10]: o `backup criar` grava `registry/ultima-copia.json`
  (`fundacao.ultima_copia/1`), e o `backup verificar` com sucesso, com a âncora conferida e na fundação viva, anota a
  verificação nele.
  `python -m fundacao backup situacao` (administração ou auditoria) diz a idade da última cópia, pelo registro e pelo
  livro de cópias, e, passados 7 dias, avisa (`W_COPIA_ANTIGA`) com os comandos prontos da próxima cópia (rótulo
  `semanal-AAAA-Sss`, na pasta da última) e da verificação. Nas sessões do Windows, o hook
  `assets/hooks/aviso_copia.py` lê só esse registro e, sem cópia ou com a última passando de 7 dias, lembra no início
  da sessão, com o mesmo comando. É lembrete, não prova: quem grava `registry/` forja o registro; a prova é o
  `backup verificar` com o `sha256_manifesto` guardado fora da cópia.
- **Cópia cifrada** [Decisão; 1.7.11; DECISAO-010, item 7: "senha que só o titular sabe"]. Perdida a senha ou a chave
  privada, ninguém abre as cópias dessa chave (nem o kit, nem o coordenador, nem a Anthropic); o titular aceitou isso.
  - **Mecanismo.** GnuPG por caminho fixo (o do Git para Windows em `Program Files`; no Ubuntu, `/usr/bin/gpg`; versão
    2.4 ou mais, anotada no manifesto; um `gpg` posto antes no PATH não vale). A chave **pública** da cópia fica na
    âncora protegida, ao lado do `allowed_signers` (`chave-da-copia.asc`; só administrador grava), instalada pelo
    `preparar-maquina.ps1 -ChaveDaCopia` no UAC; é a presença dela que liga a cifra, porque `registry/` a sessão grava.
    O `backup criar` só usa a pública, então roda sem a senha. Formato **SEIPD v1 (pacote 18, com MDC) e AES-256**, sem
    compressão, e não OCB: o `gpg` 2.4.9 do Git não tem OCB (medido em 08/11/2026). O MDC só confere no fim, e o
    `gpg --decrypt` entrega o claro antes de conferi-lo (saída 2): só vale o que saiu com código 0, e a **parte** é a
    unidade que se descarta.
  - **Formato** (`tar-pax+openpgp-seipd`). A pasta da cópia (`manifest.json`, `files/`, `state/state.sqlite`) vira
    partes independentes de cerca de 1 GiB (`parte-001.gpg`, …; um arquivo nunca se divide), mais `parte-final.gpg`
    (o banco e o manifesto interno), `manifesto-cifrado.json` (em claro, sem nome de arquivo: destinatário, tamanho e
    SHA-256 de cada parte) e `LEIA-ME.txt` (o roteiro à mão, sem segredo). Um setor ruim no disco perde uma parte, não a
    cópia. A âncora é o SHA-256 do manifesto externo (`sha256_manifesto`); o do manifesto interno
    (`sha256_manifesto_interno`) é o de hoje, e o livro anota `cifrada: true` e o destinatário.
  - **`backup criar`.** Copia em claro para um preparo local no disco interno (`--preparo-local`; recusa com pouco
    espaço), confere, cifra para o destino, roda o `verificar` sem senha e apaga o preparo (a sobra é contada). Chave
    instalada e não protegida recusa sem gravar nada; `--sem-cifra "<motivo>"` grava em claro, com o motivo no livro e o
    aviso `W_COPIA_EM_CLARO`. `backup cifrar --origem <cópia em claro conferida> --destino <nova>` converte uma cópia
    antiga. No `aplicar` do atualizador, as cópias ANTES e DEPOIS saem cifradas, e o ensaio restaura do preparo local
    (`--pasta-ensaio` passa a ser local, para não deixar raiz em claro no disco das cópias).
  - **Conferir sem a senha** (o coordenador): `backup verificar` vê âncora, tamanho, SHA-256 e destinatário de cada
    parte (cabeçalho OpenPGP) e responde `conteudo_conferido: false`. Só a senha prova que as partes decifram e que o
    conteúdo bate. `backup restaurar` com origem cifrada recusa e diz o comando do `decifrar-copia`.
  - **Pelo titular** (ferramenta fixa `assets/host/fundacao_titular.py`, no terminal dele; a senha vai só na janela do
    `pinentry`, e o agente do `gpg` é encerrado no fim): `preparar-chave-copia --raiz <raiz> --guardar-em <pasta fora da
    raiz e do disco das cópias>` (uma vez; cria o chaveiro dedicado, mostra a impressão digital para o papel e grava a
    chave privada protegida); `conferir-copia --origem <pasta>` (uma vez por mês: decifra em fluxo, confere cada arquivo
    contra o manifesto interno sem gravá-lo e registra o resultado, sem conteúdo, em `conferencias-copia.jsonl`; passados
    35 dias o `backup situacao` avisa `W_CONTEUDO_NAO_CONFERIDO`); `decifrar-copia --origem <pasta> --destino <pasta nova> --sha256-manifesto <código do papel>`
    (a âncora é o código que o titular guardou fora: o livro `state/copias.jsonl`, que a sessão grava, não basta nem sozinho;
    sem o código só com `--aceitar-sem-ancora`, escolha dele; restauração de verdade; a pasta decifrada está em claro, e apagá-la é do titular). Guarde a chave protegida em três
    lugares, nenhum no disco das cópias; a senha, só no papel. A chave da cópia pede UAC próprio, além do da âncora.
  - **Limites que ficam** (registre sempre): a cifra não prova a origem (quem tem a chave pública monta outra cópia
    válida; quem prova é a âncora guardada fora); o GnuPG protege a chave com S2K sem Argon2, então a senha é longa
    (seis palavras sem relação); o preparo local passa em claro pelo disco interno; a raiz viva continua em claro no
    disco dela; as cópias em claro antigas ficam até o titular aposentá-las, e apagar não limpa um disco rígido. Chave
    nova: as cópias da antiga aparecem com `destinatario` diferente, como aviso. Tempos e espaço da cópia cifrada na
    máquina real: não medidos (o desenho os estima).
- **Trava de manutenção** [Decisão; 1.7.10]: `state/manutencao.json` existe do começo ao fim do `backup criar`, também
  na falha, e do `aplicar` da atualização; o lançador do Ubuntu não abre sessão com ela. Trava que já existia não é
  trocada nem removida por quem não a criou. O `backup criar` devolve um resumo; a lista de arquivos, só com
  `--detalhar` (ela está sempre no `manifest.json` da cópia).
- **Trava do banco** [Decisão; 1.7.10]: o backup do kit não percorre `state/` — leva o banco pela API de backup do
  SQLite —, então o marcador `state/banco.trava`, que o porteiro do Ubuntu grava, nunca vai na cópia nem volta na
  restauração. O `scripts/backup_sqlite.py` confere a trava pelo kit da skill antes de abrir a origem: com o marcador
  do outro lado na pasta dela, recusa (`BancoTravado`, código 1) sem abrir nem criar nada.
- **Nova tentativa no WinError 5** [Decisão; falha real de 31/10/2026: o `backup criar` rodou 22 minutos e terminou
  com acesso negado na renomeação final]: a promoção e as renomeações do preparo repetem só a recusa passageira do
  Windows (WinError 5, 32 e 33: antivírus, indexador ou Explorador com a pasta aberta), com esperas de 1, 2, 4, 8, 15 e
  30 s e nova conferência a cada vez; esgotadas, `E_PROMOCAO`, com as tentativas e os atributos do preparo, sem
  conteúdo. O que sobra do preparo é contado e informado (`W_SOBRA_DO_PREPARO`), nunca apagado em silêncio: a sobra
  pode ter dados da fundação, e apagá-la é do titular, depois de conferir. No `aplicar`, a cópia ANTES que falha na
  promoção tenta de novo uma vez, com rótulo novo, se o destino não existe.
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
| `.git` de um projeto (1.7.10) | levado sem hooks, sem `*.lock` e sem config com credencial ou programa; levados e excluídos contados no manifesto, sem conteúdo |
| `.cache` de um projeto (1.7.10) | fora da cópia (reconstruível); a verificação continua passando |
| Renomeação final recusada pelo Windows (WinError 5, 32 ou 33) (1.7.10) | nova tentativa com espera; esgotada, `E_PROMOCAO`, e a sobra do preparo contada (`W_SOBRA_DO_PREPARO`) |
| Última cópia com mais de 7 dias (1.7.10) | `backup situacao` avisa (`W_COPIA_ANTIGA`) com o comando da próxima; no Windows, o lembrete no início da sessão |
| Cópia ou atualização em andamento (1.7.10) | `state/manutencao.json` presente; o lançador do Ubuntu não abre sessão |
| `aplicar` da 1.7.10 numa raiz sem `em-uso` e `.claude/projetos` na política | os dois acrescentados à lista `incluir`, o resto preservado; política estragada fica como está, com aviso |
| `voltar` da versão em uso sem o aceite assinado sobre o pedido de volta, com um aceite já usado ou depois de outra promoção ou volta (1.7.10) | recusa; nada trocado em `em-uso/` |
| `promover` com um aceite já usado, ou de uma proposta feita antes de outra promoção ou volta (1.7.10, revisão de segurança KIT-F1) | recusa; nada trocado |
| `conferir` com `.venv`, `venv` ou `node_modules` em `atual/` (1.7.10, KIT-F5) | código 0 com `nao_conferido` e o aviso "não conferido: <pasta>"; com `__pycache__` a mais, código 1 e a dica |
| Marcador `state/banco.trava` do outro lado (vivo, velho ou ilegível) no atualizador ou no `scripts/backup_sqlite.py` (1.7.10) | param sem abrir o banco nem criar nada, com o motivo; no velho ou ilegível, também o comando do titular |

## Com o kit e scripts
Para migrar memória para o esquema 5, retornar uma instalação da 1.7.9 ou adotar o livro de cópias assinado,
leia [compatibilidade e retorno](../atualizacao-1.7.9.md); para atualizar para a 1.7.10 ou voltar dela,
[a atualização para a 1.7.10](../atualizacao-1.7.10.md). A linha da âncora da 1.7.9 (e a de uma 1.7.10 de antes)
não tem o namespace `fundacao-copia`: o `preparar-maquina.ps1` da 1.7.10 a troca pela linha com ele, com a mesma
chave, no UAC da âncora, e até o titular rodá-lo com o UAC a adoção do livro assinado não confere (Limites
conhecidos, no texto da 1.7.10).
O modo estrito usa `--exigir-livro-assinado`; preparar o documento não assina nem aprova a entrada. A chave continua
com o titular.

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
`tests/test_backup_completo.py`, `tests/test_restauracao_revisoes.py`; 1.7.10: `fundacao/core/manutencao.py` (trava
de manutenção, última cópia, situação e a regra do `.git`), `fundacao/core/limpeza.py` (sobra do preparo contada),
`fundacao/cli_backup.py` (`backup situacao` e `--detalhar`) e os testes `tests/test_backup_1710_git.py`,
`tests/test_backup_1710_cache.py`, `tests/test_backup_1710_limpeza.py`, `tests/test_backup_1710_promocao.py` e
`tests/test_backup_1710_manutencao.py`, com `scripts/tests/test_atualizar_fundacao_1710.py` (política da raiz e nova
tentativa da cópia ANTES), `scripts/tests/test_versao_em_uso.py` e `scripts/tests/test_integ_fluxob_1710_versao.py`
(o `voltar` com o aceite assinado sobre o pedido de volta, um aceite por volta, e o `promover` pela cópia conferida),
`scripts/tests/test_atualizar_fundacao_trava_banco.py` e `scripts/tests/test_backup_sqlite_trava.py` (a trava do banco
antes de abri-lo); cenários CEN-09 e CEN-16. `scripts/backup_sqlite.py` e a CLI
montam a URI do SQLite com `Path.as_uri()` (codifica `#`, `%` e espaços; sem isso, `#` vira
fragmento e o SQLite abriria outro arquivo).
