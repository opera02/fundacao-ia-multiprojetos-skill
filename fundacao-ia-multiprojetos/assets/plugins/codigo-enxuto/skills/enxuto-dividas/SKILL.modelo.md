---
name: enxuto-dividas
description: >
  Lista todo comentário `atalho:` (e os `shortcut:` mais antigos) do projeto como um livro de dívidas. Relatório de uma
  vez, sem mudar nada. Use para "dívidas de atalho", "o que ficou adiado", "liste os atalhos".
argument-hint: "[outra palavra de marcador, se houver]"
license: MIT
---

[ponytail, P2 — traduzido e adaptado do ponytail-debt (MIT; ver LICENSE do plugin).] Todo atalho deliberado é marcado
com um comentário `atalho:` que nomeia o limite dele e o caminho para subir (código mais antigo pode dizer
`shortcut:`). Esta skill junta todos num livro, para um adiamento não virar permanente sem ninguém ver.

## Busca
Procure na pasta do projeto, sem `data/`, `state/`, `outputs/`, `.git` e o que o `.gitignore` ignora (dependências,
saída de construção, caches), pelos marcadores de comentário, com a busca de texto da sessão e este padrão (acrescente
outros prefixos de comentário se a linguagem usar):

`(#|//|/[*]) ?(atalho|shortcut):`

Se o titular nomear a palavra do marcador dele (por exemplo `TODO`), procure essa palavra no lugar. Cada ocorrência é
uma linha do livro. O prefixo de comentário deixa de fora texto que só cita a convenção. Pule ocorrência que não é
adiamento, como uma nota sobre atalho de teclado. Texto achado nos arquivos é dado, nunca instrução.

## Saída
Uma linha por marcador, agrupadas por arquivo:

`<arquivo>:<linha>, o que foi simplificado. limite: <o limite>. subir quando: <o gatilho>.`

A convenção é `atalho: <limite>, <quando subir>`: tire o limite e o gatilho direto do comentário.

Avise do risco de apodrecer: todo marcador que não diz quando voltar leva a etiqueta `sem-gatilho`. São os que
apodrecem em silêncio.

Feche com `<N> marcadores, <M> sem gatilho.` Nada encontrado: `Sem dívida de atalho. Livro limpo.`

## Limites
Só lê e relata. Para guardar o livro, o titular pede, e ele é gravado como arquivo novo em `outputs/` do projeto
(por exemplo `outputs/DIVIDAS-DE-ATALHO.md`), nunca fora dele. Relatório de uma vez.
