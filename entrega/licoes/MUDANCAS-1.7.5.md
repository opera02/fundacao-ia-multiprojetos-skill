# Mudanças da 1.7.5 — efeito e veredito

Versão: 1.7.5 · Anterior: 1.7.4 (só empacotada) · Registro: carga inicial de 2026-10-21.
A 1.7.5 é a 1.7.4 com um arquivo em LF; a nota da versão está em `entrega/README-ENTREGA.md`.
Commits citados são da árvore de desenvolvimento (a cópia pública tem outro histórico).

## Mudanças

| # | Componente | O que mudou | Motivo observado (onde) | Efeito observado (onde) | Veredito |
|---|---|---|---|---|---|
| M1 | `fundacao-ia-multiprojetos/scripts/tests/test_regra_retomada_desatualizada.py` | o fim de linha passou de CRLF para LF; o conteúdo não mudou (commit `83767d2`) | a montagem da transferência da 1.7.4 parou: o texto para revisão relê o arquivo em modo texto e não o reproduzia (nota da 1.7.5) | a transferência da 1.7.5 foi montada (`entrega/transferencia/fundacao-ia-multiprojetos-1.7.5-para-revisao.md`) | ajudou |

## Lições

### L1 — Texto gravado por ferramenta vai em LF
- Gatilho: arquivo de texto gravado por script, ferramenta ou cópia no Windows, ou tirado de um clone com a
  configuração padrão do Git no Windows.
- Lição: grave texto em LF (no Python, `newline="\n"`) e deixe o repositório fixar o fim de linha (`.gitattributes`
  com `* text=auto eol=lf`); conferência por hash ou por releitura em modo texto quebra com CRLF. Na 1.7.6 a mesma
  classe voltou: num clone no Windows os `.sh` saíram em CRLF e dois testes do preparo do WSL falharam.
- Evidência: M1; `.gitattributes`; `entrega/README-ENTREGA.md` (notas da 1.7.5 e da 1.7.7); commits `83767d2` e
  `4d641a0`
- Confiança: alta
