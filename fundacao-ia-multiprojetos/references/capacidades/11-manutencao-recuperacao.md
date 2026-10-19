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
  Até liberar, o destino carrega `state/restauracao-nao-liberada.json`, e a CLI e o servidor
  MCP recusam usar essa raiz.
- **Sem lacuna entre o banco e o registro** [Decisão; auditoria externa da 1.3.4]: cada decisão
  protegida grava a intenção de exportação na mesma transação (outbox) e a exporta em seguida,
  de forma idempotente (linha já gravada não se repete) e com `fsync`; falha ou queda depois do
  commit fica pendente e é exportada na próxima decisão, no `init` ou ao abrir a fundação; o
  backup recusa enquanto houver pendência não gravável. Fundação de kit anterior: o `init`
  recompõe pela trilha de eventos revogações e desativações que nunca chegaram ao registro.
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
  cópia antiga. Limite: manifesto e banco ficam na mesma pasta; quem reescrever os dois forja a
  cópia — por isso a política 3-2-1-1-0 pede uma cópia imutável. `backup verificar` que não
  confere sai com código 3; manifesto com estrutura inválida, com erro JSON e código 2.
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
- **Origem danificada:** a autorização da restauração vem do banco da cópia (somente
  leitura), não do banco que se quer recuperar; nada é criado nem migrado na origem.
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
| Banco de origem corrompido ou ausente | restauração autorizada pela cópia; origem intocada |
| Restaurar sobre a origem / sobrescrever referência anterior | recusado |
| Atualização com retorno | retorno em ambiente isolado preserva leitura do estado |

## Com o kit e scripts
`fundacao/core/backup.py` (`create_backup`, `verify_backup`, `restore` com reaplicação),
`scripts/manifesto.py`, `scripts/backup_sqlite.py`, `scripts/instalar_kit.py --atualizar`
(atualização com cópia de retorno). Testes: `tests/test_cache_backup.py::TestBackupRestauracao`,
`tests/test_restauracao.py`; cenários CEN-09 e CEN-16. `scripts/backup_sqlite.py` e a CLI
montam a URI do SQLite com `Path.as_uri()` (codifica `#`, `%` e espaços; sem isso, `#` vira
fragmento e o SQLite abriria outro arquivo).
