#!/usr/bin/env python3
"""Regras de código enxuto: um texto fixo no começo da sessão e de cada subagente, só com o campo ligado.

[Decisão; ponytail, P3 — regra e texto traduzidos e adaptados do ponytail (MIT; AVISOS-DE-TERCEIROS.md); o código é
próprio, em Python, no molde do `sinais_sessao.py`.] O ponytail injeta a regra com um hook em JavaScript que grava
estado no perfil do usuário; aqui só vale o texto fixo, igual ao §1 de `references/codigo-enxuto.md` (um teste prende
os dois), sem nível ajustável, sem estado e sem oferta de editar o perfil.

Eventos: SessionStart (source startup, resume, clear ou compact; fork é válido e não emite) e SubagentStart, que
recebe o mesmo texto porque o subagente começa sem a conversa. Só emite com `FUNDACAO_REGRAS_CODIGO=enxuto` no
ambiente (o lançador o põe a partir do campo `regras_codigo` do `projeto.json`) e `FUNDACAO_PROJECT` válido como
identificador. Sem o campo, ou vazio: não lê a entrada e não escreve nada, código 0. Valor fora da lista, projeto
inválido ou entrada inválida: código 2, stdout vazio e motivo fixo sem ecoar a entrada.
Entrada: um único objeto JSON UTF-8 de até 64 KiB e 32 níveis, encerrado por EOF em até 1 s. Duplicatas e NaN
recusam. Não abre arquivos, rede ou processos; não escreve estado; não lê identidade, transcript, RETOMADA nem
caso. O texto não vem do projeto: nada de data/ ou de conteúdo do projeto entra nele.
O preparo do titular copia e registra este código: a presença no pacote significa preparado, não ativado no host.
A forma da saída é a do `sinais_sessao.py` (fonte dele, conferida em 2026-10-22: https://code.claude.com/docs/en/hooks).
"""
from __future__ import annotations

import json
import os
import re
import sys
import threading

LIMITE_BYTES = 64 * 1024
PRAZO_SEGUNDOS = 1.0
IDENTIFICADOR = re.compile(r"[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?")
VALORES = frozenset({"enxuto"})
COM_TEXTO = {"startup", "resume", "clear", "compact"}
FONTES = COM_TEXTO | {"fork"}
EVENTOS = {"SessionStart", "SubagentStart"}
ERRO = "regras_codigo: entrada, campo ou projeto invalido\n"

# O mesmo texto do §1 de references/codigo-enxuto.md: mude os dois juntos (test_regras_codigo.py confere).
TEXTO = """Código enxuto (regra deste projeto): você é um desenvolvedor sênior preguiçoso. O melhor código é o que nunca se escreve. Resolva o problema inteiro com o mínimo de código novo. Termine a resposta com uma ou duas linhas: o que ficou sem fazer ou sem conferir, e o risco que o titular precisa saber.

Antes de escrever: leia a tarefa e o código que ela toca. Liste cada lugar que a mudança alcança: chamadores, testes, dados de teste, configuração, exportações. Confira o que a mudança pode quebrar para quem usa: dados que destruiria ou exporia, chamadores que deixariam de funcionar. Isso é escopo. Funcionalidade extra não é.

A menor mudança completa: fique com a primeira opção que resolve de verdade.
1. Precisa existir? Não faça recurso, opção ou flexibilidade que ninguém pediu, e diga em uma linha o que deixou de fora. Pedido vago ("faça X") recebe a menor versão que cumpre o essencial.
2. Já existe neste código (função, componente, serviço, padrão)? Use do jeito do código ao redor.
3. Biblioteca padrão ou recurso da plataforma? Use, a menos que o projeto tenha o seu próprio.
4. Dependência já instalada? Use. Nunca acrescente dependência para poucas linhas.
5. Cabe em uma linha que se entende de relance? Uma linha.
6. Senão: o mínimo de código que funciona.

Acabamento:
- Seja preguiçoso na solução, nunca na mudança: termine tudo o que a tarefa exige, inclusive os chamadores, testes e dados de teste que a sua mudança quebra.
- Nada de abstração, camada, conversão de tipo, opção, configuração, texto padrão ou código "para depois" que ninguém pediu. Mantenha os valores na forma que a plataforma já entrega. Apagar vale mais que acrescentar. Mantenha a estrutura que o código já tem: camadas, interfaces e convenções.
- O diff mais curto que funciona vence, depois de saber tudo o que ele precisa tocar. Uma linha que precisa ser decifrada não é curta.
- Comente só o porquê que o código não mostra, em uma linha.
- Correção de erro: antes de editar, procure todos os chamadores da função que vai tocar e corrija a causa uma vez, no código comum.
- Código que você move ou junta mantém o tratamento de erro e a validação.
- Entre opções do mesmo tamanho, fique com a que acerta os casos de borda.
- Código sem a sua conferência está inacabado: lógica nova não trivial (um desvio, um laço, um leitor de formato, dinheiro ou segurança, ou um script ou aplicativo novo inteiro) deixa um teste pequeno ou uma autoconferência com assert. Mudança trivial não precisa.
- Atalho com limite conhecido leva um comentário no código neste formato: atalho: <o limite>, <quando subir>.

Nunca corte: validação na fronteira de confiança, tratamento de erro que evita perda de dados, segurança, acessibilidade, a calibração que o equipamento real exige e o que foi pedido.

Três linhas desta fundação, que valem sobre as regras acima:
1. Teste que a sua mudança quebrou se conserta no código. Apagar, pular ou afrouxar teste, ampliar exceção ou prazo é mudança de critério: não faça; proponha ao titular, com o motivo.
2. O que as regras da fundação e do projeto exigem (por exemplo RETOMADA, evidências, avisos de terceiros, FINALIDADE e ARVORE-SKILL.md na árvore da skill, teto do texto sempre carregado) conta como pedido, não como extra.
3. Rótulo de origem e de decisão no comentário é o porquê e fica; o marcador de atalho é atalho:, não outro."""


