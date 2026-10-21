# 05 — GOLD: preparação, curadoria, aprovação, vigência, proveniência e retirada

Requisitos: R29, R30, R31 (e R20). Aulas: A15 [Livro p84–88], A18 [Livro p98–101];
3.0 §3.6. Trilha: essencial.

## Definição adotada
GOLD é a camada de dados limpos, refinados, validados e prontos para consumo pelas
IAs **conforme os critérios do usuário** — não é produto, tipo de banco nem padrão
científico [Livro p84]. [3.0 R6.1] "Registro com proveniência verificada, rubrica e
aprovação humana vinculada ao hash, com finalidade e vigência" (distinto da
arquitetura medalhão, embora relacionado).

## Estados de trabalho [Livro p84]
**origem** (material recebido, imutável) → **preparação** (texto por página/seção,
campos) → **curadoria** (qualidade e autorização de uso) → **GOLD vigente** → correção
ou retirada (propagar aos derivados). Pastas `sources/`, `prepared/`, `gold/` ajudam,
mas a separação real está no estado registrado e no controle de publicação.

## Ficha de admissão [Livro p85; 3.0 R6.2]
Identidade, projeto/caso, fonte e versão, hash do original, localizador (página/seção),
transformação, hash do derivado, texto publicado, critérios aplicados (versão da
rubrica), estado, revisor **autenticado**, data de aprovação, próxima revisão,
finalidade, vigência; jurídico: URL de fonte oficial e situação normativa [3.0 R6.5].
Modelo: `assets/templates/FONTE-PROVENIENCIA.json`. Proveniência PROV:
`wasDerivedFrom`, `wasRevisionOf`, `wasInvalidatedBy`, `wasQuotedFrom` [3.0 R6.4].

## Rubrica de cinco perguntas [Livro p85]
Origem identificável? Extração preservou o significado? Conteúdo vigente? Alcance de
acesso correto? Finalidade de uso clara? — cada uma com aprovado · reprovado ·
pendente **e** a evidência ("conferimos o dia da semana, a negação e o identificador
contra a página 2", não "não encontramos erro"). Atenção especial a números, unidades,
datas, exceções e "não". Citação literal e síntese autoral coexistem, identificadas.

## Implementação
1. Registre originais com ID, versão, hash e responsável; nunca altere o original.
2. Prepare preservando páginas; derivados têm hash próprio.
3. Curadoria por papel autorizado; quem preparou não aprova o próprio texto; a
   aprovação refere-se ao **hash do conteúdo publicado** [Livro p85]. [Decisão; auditoria
   externa da 1.3.4] A conferência do hash é feita DENTRO da transação que grava a decisão,
   e a gravação só vale se o hash preparado continuar o revisado: preparação nova no intervalo
   devolve conflito (refaça a revisão), nunca "aprovado" para outro texto. A busca e a
   verificação de citação recusam versão cujo hash aprovado difere do preparado.
4. Divergência entre versões: só a **declaração explícita de substituição** resolve
   (data de arquivo mais recente não basta) [Livro p85]. Duas fontes vigentes sem
   precedência: registre o conflito; aprove no máximo uma nota que descreva o
   conflito, nunca escolha a frase preferida [Livro p88].
5. Candidatos pendentes ficam fora do consumo normal; retirada impede entrega a novos
   consumidores e propaga aos derivados (ver `references/capacidades/06-rag.md` e `references/capacidades/07-cag-caches.md`).
6. Revisão periódica por risco de mudança e consequência do erro (a data do livro é
   fictícia, não prazo legal) [Livro p85].

## Verificação
| Caso | Esperado |
|---|---|
| Extração com "após" no lugar de "antes" | reprovada (fidelidade), não publicada; correção cria nova transformação; origem intacta [Livro p86] |
| GUIA-003@1 (sexta) × @2 (quinta, com substituição declarada) | @2 vigente; @1 superada com trilha [Livro p85] |
| Candidato pendente | ausente do consumo |
| Retirada de item aprovado | some das consultas; derivados bloqueados, inclusive após restauração de backup |
| Preparação nova entre a leitura e a aprovação do curador | conflito; nada aprovado; o texto novo não é entregue |
| Reprovação de fonte antes aprovada, com resposta em cache | busca vazia e cache inválido nas duas portas |
| Reconstrução da admissão | ficha permite achar fonte, trecho conferido e conteúdo rejeitado [Livro p88] |

## Critério de aceite
Uma aprovação, uma reprovação e uma retirada demonstradas, com ficha completa e
revisor autenticado [Livro p87].

## Com o kit
`fundacao/core/knowledge.py` (`register_source`, `prepare`, `curate` com `RUBRIC`,
`withdraw`, `cleanup`). Dados didáticos (GUIA-001/002/003): `references/livro/m05-gold-rag.md`.
Testes: `tests/test_conhecimento.py`, `tests/test_auditoria_1_5_0_dados.py` (#12, #18).

> **No kit:** identificadores de fonte são qualificados pelo projeto (`juridico-lab/GUIA-001`; citação `juridico-lab/GUIA-001@1, p. 2`). Os nomes curtos do livro (`GUIA-001@1`) continuam valendo como exemplo didático [Decisão: evita colisão e sondagem entre projetos]. Um identificador de fonte pertence a um só escopo (projeto e caso), e a versão é inteiro a partir de 1 [varredura da 1.4.5, #12, #18].
