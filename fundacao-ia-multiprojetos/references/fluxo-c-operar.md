# Fluxo C — Verificar, manter, atualizar, recuperar e retomar

Operações sobre uma fundação existente. Origem: Apêndice C (prompts C1–C7)
[Livro p194–198] e Módulos 09–10 [Livro p159–181]. Antes de qualquer operação:
leia RETOMADA, inventário, matriz e o estado efetivo (`python -m fundacao status`
ou equivalente). Registre evidências em `evidence/<operação>/<run_id>/`. Se o `status`
recusar por falta de banco de estado, **não** rode `init` (criaria uma fundação vazia por
cima da perda): vá ao C9.

Na fundação **em uso**: acesse dados só pelos serviços da fundação, com a identidade
declarada pelo usuário; não liste recursivamente `projects/` (nomes de arquivos de outros
projetos também são dados). Provas negativas extensas (outras identidades, sondagens,
identidade não registrada) rodam numa **cópia restaurada** (C9), não na fundação viva —
lá elas gravam negativas reais na trilha e usam identidades que o usuário não declarou.

## Sumário
C1 validar entrega · C2 diagnosticar falha · C3 corrigir dentro de limite · C4
retomar em outra sessão/provedor · C5 criar outro projeto · C6 atualizar componente
· C7 promover para GOLD · C8 habilitar/desabilitar/substituir · C9 backup,
restauração e retomada · C10 auditoria operacional · C11 avaliação final da matriz
· Projetos no Ubuntu (1.7.10): porteiro, aberturas e trava do banco

---

## C1 — Validar uma entrega declarada concluída [Livro p194]
Inspecione estado, inventário, registros e arquivos produzidos; diferencie
instrução, configuração, implementação e funcionamento observado; confira se cada
evidência corresponde à versão entregue. Monte a matriz requisito → evidência →
resultado → pendência e execute verificações proporcionais ao risco, incluindo
**um cenário válido e uma negativa** (acesso, isolamento ou desativação). Não altere
o componente durante a validação; registre os defeitos. Texto da IA não é prova.
Saída: `validacao/` com matriz, procedimentos e resultados (passou · falhou · não verificável).

## C2 — Diagnosticar uma falha [Livro p195]
Entradas: projeto, `task_id`, `run_id`, esperado × observado, horário. Construa
reprodução mínima com dados fictícios; localize a etapa que diverge (entrada,
autorização, planejamento, ferramenta, armazenamento, recuperação, apresentação);
formule hipóteses e busque a evidência que refuta cada uma; diferencie causa
demonstrada, hipótese plausível e informação ausente. Confirme se o componente
estava ativo e se o contexto autenticado era do projeto. Não aplique correção aqui.
Saída: reprodução, sequência relevante, hipótese sustentada, mudança mínima proposta.

## C3 — Corrigir dentro de um limite definido [Livro p195]
Confirme que o defeito existe na versão atual; registre ponto recuperável; aplique
a menor alteração que resolve a causa demonstrada; preserve contratos de outros
projetos, dados, histórico e aprovações; **não** atualize dependências sem relação,
não desative controles, não remova testes. Repita a reprodução, um comportamento
vizinho e a negativa de isolamento/permissão. Ampliação de escopo = preparar para
revisão e seguir o independente. Saída: diff, resultados, procedimento de reversão.

## C4 — Retomar em outra sessão ou provedor [Livro p196]
Não presuma acesso a conversas ou memória interna de outro aplicativo. Confira
registro persistente, artefatos, versões, pendências, aprovações vigentes e hashes
antes de confiar em resumos. Produza primeiro um **entendimento verificável**
(objetivo, último resultado confirmado, trabalho restante, próximo passo
autorizado); recupere uma decisão aprovada e sua origem; confronte uma tentativa
fictícia de acesso a outro projeto. Antes de repetir ação com efeito, consulte o
estado dela e preserve os identificadores de deduplicação. Grave novo `run_id` e
`provider_id`. Transferência manual entre interfaces = "transferência manual
assistida", não integração [Livro p73, p181].

## C5 — Criar outro projeto pela base comum [Livro p196–197, A36 p179]
Receba finalidade, entregas, responsáveis, recursos e restrições; confira que o
identificador e o destino estão livres; gere pelo modelo com configuração própria,
fontes vazias e referências aos componentes comuns escolhidos; registre versão do
modelo; **não copie** documentos, memórias, credenciais ou históricos de outros
projetos; integrações sem acesso/custo autorizado ficam desativadas. Prove: leitura
permitida no novo projeto, negativa contra recurso privado de outro, componente
desativado sem execução, projeto visível na seleção. Kit: `python -m fundacao projeto criar ...`.

