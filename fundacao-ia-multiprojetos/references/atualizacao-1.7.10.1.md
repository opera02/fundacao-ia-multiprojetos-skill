# Correção 1.7.10.1: o aceite de risco do canário

Escrita em 02/11/2026, a pedido do titular, para que a ficha de aberturas de um projeto possa valer com o canário
reprovado (`false` ou `null`), sob um aceite de risco assinado por ele (DECISAO-007 da fundação dele). A skill vai para
1.7.10.1; o kit continua 1.7.10: o banco, o kit da raiz, os hooks e o perfil do Windows não mudam. Mudam só o preparo do
host no Ubuntu (`assets/host/preparo_host.py` e `assets/host/wsl/preparar-wsl.sh`), a ferramenta fixa do titular
(`assets/host/fundacao_titular.py`) e os textos. A atualização da fundação é o C6 com kit igual
([fluxo-c-operar.md](fluxo-c-operar.md)): só as instruções da raiz são regeneradas.

Honestidade (registre sempre): o aceite não confina nada. Com a raiz em `/mnt/e`, o isolamento entre projetos continua
lógico, com o risco de persistência pelo `/mnt/c` ([segurança e isolamento §8.1](seguranca-isolamento.md)). O aceite só
registra, com a assinatura do titular, que ele decidiu abrir a ficha de um projeto mesmo assim.

## O que muda

| Peça | 1.7.10 | 1.7.10.1 |
|---|---|---|
| `preparo_host.py instalar-canario` e `preparar-wsl.sh --canario` | o relatório real com `false` ou `null` é recusado, e o `preparar-wsl.sh` para (código 1) sem preparar os projetos | ele é instalado como revogação: substitui o aprovado da mesma versão do Claude Code, o script mostra `[revogar] canario` e o preparo dos projetos segue, com tudo fechado. Só o que não é relatório real do ensaio (simulação, outro esquema, sem conclusão) é recusado |
| Portão do canário | aprovado ou fechado | também expõe o relatório reprovado do Claude Code fixado e da forma de caminho da raiz (`reprovado`: o SHA-256 do arquivo e a conclusão), o único a que um aceite se prende |
| Ficha com o canário reprovado | nunca vale | vale no projeto que tem o aceite de risco assinado para aquele relatório, dentro da vigência |
| Ferramenta do titular | `assinar-ficha` e `verificar-ficha` | mais `aceitar-risco` |
| `hashes.json` da área do projeto | `canario` | mais `aceite_risco`; com a ficha valendo sob o aceite, o relatório reprovado e o aceite (com o `.sig`) ficam fixados pelo SHA-256 |
| Lançador (`conferir-abertura`) | confere o canário aprovado | também recusa abrir com o aceite vencido ou com outro relatório instalado depois do preparo |

A revogação segue a direção do achado CAN-2 da revisão de segurança da 1.7.10 (ramo `v1710/seg-canario`, do lote B,
ainda sem revisão): o canário mais novo vale, também quando reprova. O ramo faz mais (recalcula a conclusão pelos itens,
CAN-1, e exige as sondas novas): fica para a 1.7.11, e ao juntá-lo a parte da revogação é a mesma.

## O aceite

- **Quem faz:** só o titular, pela ferramenta fixa na cópia protegida (`/usr/local/lib/fundacao-ia/<versão do kit>/`,
  gravada pelo `preparar-wsl.sh`), fora do Claude. A sessão não prepara nem vê o aceite antes: ele é montado só com
  código fixo, a partir do relatório real do ensaio que o titular indica (`--canario`, o mesmo que ele instala).
- **O que guarda** (esquema `fundacao.aceite_risco_canario/1`, fechado): o projeto, a versão (1 + a maior que a caixa
  de entrada, o espelho da área na raiz e, no Ubuntu, a área do titular mostram), a data do aceite, a vigência e,
  do relatório, o SHA-256, o Claude Code (versão e SHA-256), a forma de caminho (`ext4` ou `drvfs:/mnt/<x>`), a
  conclusão (`false` ou `null`) e os ids dos itens que falharam, que não mediram e em que o canário apareceu; mais a
  lista fixa de riscos, a mesma que a tela mostra. Relatório aprovado, simulado ou fora da forma: recusado.
- **Assinatura:** `ssh-keygen -Y sign -n fundacao-abertura`, a chave e a âncora da ficha (a linha da âncora da 1.7.10
  já aceita esse namespace: nenhum UAC novo). O esquema próprio faz a ficha não servir de aceite nem o aceite de ficha
  (testado). A tela mostra o que o relatório mediu e os riscos, e o titular digita o nome do projeto.
