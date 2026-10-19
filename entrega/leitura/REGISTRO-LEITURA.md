# Registro de leitura das fontes

Data: 18/10/2026 · Ambiente: Windows 11, Python 3.12.10, Claude Code 2.1.302.

## Fontes lidas

| Fonte | Arquivo | Tamanho | SHA-256 |
|---|---|---|---|
| Livro *Fundação de IA Multiprojetos — Edição 2.0* (18/10/2026), 219 páginas, 41 aulas, 10 módulos, Apêndices A–F e Referências verificadas | `Fundacao_IA_Multiprojetos_Livro_2.0.pdf` | 858.964 bytes | `2704054bd6ef1977543020ca0f92f544cf470ae9ad06633867c655dd93a4f99b` |
| *Fundação de IA Multiprojetos 2.0 → 3.0: o que corrigir, o que acrescentar e como reorganizar* (482 linhas) | `Fundação de IA Multiprojetos 2.0 para 3.0_ correções, acréscimos e reorganização.md` | 54.787 bytes | `45396627b0a3aa2ee180139760b9d76a9f5dd2e99be5b8baf92b57c103a66009` |

A leitura cobriu as páginas 1–219 do livro (aulas, apêndices e referências) e o
documento 3.0 inteiro. As sínteses por módulo estão em
`fundacao-ia-multiprojetos/references/livro/` (m01–m10, apêndices, glossário,
padrões, cheatsheet), e as correções 3.0 em `references/livro/correcoes-3.0.md`.

## Métodos de extração usados

1. **book-to-skill, modo texto** (`extract.py --mode text`, pdftotext): extração
   completa das duas fontes (219 páginas; 84.585 palavras; ~112 mil tokens).
   Funcionou. Não havia sumário detectável por metadados, então o mapeamento de
   aulas veio da varredura de títulos e do sumário impresso (p5–7).
2. **pdftotext paginado e com layout** (`-layout`): usado para localizar trechos
   por página e conferir tabelas.
3. **PyMuPDF**: renderização de páginas para conferência visual e extração de
   palavras com coordenadas (tabela do Apêndice B).

## Falhas e efeitos colaterais

| Ocorrência | Consequência | Tratamento |
|---|---|---|
| book-to-skill, **modo técnico** (Docling): `std::bad_alloc` nas páginas 79–92 e término com código 139 | extração estruturada não concluída | refeita em modo texto (item 1); log preservado como `b2s_extract_technical_FAILED.log` |
| A tentativa com Docling **baixou automaticamente** os modelos de layout do Hugging Face Hub para `~/.cache/huggingface/hub` (`models--docling-project--docling-layout-heron`, 164 MB, e `models--docling-project--docling-models`, 342 MB), às 17:29–17:30 | ~506 MB em cache no perfil do usuário | mantidos (não apago dados sem pedido). Para remover: apague essas duas pastas |
| Leitura de PDF pela ferramenta do host indisponível (`pdftoppm` ausente) | sem imagens das páginas pela ferramenta | páginas renderizadas com PyMuPDF |

## Trechos comprometidos na extração e como foram resolvidos

| Páginas | Problema | Resolução | Situação |
|---|---|---|---|
| 187–193 (Apêndice B, matriz R01–R51) | Na extração de texto (simples e com layout) as células se fragmentam e a coluna **Aulas** se desloca (ex.: p189, R12–R15 aparecem com as aulas empilhadas fora da linha) | Coluna Aulas reextraída por coordenadas de palavras (PyMuPDF) para os 51 requisitos e comparada com a matriz; p189 conferida visualmente | **0 divergências** (as anotações "3.0: …" da matriz são acréscimos intencionais) |
| 20, 45, 86, 91, 104, 175 (diagramas de arquitetura, estados da tarefa, ciclo GOLD, fluxo RAG, fluxo CAG, ciclo de restauração) | Rótulos saem no texto, mas setas e ordem dos fluxos só existem no desenho | Páginas renderizadas e conferidas | Fluxos refletidos em `references/capacidades/01`, `05`, `06`, `07`, `11` e no núcleo do kit |
| 5–7 (sumário) | Linhas pontilhadas fragmentadas | Sem perda de conteúdo | — |
| 10, 82, 87, 98, 152, 169, 194, 196 | Quadros e listas com moldura | Renderizadas na leitura inicial para conferência visual | Texto íntegro |

Não há imagens rasterizadas no PDF (todo o conteúdo é texto ou desenho vetorial),
nem caracteres de substituição ou glifos de uso privado no texto extraído; o
marcador de uma "página 220" vazia na extração paginada é artefato do separador.

## Como o conteúdo foi tratado

- **Livro** → rótulo `[Livro pX]`; **3.0** → `[3.0]` (proposta de correção, conferida
  quando muda comando, custo ou termo); **[Verificado 2026-10-18]** → fato conferido
  em documentação oficial (fontes em `references/fontes-verificadas.md`);
  **[Decisão]** → escolha de projeto desta skill.
- Exemplos jurídicos (caso Aurora, honorários), OpenSquad, CaixaSim, nomes de pastas
  e Python+SQLite foram marcados como **didáticos**.
- Fatos jurídicos do documento 3.0 não conferidos nesta execução ficaram rotulados
  "[3.0 — não verificado nesta skill]" em `references/privacidade-sigilo.md`.