## C6 — Atualizar um componente compartilhado [Livro A33 p167–169, p197; 3.0 R13.4–R13.5]
Seis etapas: **preparar** (versão atual, motivo, arquivos e consumidores, estado
recuperável) → **ler** notas oficiais/migração datadas → **isolar** (cópia/ambiente
de teste; uma mudança por vez, nunca "atualizar tudo") → **comparar** (contratos de
entrada/saída, estado persistido, segurança, operação; mesma amostra dos projetos;
para modelos, qualidade de domínio) → **decidir** (aprovada · reprovada ·
insuficientemente verificada; adiar é opção registrada) → **promover ou retornar**.
Mudança de banco: defina compatibilidade de leitura e retorno antes de escrever dados
novos (`PRAGMA user_version` + scripts numerados; *expand/contract*); reverter código
não reverte dados. Versão declarada ≠ versão carregada pelo host: recarregue e confira.
Fixe versões de CLIs, SDKs e modelos no perfil "dados reais".
Kit, em um comando [Decisão; 1.5.0]: `python <skill>/scripts/atualizar_fundacao.py checar --raiz <raiz>`
(só lê, sem executar nada da raiz: versões, o que muda, alteração local pelo hash registrado na instalação,
executável desconhecido, identidade, cadeia) e
`aplicar --raiz <raiz> --backups <outro disco>`: backup ANTES verificado → ensaio do kit novo numa cópia
restaurada (`init`, cadeia, suíte; falha que já existia não bloqueia, regressão bloqueia sem tocar a raiz)
→ promoção → instruções da raiz (`AGENTS.md` e `CLAUDE.md` regenerados, com os anteriores guardados em
`registry/kit_backup/instrucoes-<data>/`; `AGENTS.md` escrito à mão não é tocado e o resumo traz o comando com
`--adotar`) → backup DEPOIS (que as leva) → registro em `evidence/atualizacoes/`; `desfazer --registro <arq>`
devolve o código, e as instruções não editadas depois, se o `user_version` do banco não mudou e o registro confere
com a âncora. Kit igual, skill nova [Decisão; defeito anotado na liberação da 1.7.6]: o `aplicar` confere o texto
que `instrucoes_raiz.py gerar` produziria e, se for outro, regenera só as instruções da raiz, pelas mesmas regras
(anteriores guardados, registro com o hash antes e depois, `desfazer` aceito); sem diferença, não escreve nada.

**Na 1.7.10.1** (skill nova, kit 1.7.10 igual): o `aplicar` só regenera as instruções da raiz; o que muda é o preparo
do Ubuntu e a ferramenta do titular, com o aceite de risco do canário ([correção 1.7.10.1](atualizacao-1.7.10.1.md)).

**Na 1.7.10.2** (skill nova, kit 1.7.10 igual): o `aplicar` também só regenera as instruções da raiz. O hook
`guarda_ferramentas.py` muda: depois da liberação, o titular roda o `preparar-maquina.ps1` e o `preparar-wsl.sh` com
todos os projetos, porque o lançador de cada um confere os hooks da raiz ([correção 1.7.10.2](atualizacao-1.7.10.2.md)).

**Na 1.7.10, o `aplicar` faz também** [Decisão; 1.7.10] (compatibilidade, o que muda e o que o `desfazer` não volta:
[atualização para a 1.7.10](atualizacao-1.7.10.md)):
- recusa com o WSL ligado, no começo e antes da restauração do ensaio, sem alterar nada, porque o banco não abre pelos
  dois lados. Fechar o Ubuntu é do titular: ele fecha as sessões do Ubuntu e, no PowerShell, roda
  `wsl --terminate <distribuição>`. O executor nunca roda `wsl --shutdown` nem `--terminate`: com o Ubuntu ligado, ele
  para e pede. Com o marcador do Ubuntu em
  `state/banco.trava`, o `checar`, o `aplicar` e o `desfazer` param na etapa `banco` ("Trava do banco", abaixo);
- grava a trava de manutenção `state/manutencao.json` do começo ao fim, também na falha, e o lançador do Ubuntu não
  abre sessão com ela; trava que já existe recusa: confira o pid e o host dela e, sem manutenção em andamento,
  apague-a;
- monta o ensaio numa pasta nova dentro de `--pasta-ensaio` (padrão: a de `--backups`, no disco das cópias; dentro da
  raiz, recusa); mostra no começo a estimativa de tempo, e `--prazo` (segundos por subprocesso longo, no mínimo 60) tem
  padrão derivado dela; conta o que sobra da limpeza do ensaio; tenta de novo, uma vez, a cópia ANTES que falha na
  promoção;
- depois da promoção e antes da cópia DEPOIS, acrescenta `em-uso` e `.claude/projetos` à lista `incluir` de
  `registry/backup_policy.json` (o `desfazer` não a volta: capacidade 11).

**Depois do `aplicar`, os passos do titular** (o atualizador não copia hooks nem mexe no host;
`references/fluxo-a-implantar.md` §Host): numa fundação vinda da 1.7.9, primeiro o registro da origem de cada projeto
vindo de outra pasta (passo 2 do §Host: o `registry/projetos-host.json` é novo, e o preparo do Ubuntu tira dele as
origens; [atualização para a 1.7.10](atualizacao-1.7.10.md), Ordem, passo 3); no Windows, o preparo da máquina, com o
UAC (`assets/host/windows/preparar-maquina.ps1`, passo 4 do §Host), que copia os hooks novos para
`<raiz>/.claude/hooks/`, refaz o perfil do Windows e, com um Python instalado para todos os usuários, grava a cópia
protegida da ferramenta do titular da versão nova; no Ubuntu, o `assets/host/wsl/preparar-wsl.sh` com cada projeto,
que confere os hooks e o kit da raiz contra os da skill e refaz a área do titular, o lançador e a cópia protegida do
Ubuntu; por fim, o canário, com o perfil novo (o item C do checklist de cada projeto volta a pendente). Até lá, o
lançador de cada projeto recusa abrir: os hooks e o kit da raiz mudaram desde o preparo.