def _recusar(*_):
    raise ValueError("entrada invalida")


def _objeto_sem_duplicatas(pares):
    objeto = {}
    for chave, valor in pares:
        if chave in objeto:
            _recusar()
        objeto[chave] = valor
    return objeto


def _entrada():
    # Leitura em daemon: também há prazo quando o produtor segura a pipe aberta sem mandar EOF. O main encerra sem
    # esperar a thread. os.read não segura o lock do BufferedReader; cada chamada é limitada e a memória total fica
    # em 64 KiB + 1.
    resultado = []

    def ler():
        try:
            partes, total = [], 0
            while total <= LIMITE_BYTES:
                parte = os.read(sys.stdin.fileno(), min(4096, LIMITE_BYTES + 1 - total))
                if not parte:
                    break
                partes.append(parte)
                total += len(parte)
            resultado.append(b"".join(partes))
        except (OSError, ValueError):
            resultado.append(None)

    leitor = threading.Thread(target=ler, daemon=True)
    leitor.start()
    leitor.join(PRAZO_SEGUNDOS)
    if leitor.is_alive() or not resultado or resultado[0] is None or len(resultado[0]) > LIMITE_BYTES:
        _recusar()
    objeto = json.loads(resultado[0].decode("utf-8"), object_pairs_hook=_objeto_sem_duplicatas,
                        parse_constant=_recusar)
    if not isinstance(objeto, dict):
        _recusar()
    pendentes = [(objeto, 1)]
    while pendentes:
        valor, nivel = pendentes.pop()
        if nivel > 32:
            _recusar()
        if isinstance(valor, dict):
            pendentes.extend((v, nivel + 1) for v in valor.values())
        elif isinstance(valor, list):
            pendentes.extend((v, nivel + 1) for v in valor)
    return objeto


def main(argv=None) -> int:
    sys.stdout.reconfigure(encoding="utf-8", newline="\n")
    sys.stderr.reconfigure(encoding="utf-8", newline="\n")
    argv = sys.argv[1:] if argv is None else argv
    try:
        if argv:
            _recusar()
        campo = os.environ.get("FUNDACAO_REGRAS_CODIGO", "")
        if campo == "":
            return 0  # desligado: nem lê a entrada
        if campo not in VALORES:
            _recusar()
        projeto = os.environ.get("FUNDACAO_PROJECT", "")
        if not IDENTIFICADOR.fullmatch(projeto) or ".." in projeto:
            _recusar()
        evento = _entrada()
        nome = evento.get("hook_event_name")
        if nome not in EVENTOS or (nome == "SessionStart" and evento.get("source") not in FONTES):
            _recusar()
        if nome == "SubagentStart" or evento["source"] in COM_TEXTO:
            print(json.dumps({"hookSpecificOutput": {"hookEventName": nome, "additionalContext": TEXTO}},
                             ensure_ascii=False))
        return 0
    except (ValueError, TypeError, RecursionError, OSError):
        sys.stderr.write(ERRO)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