- **Onde fica:** a ferramenta grava em `<raiz>/.claude/projetos/<p>/risco/aceite-risco-canario.json` (e o `.sig`),
  a caixa de entrada; o preparo do Ubuntu o confere e o copia para `/etc/fundacao-ia/projetos/<p>/risco/`, de dono
  root, que é o que vale.
- **O que o preparo confere:** a assinatura (a mesma conferência da ficha), a forma canônica, o esquema, o projeto, a
  vigência (até 180 dias desde o aceite; a ferramenta propõe 90) e o vínculo com o relatório instalado (SHA-256, Claude
  Code fixado e forma da raiz) e a versão, que tem de passar da maior já instalada (a área guarda
  `risco/maior-versao`: um aceite antigo, ou mais longo, devolvido à caixa de entrada não volta). Qualquer diferença:
  não instala, diz o motivo no relatório do preparo, e vale o aceite que já estava na área (ou nada).
- **Onde está o relatório:** a ferramenta recusa o relatório guardado dentro da raiz ou, no Ubuntu, num disco do
  Windows (`/mnt/...`), onde as sessões gravam; vale o que o ensaio gravou na casa do Ubuntu.
- **O que ele abre:** nada sozinho. Com ele, vale a ficha assinada do projeto, como ela está; sem ficha, nada abre.
- **Fecha sozinho:** vencido (o lançador para e pede um aceite novo e o preparo); outro relatório instalado; outro
  Claude Code fixado; outra forma de caminho da raiz. Os outros projetos continuam fechados.

## Ordem numa fundação em uso

1. **Executor:** a liberação da 1.7.10.1 (publicada, instalada no perfil e aplicada na fundação, com kit igual).
2. **Titular, no Ubuntu:** o `preparar-wsl.sh` do projeto com `--canario <relatório reprovado>` (o passo 5 do canário
   do `assets/templates/CHECKLIST-PROJETO.md`). Ele mostra `[revogar] canario`, prepara o projeto com tudo fechado e
   atualiza, no mesmo lugar, a cópia protegida da ferramenta (a pasta é a da versão do kit, 1.7.10). Os outros
   projetos não precisam de nada: o kit e os hooks não mudaram, e nenhum deles tinha relatório fixado.
3. **Sessão do projeto:** prepara a ficha (`python -m fundacao abertura preparar`); **titular:** assina a ficha
   (`assinar-ficha`), como na 1.7.10.
4. **Titular:** assina o aceite (`aceitar-risco`, comando no checklist, "Passo do titular: o aceite de risco").
5. **Titular, no Ubuntu:** o `preparar-wsl.sh` do projeto de novo. O relatório do preparo mostra "canário NÃO aprovado:
   a ficha vale só neste projeto, sob o aceite de risco". A sessão nova do projeto já abre com o perfil novo.

## Retorno

- **Fechar antes da vigência:** uma ficha nova sem as aberturas, assinada, e o preparo (DECISAO-006, §6; o piso da
  ficha impede a volta da anterior). Outra forma: com `sudo`, apagar só os dois arquivos do aceite na área do projeto
  (`aceite-risco-canario.json` e o `.sig`), deixando o `maior-versao`, e rodar o preparo; uma cópia antiga devolvida à
  caixa de entrada não volta. Não apague a pasta `risco/` inteira da área: sem o `maior-versao`, uma cópia antiga
  guardada por uma sessão voltaria (revisão de segurança da 1.7.10.1, R17101-ACE-1).
- **Voltar para a skill 1.7.10:** o preparo dela não conhece o aceite e recusa o relatório reprovado instalado: tudo
  fecha. A cópia protegida da ferramenta volta à da 1.7.10 no primeiro preparo dela. Nada no banco muda.

## Limites (registre sempre)

- O aceite não confina nada (início deste texto). Ele tampouco revê sozinho a DECISAO-003 e a DECISAO-005 de um
  projeto: isso é decisão do titular, registrada antes da primeira ficha com rede (DECISAO-006).
- O relatório é o arquivo do titular: o preparo confere a forma e a conclusão, não refaz a conclusão pelos itens
  (CAN-1, lote B, 1.7.11).
- O lançador confere o aceite pelos hashes fixados e pela vigência; a assinatura é conferida no preparo.
- Na forma do Windows, a ferramenta não lê a área do Ubuntu: a versão nova vem da caixa de entrada e do espelho. Se a
  área tiver uma versão maior, o preparo avisa e não instala: assine pela forma do Ubuntu.
- O canário de 02/11/2026 não mediu o confinamento: as sondas foram recusadas antes de rodar, e o item que falhou é o
  dos plugins embutidos do Claude Code 2.1.302 ([fontes verificadas](fontes-verificadas.md), conferência da
  1.7.10.1). O canário que mede de fato fica para a 1.7.11.