Catraca [Decisão; 1.7.0]: no ensaio, teste que passava e some ou passa a ser pulado também é regressão, salvo
retirada declarada pelo kit novo em `tests/testes_retirados.json` (ID → versão e motivo); o arquivo de código que
o kit anterior instalou e o novo não tem mais (órfão) sai da raiz guardado no backup da promoção e volta no
`desfazer`. O `registry/kit_install.json` e os registros em `evidence/atualizacoes/` são dados (graváveis por shell)
[revisão de segurança da 1.7.0]: caminho que o instalador nunca grava (com `..`, absoluto ou com barra invertida) não
vira órfão e faz o `checar` recusar; caminho que passa por ligação ou junção dentro da raiz (ex.: `tests/elo` →
`.claude`) também recusa (instalação: código 4); o `desfazer` só aceita o registro da própria raiz, com cópias em
`registry/kit_backup/`, caminhos sem ligação no meio e instruções só em `AGENTS.md` e `CLAUDE.md`, e confere tudo
antes de alterar qualquer arquivo.
Nada da raiz roda antes de conferido [Decisão; auditoria Codex Security da 1.7.6, #8]: o `checar` não importa o
pacote da raiz; a cadeia de eventos é recalculada pelo kit da skill, com o banco aberto somente leitura, e vale
`cadeia_integra` (o `eventos verificar` sai com código 0 mesmo com a cadeia quebrada). Executável nas áreas de
código (`fundacao/`, `templates/`, `tests/`: `.py`, `.pyc` fora do `__pycache__`, `.pyd`, `.so`) que nem o kit novo
nem o registro da instalação conhecem, ou com outro hash, e ligação nelas fazem o `checar` recusar
(`executaveis_a_mais`) — inclusive teste local em `tests/` que o kit não instalou: retire-o ou mova-o para fora
dessas pastas. O código ANTES (backup ANTES e restauração do ensaio) roda de uma cópia conferida por hash; `init`,
cadeia e backup DEPOIS, do kit da skill; sempre com `python -I`. As duas suítes do ensaio rodam de cópias conferidas,
com os módulos enumerados da lista, nunca da árvore viva; de `registry/` levam a configuração, não as cópias do código
que a promoção guarda em `registry/kit_backup/` [revisão de segurança da 1.7.7, R177-ATU-01]. O `__pycache__` não é
conferido nem recusa (o Python o refaz da fonte), mas `.pyc` plantado ali rodaria no lugar da fonte: o `checar` o
lista em `bytecode_a_apagar` e a promoção o apaga das áreas de código, sem seguir ligação; `__pycache__` que é
ligação recusa [mudança de critério; R177-ATU-02]. Com o kit igual, o `aplicar` não o apaga: apagar o `__pycache__`
é sempre seguro. O primeiro nível da raiz também é conferido [mudança de critério; segunda passada, R177B-B-06]: o
uso normal (`python -m fundacao` com a raiz como pasta atual) a põe no caminho de importação, à frente da biblioteca
padrão, e um `argparse.py` ali rodaria no lugar do módulo. Módulo (`.py`, `.pyw`, `.pyc`, `.pyd`, `.so`), `.pth` e
pacote (pasta com `__init__` executável) do primeiro nível que nem o kit novo nem o registro conhecem fazem o `checar`
recusar (`executaveis_a_mais`): tire-os da raiz ou ponha-os numa subpasta que não seja pacote; ligação com esses nomes
ou com o de `__pycache__` também recusa, e o `__pycache__` do primeiro nível sai na promoção, como o das áreas de
código. A pasta `mcp/` (o nome de primeiro nível que o kit importa de fora da biblioteca padrão, comparado sem caixa)
entra mesmo sem `__init__` [terceira passada, R177C-B-03]: sem o SDK do MCP instalado, o Python a monta como pacote de
namespace, e o servidor MCP do kit rodaria o que ela tiver; executável dela e ligação com esse nome ou dentro dela
recusam, e o próprio servidor trata esse namespace como SDK ausente. As demais pastas sem `__init__` continuam fora do
inventário. O que for plantado na raiz depois do `checar` ele não vê: rode sem outra sessão gravando nela. Limite: o
hash registrado vem do `registry/kit_install.json`, que a mesma conta grava; quem troca código e registro juntos passa
por versão anterior (`references/seguranca-isolamento.md` §6).
Plano do `desfazer` autenticado [Decisão; auditoria Codex Security da 1.7.6, #10]: o `aplicar` anota o SHA-256 de
cada registro que o `desfazer` pode usar (atualização promovida, mesmo com falha depois) em
`registry/atualizacoes.jsonl`, fora de `evidence/`. Vale também para a promoção que o instalador interrompeu depois de
gravar (saída sem `nada_escrito`, como o código 3 com o registro da instalação não gravado — ligação no lugar dele, ou
histórico ilegível ou trocado, que o instalador não lê como histórico nem refaz): o `aplicar` apaga o
`__pycache__`, grava o registro com a promoção marcada como interrompida e o ancora antes de parar, com o comando
pronto em `para_voltar`; com `nada_escrito`, para sem tocar a raiz; sem saída legível do instalador, não há plano, e a
volta é a cópia ANTES (C9) [terceira passada, R177C-B-04]. A promoção que falhou e o próprio instalador desfez (código
5, `desfeito`, composição `nao_alterada`; no Windows, por exemplo, arquivo preso pelo antivírus) conta como
`nada_escrito`: o código da raiz é o de antes, o `aplicar` para sem âncora e sem tocar a raiz e diz isso; resolva o
que está em `erros` e repita [quarta passada, R177D-5]. Registro alterado depois, forjado ou de versão anterior do
atualizador não confere, e a volta é a cópia ANTES (C9); a âncora fica em `registry/`, com o mesmo limite acima.
Substituídos, copiados e órfãos retirados só podem estar
nas áreas de código — nunca `state/`, `projects/`, os dados de `registry/` nem `evidence/`. O `desfazer` acrescenta a
volta ao `registry/kit_install.json`, e o `checar` seguinte vê de novo a versão anterior a atualizar, não "alterado
localmente" [achado na validação da 1.7.7]. Ele só devolve se o código ainda é o que a atualização deixou
(`sha256_novo`): repetido, ou depois de outra atualização, recusa sem alterar nada.
Gravação sem seguir ligação [Decisão; revisão de segurança da 1.7.7, R177-ATU-03]: o atualizador e o
`instrucoes_raiz.py` gravam por temporário de nome imprevisível, criado com exclusividade e posto no lugar com
`os.replace`; registro novo com exclusividade; âncora acrescentada sem seguir ligação nem vínculo físico. Ligação no
caminho ou vínculo físico em `registry/kit_backup`, `registry/kit_install.json`, `registry/atualizacoes.jsonl` ou
`evidence/atualizacoes` faz o `checar` e o `desfazer` recusarem, e o `aplicar` confere de novo logo antes da promoção:
o que apareceu durante o ensaio para na etapa `promocao`, sem tocar a raiz; o `instalar_kit.py` grava o
`registry/kit_install.json` pelo mesmo padrão [segunda passada, R177B-B-05]. `AGENTS.md` ou `CLAUDE.md` que é ligação
não é lido nem gravado (o resumo avisa). O inventário do host roda depois do registro e da âncora, com 120 s: travar
ou falhar aparece no resumo como "inventário do host não conferido", e a atualização registrada fica [R177-VAL-04].
Etapa deixada em `running` pelo kit anterior é refeita
quando a posse vence (o recibo antigo não basta): reconcilie efeitos externos antes de retomar.
Passo a passo: `python <skill>/scripts/instalar_kit.py --destino <raiz>` monta o plano antes de
escrever. Com conflito (código alterado localmente), **nada é escrito**: a saída traz o plano
(`conflitos_preservados`, `atualizacao_incompleta: true`, `kit_version: null`) e o código 3.
Depois da decisão: `--atualizar` substitui os arquivos de código diferentes e guarda a versão
anterior em `registry/kit_backup/<data>-<sufixo>/` (retorno = copiar de volta; código 5 com
`desfeito: false` = o retorno também falhou) e retira os órfãos, guardando-os ali também (sem `--atualizar`,
órfão também dá código 3, com nada escrito); `--manter-conflitos`
aceita, por decisão explícita, um estado **misto** (copia o que falta, preserva os conflitos,
anota `composicao: "mista"` em `registry/kit_install.json` e sai com código 3). A configuração
local (`registry/`: rotas, componentes) nunca é sobrescrita, nem com `--atualizar`. Ligação ou
junção que leve para fora do destino recusa a instalação inteira (código 4). A versão só é
declarada quando a composição foi conferida arquivo a arquivo (`composicao: "verificada"`,
código 0). Depois de atualizar, rode `python -m fundacao init` na raiz (idempotente): migra o
banco, exporta decisões protegidas pendentes, cria a identidade do registro de retiradas se
faltar, repara derivados de memórias já retiradas e preenche as retiradas e revogações que
estão no banco e faltam no registro; sem isso, o `backup criar` recusa. Faça então um backup
novo — cópias anteriores à 1.3.0 não têm a identidade anotada (ver C9). Componente habilitado
cujo código mudou na atualização é recusado no despacho até ser habilitado de novo (C8).

## C7 — Promover conhecimento para GOLD ou base comum [Livro p198, A13 p77–78]
Separe fato, decisão, hipótese e preferência; confira nas fontes; preserve exceções;
marque conflitos sem escolher silenciosamente; remova detalhes do caso (inclusive em
nomes de arquivos e metadados); calcule o hash da proposta e apresente as diferenças
à autoridade competente. Sem aprovação aplicável ao conteúdo, finalidade e escopo
exatos: entregue a proposta revisável e mantenha pendente. Com aprovação: publique
**novo** registro, preserve o original restrito, teste leitura pelo público aprovado,
negativa ao conteúdo privado e retirada dos derivados. Ver `capacidades/05-gold.md`, `capacidades/04-memoria.md`.

## C8 — Habilitar, desabilitar e substituir [Livro A34 p170–173]
Separe instalado · habilitado · saudável · autorizado. Desativação completa: (1)
bloqueie novas tarefas no registro; (2) trate execuções em andamento por política
explícita (terminar, cancelar ou *drain*); (3) verifique **todos** os caminhos —
conversa, código, hooks, filas, tentativas, agendadores, MCP e plugins; (4) avalie
credencial exclusiva × compartilhada antes de revogar. Substituição preserva o
contrato percebido pelos consumidores; normalize o equivalente e declare o que não é;
*fallback* nunca envia dados a destino não autorizado; reavalie caches e índices
dependentes (vetores de modelos diferentes não são intercambiáveis). Prove ausência
de novos efeitos com evento controlado. Kit: `python -m fundacao componente desabilitar --id <id>`
(a desativação vai para o registro protegido: restaurar uma cópia anterior a reaplica).
**Componente lido pelo host** (`entrypoint: "host-skill:<caminho do SKILL.md>"`, ex.: skill de
projeto do Claude Code): o kit não o executa, e desabilitar no registro **não** o desliga no
host, que lê a pasta. A retirada tem dois passos: (1) `componente desabilitar` no registro — o
comando avisa (`W_SKILL_DE_HOST_AINDA_NO_DISCO`, na saída e no stderr) enquanto o arquivo
existir, sem apagar nem mover nada; (2) retirar a pasta do alcance do host (mover para uma pasta
de guarda fora de `.claude/skills/`, com hash conferido), e só então conferir que o host não a
carrega. Habilitar um componente executável grava no registro o hash do código aprovado
(`entrypoint_sha256`); código que mudou depois disso (atualização, edição) é recusado no
despacho até ser revisado e habilitado de novo. O ponto de entrada precisa ser código da
própria fundação (`fundacao.components.<modulo>:<funcao>`); código guardado em pasta de projeto
não é despachado.

## C9 — Backup, restauração e retomada [Livro A35 p174–177; A18 p99]
Defina conjunto de recuperação (canônicos × reconstruíveis), RPO e RTO antes do
teste. Snapshot consistente; registre eventos posteriores (decisão nova, fonte
retirada, efeito confirmado); restaure em **destino diferente**; recrie ambiente;
**reaplique retiradas e reconcilie efeitos posteriores antes de liberar**; valide
integridade, versões, contratos, negativas, memória vigente, citações e caches;
retome sem repetir efeito confirmado; meça tempo e perda observável. Sem registro
de retiradas disponível, a restauração não está pronta para usuários.
Kit: `python -m fundacao backup restaurar --origem <ref> --destino <novo> --retiradas <log>`
(backup e restauração copiam todos os projetos: exigem identidade com `admin` na fundação).
A cópia leva `fundacao/`, `registry/`, `templates/`, `projects/`, `AGENTS.md`, `CLAUDE.md`, o banco e os registros
da fundação — `docs/`, `evidence/`, `ferramentas/`, `tests/` e `RETOMADA.md` e, depois do `aplicar` da 1.7.10,
`em-uso/` e `.claude/projetos/` (C6) —, sem complemento à parte; a lista dos registros fica em
`registry/backup_policy.json` (`{"incluir": [...]}`). Ficam fora o `.env` e o reconstruível (`__pycache__`, `.venv`,
`node_modules` e, desde a 1.7.10, `.cache`); o `.git` só entra dentro dos projetos, sem ganchos nem configuração com
credencial ou programa; o arquivo com cara de segredo entra como está, sem ser lido, contado em `segredos_incluidos`,
e a cópia não é cifrada (capacidade 11). O `backup criar` e o `backup restaurar` recusam destino dentro da raiz
(inclusive `<raiz>/copias`): guarde e restaure fora dela, de preferência em outro disco. No desastre, rode o
`backup restaurar` com `--raiz` na raiz danificada, para o kit poder recusar destino dentro dela. A política compara
`state/` e `.git` sem caixa e pelo caminho resolvido (`State`, `STATE`, `state.`, `.` e ligação no meio recusam) antes
de copiar.
Cópia semanal [Decisão; 1.7.10; capacidade 11]: o `backup criar` trava a manutenção (`state/manutencao.json`) do
começo ao fim, também na falha, e o lançador do Ubuntu não abre sessão nesse meio-tempo; ele devolve um resumo (a
lista de arquivos, só com `--detalhar`) e grava `registry/ultima-copia.json`, que o `backup verificar` bem-sucedido
anota. `python -m fundacao backup situacao` (administração ou auditoria) diz a idade da última cópia e, passados 7
dias, avisa (`W_COPIA_ANTIGA`) com os comandos prontos da próxima cópia e da verificação. Nas sessões do Windows, o
hook `assets/hooks/aviso_copia.py` lembra o mesmo no início da sessão. É lembrete, não prova: a prova é o
`backup verificar` com o `sha256_manifesto` guardado fora da cópia. Depois da primeira cópia numa pasta nova, o
titular roda de novo o `assets/host/windows/preparar-maquina.ps1` com `-Backups` e a pasta das cópias: só assim o
perfil das sessões do Windows nega a leitura e a edição delas; com a cópia registrada, os scripts do Windows recusam o
`-SemBackups` e trazem a pasta no comando pronto (fluxo A §Host). A sobra de um preparo que falhou
(`W_SOBRA_DO_PREPARO`) é contada, nunca apagada em silêncio: apagá-la é do titular, depois de conferir.
Âncora da cópia [varredura da 1.4.5, #8]: o `backup criar` devolve `sha256_manifesto` e o anota em
`state/copias.jsonl`, ao lado do registro protegido; guarde o código fora da pasta da cópia e o
livro junto do registro. A restauração confere a cópia por ele (`--sha256-manifesto` ou o livro ao
lado de `--retiradas`): âncora errada não libera; sem âncora, não libera — nem com o código
`fundacao/` igual ao do kit — salvo `--aceitar-copia-sem-ancora "<motivo>"` (decisão do
administrador, com o motivo na resposta e na trilha, e aviso `W_COPIA_SEM_ANCORA`) [Decisão;
auditoria Codex Security da 1.7.6, #2]. O livro só vale tanto quanto `state/` está protegido (no perfil
de dados reais do WSL, a sessão grava `state/` e a pasta de backups): a conferência por ele sai com
`aviso_ancora` (`W_ANCORA_DO_LIVRO`), e, depois de suspeita de comprometimento, vale só o
`--sha256-manifesto` guardado fora; livro e registro dentro da própria cópia não valem [revisão de
segurança da 1.7.7, R177-KIT-01].
Quem verifica e restaura [auditoria da 1.7.6, #2]: com a fundação viva, a política dela (quem perdeu
a administração depois da cópia não restaura; administração forjada na cópia não conta); com o
banco de origem corrompido ou perdido, a política da cópia, só se a âncora a autenticar — sem
fundação viva e sem âncora, ninguém (código 2): guarde o `sha256_manifesto` fora da cópia, é ele a
prova na recuperação de desastre. Nada é criado na origem. Preparo privado [auditoria da 1.7.6,
#12]: a restauração monta a raiz numa pasta de preparo ao lado do destino, lendo a cópia sem seguir
ligação, confere de novo antes de promovê-la (renomeação atômica) e só então o destino a recebe;
ligação no caminho da cópia ou do destino recusa. Não libera (código 3) quando
o registro de retiradas não foi informado, não existe no caminho dado, é ilegível, tem
identidade diferente da anotada na cópia (outra fundação ou registro recriado) ou não alcança
as linhas conhecidas na cópia — e, nesses casos, nada é copiado para o destino. Retiradas de
fontes **e de memória** e revogações de acesso posteriores à cópia são reaplicadas antes de
liberar, com eventos na trilha restaurada. O `init` cria o registro com identidade
(`state/retiradas.jsonl`). Cópia de kit anterior à 1.3.0 sem retiradas: só com
`--aceitar-registro-nao-comprovado`, depois de conferir o registro à mão (decisão da
administração, registrada). Destino com `state/restauracao-nao-liberada.json` não é usado.
A verificação confere também o banco da cópia contra o manifesto (hash, nas cópias da 1.3.1 em
diante, e contagens; cópia mais antiga, só contagens, com aviso) e sai com código 3 quando não
confere; desativações de componente posteriores à cópia são reaplicadas; o que não é
reaplicado (concessões, habilitações, arquivos como `registry/route_policy.json`) vem listado em
`nao_reaplicado` — confira antes de liberar o uso. A raiz restaurada roda o kit que veio na
cópia: se a resposta trouxer `acao_necessaria`, atualize o kit nela e rode `init` antes de usar.
Cópias podem ficar em pasta de rede (UNC); restaure a fundação que será usada em disco local
(destino em rede vem com `aviso_destino`).
Registro protegido sem lacuna [Decisão; auditoria externa da 1.3.4]: toda revogação, retirada e
desativação grava a intenção de exportação **na mesma transação** da decisão (outbox) e a exporta
logo depois; se o append falhar ou o processo cair no meio, a pendência é exportada na próxima
decisão protegida, no `init` ou ao abrir a fundação pela CLI (com aviso
`W_REGISTRO_PROTEGIDO_PENDENTE` enquanto não der). O `backup criar` exporta antes e **recusa** a
cópia se houver pendência que não consiga gravar. Escritores ativos durante a restauração: o
registro é relido depois da reaplicação e o que entrou nele no intervalo também é reaplicado;
o registro do destino recebe exatamente o conteúdo reaplicado (`corte_do_registro` na resposta),
de modo que banco e registro do destino ficam no mesmo corte; registro reescrito ou que não para
de mudar impede a liberação. Para um corte sem escritores, pare as sessões que operam a origem
antes de restaurar.
Cenário realista adicional: perda do log posterior e "agente apagou dados e backups
locais" → exige cópia fora da máquina [3.0 R13.1, R13.3].

## C10 — Auditoria operacional [Livro A32 p163–166; 3.0 R10]
Amostra: uma execução de cada projeto, com falha ou interrupção. Reconstrua por
`run_id` (entrada, escopo, componentes, operações, resultado, aceite); compare o
painel com registros brutos (denominadores, nulos ≠ zero, tarefas interrompidas
incluídas); confira citações RAG, correções de memória, revogações e negativas;
confirme que componentes desativados não recebem tarefas por caminho algum; use
exemplos de controle com erro conhecido para provar que o revisor detecta.
Corrija o estado de requisitos declarados sem evidência. Modelo:
`assets/templates/AUDITORIA.md`; na auditoria operacional, o kit confere a cadeia de hashes com
`python -m fundacao eventos verificar`. Auditoria de segurança somente leitura da fundação em uso:
`assets/templates/AUDITORIA-SEGURANCA.md` (enxuto: comandos copiados, divergências de método, resposta final
copiada do relatório). Revisão de segurança de uma versão (diff da anterior para a nova), somente leitura,
relatório privado: `assets/templates/REVISAO-SEGURANCA.md`. Os dois modelos de segurança
(`assets/templates/AUDITORIA-SEGURANCA.md` e `assets/templates/REVISAO-SEGURANCA.md`) seguem as seis regras de
escrita do topo de `assets/templates/REVISAO-SEGURANCA.md` (frase de fato com o comando e o trecho literal; saída
cortada sustenta só o que mostra; sem autorização expressa do pedido, não copiar nem executar a árvore revisada).
Nos dois, use caminhos absolutos e não mude o diretório do shell para dentro da árvore revisada: o Claude Code com
sandbox cria `.claude/.cc-writes` no diretório atual do shell (`references/fontes-verificadas.md`, §1).
Auditor independente (outro agente/provedor ou humano) sempre que possível [3.0 R9.5]. Nos dois modelos de
segurança, antes de redigir os achados, preencha o quadro de afirmações: fonte, resultado observado, escopo e
condições ainda não verificadas.
O registro de operações (em `assets/templates/REVISAO-SEGURANCA.md`; no esqueleto, a tabela de comandos executados)
sustenta também o método: leituras, erros e
recusas relatados devem corresponder às operações emitidas e aos resultados recebidos.
Fato sustentado por outra operação não comprova que a ação alegada foi executada.
Com recibos externos, cada ação ou erro relatado deve corresponder a um ID e ao resultado
registrado. Uma lembrança ou plano sem esse vínculo não comprova ocorrência, nem uma
falha do controlador. Não descreva uma saída local ou chamada omitida sem prova própria;
retire esse relato e marque a verificação como não comprovada. Ressalvá-lo não o valida.
Derive do quadro os títulos, as conclusões e a resposta final; releia-os contra o quadro e o
rastro. Remova ou limite cada afirmação sem suporte. Fonte excluída não sustenta
ausência; ocorrência posterior não comprova causa; pré-requisito não verificado
mantém o alcance e o impacto dependentes dele como hipóteses.
Declare confiança por achado; nos dois modelos de segurança, confira os campos pela seção de conferência formal
antes da entrega. Com recibos externos, confronte quantidade e hash com a cópia efetivamente entregue: a consulta pode
ter sido acrescentada ao recibo atual depois de gerar a saída lida. O conferidor auxiliar da skill recebe apenas
literais por stdin e não verifica mérito ou acesso; sua aprovação formal não substitui o quadro, o rastro ou o
auditor independente. Uma atribuição sobre o que um script consulta exige trecho ou resultado efetivo; o nome
inventário/auditoria não prova consulta de âncoras, ACLs ou isolamento.

**Reavaliação do comportamento** [análise do vibe-coding-toolkit, 21/10/2026]: mudou a versão do host (Claude
Code ou Codex — a atualização automática conta), os hooks, as instruções (AGENTS.md/CLAUDE.md) ou a skill →
rode de novo as avaliações E3 (retomada), E10 (RETOMADA desatualizada) e E12 (pergunta de andamento) e o
cenário CEN-13 (hooks), numa sessão aberta **fora** de uma fundação com os hooks do host (os guardas da raiz
bloqueiam a escrita e a identidade de ensaio e distorcem o resultado). O avaliador fica fora do alcance de quem
é avaliado: bancada do avaliador e área do executor separadas, cópia da skill sem `evals/` e um alarme antes de
entregar o pedido; execução cujo rastro leu o gabarito fica "contaminada" [Decisão; harness2, P2]. Avaliação não
rodada fica "não rodada", nunca "passou"; uma rodada que passa é teste de fumaça, não taxa de confiabilidade; com k
execuções, a de segurança só passa se passar em todas (pass^k) [Decisão; everything-claude-code, proposta 4]. Caso
novo nasce de falha real observada, não para engordar a bateria.

## C11 — Avaliação final e fechamento da matriz [Livro A36 p178–181]
Reconcile cada requisito com implementação, integração, teste, evidência, estado e
bloqueio, revisando bloqueados → inativos → ativos. Demonstrações integradas:
(1) dois provedores com memória externa e negativa entre projetos; (2) fluxos dos
dois projetos de aplicação; (3) desativação, substituição, restauração e retomada;
(4) novo projeto `pesquisa-lab` pelo modelo. Para bloqueios, especifique a condição
mínima de resolução; não declare conclusão se algum requisito obrigatório não foi
demonstrado. Registre o que o usuário demonstrou ao orientar, avaliar, pedir correção
e criar projeto (R51) — o registro descreve o que foi observado, não o que se supõe.

## Projetos no Ubuntu (1.7.10): porteiro, aberturas e trava do banco
[Decisão; 1.7.10.] Cada projeto com dados reais trabalha numa sessão própria do Ubuntu, aberta pelo lançador
`abrir-fundacao-<p>` (preparo: `references/fluxo-a-implantar.md` §Host). Com a raiz em `/mnt/<letra>`, as camadas
abaixo são lógicas até o canário passar (`references/seguranca-isolamento.md` §8).

**Porteiro: o banco pela fila.** Na sessão do projeto, `python3 -m fundacao ...` não abre o banco: o cliente do kit
grava um pedido em `projects/<p>/.porteiro/pedidos/` e espera a resposta em `respostas/`. O porteiro
(`assets/host/wsl/porteiro.py`), iniciado pelo lançador fora do sandbox, roda o kit com a identidade `sessao-<p>`,
presa ao projeto do lançador, e devolve a mesma saída e o mesmo código de saída. As decisões que a sessão prepara
continuam assinadas pelo titular.
- Pedido tipado: só o mapa fixo do que a sessão usa — `status`; `tarefa criar|ver|concluir`;
  `decisao preparar|verificar|registrar|comando|conferir-ancora`; `abertura preparar|verificar|vigente`;
  `conhecimento listar|buscar`; `memoria licao propor|consultar|pendente`. Nunca `init`, `projeto`, `acl`,
  `componente`, `backup`, `copia-assinatura`, `rota`, aprovar, curar, `--raiz` ou `--ancora`. Na 1.7.10, nem `eventos`
  nem `memoria licao historico` (voltam na 1.7.11, restritos ao projeto), e nenhum caso pelo serviço (abrir por caso é
  decisão do titular). `git-enviar`, `executar` e `rodar`: 1.7.11.
- Recusa do porteiro: código 2, com `E_PORTEIRO` e o motivo. "não rodou; repita": o pedido esperou mais de 15 s na
  fila e na vez do banco e não rodou; repetir é seguro. "pode ter rodado: confira o efeito antes de repetir": o cliente
  desistiu depois de o porteiro tirar o pedido da fila; repetir às cegas pode fazer em dobro. Cada pedido tem até 100 s
  no kit.
- Um porteiro por projeto; o servidor MCP do kit não inicia na sessão travada. O titular e o coordenador seguem usando
  `eventos` pelo Windows.
- Para o titular conferir, sem conteúdo: `~/.fundacao/porteiro/<p>/registro.jsonl` (id, operação, código e duração) e
  `~/.fundacao/porteiro/<p>/saida.log` (os avisos `W_PORTEIRO_*`). `W_PORTEIRO_TRABALHO_MANTIDO` traz o pid de um kit
  de uma sessão anterior ainda de pé: encerrá-lo libera a pasta na próxima abertura. Antes de abrir, o lançador roda o
  `conferir` do porteiro (`porteiro.py conferir --config <área>/porteiro.json`): 0 abre, 2 não abre.

**Caminho de uma abertura** (a ficha é fechada por padrão; regras e tetos: `references/seguranca-isolamento.md` §8.3):
1. A sessão faz o rascunho e preenche `motivo`, com as palavras do titular, e `consequencias`. O levantamento só lê;
   o rascunho só abre rede (nunca WebFetch nem WebSearch) e só propõe plugin de `plugins-candidatos/`:
   ```
   python3 -I -B <skill>/scripts/levantar_aberturas.py --pasta <pasta> --projeto <p> --rascunho <arquivo>
   ```
2. A sessão prepara a ficha: valida pelos tetos fixos, numera, grava `outputs/aberturas/ficha-v<N>.json` e mostra, em
   `para_o_titular`, a forma fixa da ferramenta do titular, só com raiz, projeto e versão:
   ```
   python3 -m fundacao abertura preparar --projeto <p> --rascunho <arquivo>
   ```
3. O titular assina fora do Claude, pela caixa Executar (Win+R), com o texto de `executar_windows` ou de
   `executar_ubuntu`. A ferramenta mostra o que a ficha abre (o que vem com `|` na frente foi escrito pela sessão),
   pede o nome do projeto e a senha da chave e grava a ficha e o `.sig` na caixa de entrada
   `<raiz>/.claude/projetos/<p>/ficha/`. As formas `powershell` e `bash` e o `preparar-projeto.ps1 -AssinarFicha` são
   o último recurso: o perfil do shell, que uma sessão pode ter gravado, carrega antes (também num terminal novo). A
   forma cuja cópia protegida falta vem como pendente (`<forma>_pendente`), com o passo do preparo que a instala.
4. O preparo do Ubuntu instala: o `preparar-wsl.sh` do projeto (fluxo A §Host, passo 5) confere a assinatura e copia a
   ficha para a área do titular, de dono root; não instala versão menor que a maior já instalada e só a aplica com o
   canário aprovado.
5. O lançador abre a sessão com o perfil novo e recusa a ficha vencida. O `vigente` diz o que vale, sem abrir o banco;
   o `verificar` confere a ficha preparada e a assinatura dela:
   ```
   python3 -m fundacao abertura vigente --projeto <p> --json
   python3 -m fundacao abertura verificar --projeto <p>
   ```
- Fechar um item é uma ficha nova, sem ele, pelo mesmo caminho. Ficha vencida, recusada ou ausente fecha tudo, sem
  voltar à anterior, que pode ser mais aberta. A caixa de entrada não é autoritativa: no Ubuntu, vale a área do
  titular.

**Trava do banco** (`state/banco.trava`; o banco nunca é aberto pelo Windows e pelo Ubuntu ao mesmo tempo): o porteiro
grava o marcador (lado `ubuntu`) do começo ao fim da sessão do projeto, renova-o a cada 30 s e o tira ao sair. O kit do
Windows recusa abrir o banco com o marcador do outro lado, vivo, velho ou ilegível (`E_BANCO_TRAVADO`, código 2):
feche as sessões do Ubuntu antes de operar a fundação pelo Windows. `python -m fundacao banco situacao` mostra o
marcador sem abrir o banco. Marcador velho (sem renovação há mais de 120 s, como o de um Ubuntu desligado à força) não
sai sozinho: o titular, com as sessões do Ubuntu fechadas, roda `python -m fundacao banco destravar --confirmar`, que
recusa o marcador ainda vivo. Limite: os comandos curtos do Windows não gravam marcador (a trava de manutenção cobre a
cópia e a atualização), e quem grava `state/` forja ou apaga o marcador: é guarda-corpo contra o engano, não barreira.
