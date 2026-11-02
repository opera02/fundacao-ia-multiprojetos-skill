#!/usr/bin/env python3
"""Confere preenchimento de revisão por JSONstdin; não lê caminhos nem aprova mérito.

Entrada: {"relatorio": "Markdown literal", "recibo_texto": "JSON literal opcional"}.
Saída JSON/código0: só os campos conferidos estão coerentes com os dados recebidos.
Não comprova veracidade, operação, acesso, autenticidade ou segurança de uma revisão.

Cada achado precisa de local (com linha, registro ou "metadado"), evidência, cenário, impacto e exatamente uma
confiança, na mesma linha do campo e sem o texto do modelo. Afirmação de alcance ("nenhum", "nada", "só",
"todos", "qualquer", "não há", "é seguro") precisa declarar a cobertura ("não localizado nas fontes X", "busca
sem corte", "condicional", "não medido", "não conferido"). Onde: valor dos campos e texto dos achados, coluna de
afirmação do quadro e item de lista do quadro (com as linhas que o continuam), título e texto antes da primeira seção
(fora de citação) e seções fora do modelo. Não são
conferidas as regras de escrita, Escopo, Cobertura e Comandos executados (lá "só" e "nenhum" descrevem o
próprio método) e a conferência (o título de cada seção, sim). Nas pendências, a conferência é outra: só "só",
"somente", "apenas" e "único" são recusados, mesmo com cobertura e com "li apenas" (pendência diz o que não foi
verificado, não o que foi), salvo nos campos de endurecimento sugerido e de hipótese, com as linhas que os
continuam. A conferência aceita as grafias com e sem acento, salvo "so" e "e" sem acento ("SO", sistema operacional, e
a conjunção não são "só" e "é"); fora das pendências, isenta a restrição de leitura ("li apenas X"), sem isentar o
resto da frase, e, nos títulos, a descrição de escopo ("de toda a fundação").
Seção de avaliação positiva ("o que está bem") é recusada. Hash abreviado com reticências ("a1b2c3…" ou
"a1b2c3…d4e5", fora de bloco de código) tem de conferir com um hash inteiro do próprio relatório: o começo e,
se houver, o fim; intervalo do git (`git ... A...B` na mesma linha e na mesma célula de tabela, os dois lados com
7 ou mais dígitos) não é abreviação.
Até 50 erros por resposta [Decisão; calibração da 1.7.9 em 25/10/2026: as falhas de precisão vieram dessas
formas]. É filtro de forma: lista de palavras, não decide se a cobertura declarada é real.
Desde a 1.7.10 (F4 da revisão de segurança da 1.7.9), a lista para de crescer em MAX_ERROS + 1 mensagens, em todas as
conferências, e o resto só é contado ("mais N erros"); antes, a regra de alcance acumulava um erro por linha sem teto.
Também desde a 1.7.10 (limites registrados no R179-26 e no R179-28): no quadro, o item de lista é conferido, com as
linhas que o continuam (antes, só a coluna da tabela: a afirmação do quadro em lista escapava); o subitem de lista
recuado com 4 ou mais espaços passa pelas regras de alcance e de hash, e sai só o bloco de código recuado, o que vem
depois de linha vazia e fora de lista (nos campos dos achados e do recibo, a linha recuada continua fora: subitem não é
o campo); e as bordas do hash abreviado recusam só dígito hexadecimal antes e depois ("xa1b2c3…" e "a1b2c3…fim" passam
a ser conferidos). Na revisão do pacote (1.7.10): nos achados, a linha recuada que continua o campo Correção (com
recuo: um ou mais espaços, ou tab) fica fora com ele, salvo quando é ela mesma outro campo ou título de achado; e o fim
do hash abreviado é a sequência hexadecimal colada às reticências, salvo a só de letras a-f que continua numa palavra
("a1b2c3…fim", "a1b2c3…do", "a1b2c3…fé": confere-se só o começo). Limite: a palavra colada só de letras a-f e
terminada ali ("a1b2c3…de", "…cada") entra como fim.
"""
from __future__ import annotations

import argparse
import hashlib
import json
import math
import re
import sys
import unicodedata

MAX_ENTRADA = 2 * 1024 * 1024
ALCANCE = ('somente preenchimento e coerência dos literais recebidos; não verifica mérito, '
           'veracidade, comandos, acesso, autenticidade, assinatura ou aprovação da revisão')
# Texto já normalizado por _normal (minúsculo, sem acento).
CAMPOS = (('local', r'local'), ('evidência', r'evidencias?'), ('cenário', r'cenario'),
          ('impacto', r'(?:alcance e )?impacto'))
# Regra de alcance: texto minúsculo (NFC) que aceita as duas grafias, com e sem acento, salvo "so" e "e" sem
# acento, que também são "SO" (sistema operacional) e a conjunção: só "só" e "é" contam.
QUANTIFICADOR = re.compile(r'\b(?:nenhum|nenhuma|nada|ningu[eé]m|todos|todas|todo|toda|qualquer|sempre|nunca|jamais'
                           r'|só|somente|apenas|[uú]nicos?|[uú]nicas?)\b|\bn[aã]o (?:h[aá]|existe)\b'
                           r'|(?<!não )(?<!nao )\b(?:est[aá]|é) (?:segura|seguro)\b')
COBERTURA = re.compile(r'n[aã]o localizad|nas fontes|no conjunto|sem corte|busca completa|n[aã]o medid'
                       r'|n[aã]o verificad|n[aã]o conferid|\bcondiciona|\bnos \d+ |\bnas \d+ |nas linhas exibidas'
                       r'|no trecho')
# Retirados da frase antes da regra; a restrição de leitura isenta só a si mesma, não o resto da frase. Nas
# pendências, só as frases fixas (a restrição de leitura ali descreve o que foi feito).
ISENTOS_FIXOS = (r'somente leitura|s[oó] leitura|nenhum achado comprovado|nenhuma corre[cç][aã]o foi aplicada'
                 r'|n[aã]o estabelece que a (?:vers[aã]o|funda[cç][aã]o) [eé] segura'
                 r'|s[oó] podem mudar arquivos que n[aã]o s[aã]o c[oó]digo')
ISENTOS = re.compile(ISENTOS_FIXOS
                     + r'|\b(?:li|lid[oa]s?|listei|listad[oa]s?)[ \t]+(?:apenas|somente|só)\b'
                     r'|\b(?:apenas|somente|só)[ \t]+(?:li|lid[oa]s?|listei|listad[oa]s?)\b')
ISENTOS_PENDENCIAS = re.compile(ISENTOS_FIXOS)
# No título, "toda a fundação" ou "todo o repositório" descrevem o escopo; "está segura" continua conferido.
ESCOPO_NO_TITULO = re.compile(r'\btod[oa] (?:[ao] )?(?:funda[cç][aã]o|reposit[oó]rio|[aá]rvore|kit|skill)\b')
POSITIVA = re.compile(r'o que esta bem|pontos (?:fortes|positivos)|aspectos positivos'
                      r'|sem achados? comprovados? (?:nestas|nas|em outras) areas')
# Seções do modelo (título sem acento, por prefixo) e como a regra de alcance as confere; outra seção, linha a linha.
SECOES = (('regras de escrita', None), ('escopo', None), ('cobertura', None), ('comandos executados', None),
          ('quadro de afirmacoes', 'quadro'), ('achados', 'achados'), ('conferencia', None),
          ('pendencias', 'pendencias'))
# Nas pendências, quantificador restritivo descreve o que foi feito ("só X foi lido"): recusado mesmo com cobertura.
RESTRITIVO = re.compile(r'\b(?:só|somente|apenas|[uú]nicos?|[uú]nicas?)\b')
MODELO = re.compile(r'arquivo:linha e revisao|ids do quadro de afirmacoes, comando e trecho|demonstrados \| condicionais'
                    r'|arquivo:linha \(para modo de arquivo|do comando, trecho literal redigido e ids do quadro')
LOCAL_OK = re.compile(r'[^\s:]:\d|\blinhas? \d|\bregistros? \S|\beventos? \d|\bmetadado')
# Hash inteiro (32 ou mais dígitos hexadecimais) e hash abreviado com reticências: o começo tem ao menos 6 dígitos,
# com letra e algarismo (palavra só de letras a-f e data só de algarismos não são hash). Texto em minúsculas. As bordas
# recusam só dígito hexadecimal antes e depois, como no hash inteiro (1.7.10; R179-28, limite): antes recusavam também
# letra, e a abreviação colada a uma palavra ("xa1b2c3…", "a1b2c3…fim") escapava da conferência. O fim (opcional) é a
# sequência hexadecimal colada às reticências, inteira; a só de letras a-f que continua numa palavra ("…fim", "…do") é a
# palavra, não o fim: confere-se só o começo (revisão do AJUSTES-179, 1.7.10: antes, o "f" de "fim" virava o fim, e a
# abreviação certa, com o hash inteiro no relatório, não conferia). A sequência com algarismo continua fim mesmo colada
# a uma letra ("…d4e5x": confere "d4e5"), para não deixar de conferir um fim que tem cara de hash.
HEX_INTEIRO = re.compile(r'(?<![0-9a-f])[0-9a-f]{32,}(?![0-9a-f])')
HEX_ABREVIADO = re.compile(r'(?<![0-9a-f])(?=[0-9]*[a-f])(?=[a-f]*[0-9])([0-9a-f]{6,})(\.{3,}|…)'
                           r'((?=[0-9a-f]*[0-9])[0-9a-f]+|[0-9a-f]+(?!\w))?')  # \w do str: também "…fé", "…café"
# Item de lista (marcador -, * ou +, ou número com . ou ), seguido de espaço ou fim de linha), desde a 1.7.10: no
# quadro, a afirmação escrita em lista (R179-26, limite 1); no _limpo, o que separa o subitem recuado do bloco de código
# (R179-26, limite 2; R179-28, limite 1).
ITEM_DE_LISTA = re.compile(r'[ \t]*(?:[-*+]|\d{1,9}[.)])(?:[ \t]|$)')
# Instrução do modelo completo entre os itens do quadro ("atribua o mecanismo somente com reprodução ou evidência"): não
# é afirmação. Isenta só ali, onde o item de lista do quadro passou a ser conferido (1.7.10).
REGRA_DO_QUADRO = re.compile(r'atribua o mecanismo[ \t]+somente[ \t]+com\b')
# Rótulos dos campos do achado no modelo completo e no enxuto (sem acento, por prefixo). Nos achados, a linha recuada
# continua o campo de cima, salvo quando é ela mesma um desses campos (revisão do AJUSTES-179, 1.7.10): a continuação
# da Correção fica fora com ela, mas um "  - Impacto: ..." recuado debaixo dela continua conferido.
CAMPOS_DO_ACHADO = re.compile(r'(?:severidade|confianca|situacao|alcance|impacto|origem|local|evidencia|quem consegue'
                              r'|cenario|contraevidencia|correcao)')
TITULO_RECUADO = re.compile(r'[ \t]*#{1,6}(?:[ \t]|$)')  # o validar() conta o "###" recuado (^\s*###) como achado
MAX_ERROS = 50


class _Erros(list):
    """Lista de erros que guarda até MAX_ERROS + 1 mensagens e conta o resto em `ocultos` (F4, 1.7.10): relatório
    feito para gerar um erro por linha não faz a lista crescer sem teto."""

    def __init__(self, itens=()):
        super().__init__()
        self.ocultos = 0
        self.extend(itens)

    @property
    def cheia(self) -> bool:
        return len(self) > MAX_ERROS

    def append(self, mensagem) -> None:
        if self.cheia:
            self.ocultos += 1
        else:
            super().append(mensagem)

    def extend(self, mensagens) -> None:
        for mensagem in mensagens:
            self.append(mensagem)

    def __iadd__(self, mensagens):
        self.extend(mensagens)
        return self


def _json(texto: str):
    def pares(itens):
        obj = {}
        for chave, valor in itens:
            if chave in obj:
                raise ValueError('chave JSON duplicada')
            obj[chave] = valor
        return obj

    def constante(_):
        raise ValueError('número não finito')

    def real(valor):
        numero = float(valor)
        if not math.isfinite(numero):
            raise ValueError('número não finito')
        return numero

    return json.loads(texto, object_pairs_hook=pares, parse_constant=constante, parse_float=real)


def _normal(texto: str) -> str:
    return ''.join(c for c in unicodedata.normalize('NFD', texto.casefold())
                   if not unicodedata.combining(c))


def _limpo(texto: str, subitens: bool = False) -> str:
    """Exemplos cercados e comentários não preenchem declarações do relatório.

    Linha recuada com 4 ou mais espaços: nos campos dos achados e do recibo (`subitens` falso), sai sempre, porque
    subitem não é o campo do achado. Para as regras de alcance e de hash (`subitens`, desde a 1.7.10; R179-26, limite
    2, e R179-28, limite 1), sai só o bloco de código recuado: o que começa depois de linha vazia e fora de lista, até
    a primeira linha não vazia com menos recuo. O subitem de lista recuado e a continuação de um parágrafo ou de um
    item ficam e são conferidos; antes, todo recuo de 4 espaços saía, e a afirmação ou o hash abreviado num subitem
    escapavam das duas regras. A lista acaba no título e no parágrafo na margem depois de linha vazia. Linear."""
    texto = re.sub(r'<!--[\s\S]*?(?:-->|$)', '', texto)
    saida, cerca = [], None
    vazia = em_lista = codigo = False  # linha anterior vazia; dentro de lista; dentro de bloco de código recuado
    for linha in texto.splitlines():
        m = re.match(r'^\s*(`{3,}|~{3,})(.*)$', linha)
        if m:
            marca = m[1]
            if cerca is None:
                cerca = marca
            elif marca[0] == cerca[0] and len(marca) >= len(cerca) and not m[2].strip():
                cerca = None
            vazia = codigo = False
            continue
        if cerca is not None:
            continue
        recuada = linha.expandtabs(4).startswith('    ')
        if not linha.strip():
            vazia = True
        else:
            if not recuada:
                codigo = False
                if ITEM_DE_LISTA.match(linha):
                    em_lista = True
                elif not linha[0].isspace() and (vazia or linha.startswith('#')):
                    em_lista = False  # título, ou parágrafo na margem depois de linha vazia: a lista acabou
            elif vazia and not em_lista:
                codigo = True  # bloco de código recuado: depois de linha vazia e fora de lista
            vazia = False
        if recuada and (codigo or not subitens):
            continue
        saida.append(linha.replace('**', '').replace('__', ''))
    return '\n'.join(saida)


def _formal(texto: str) -> str:
    return _normal(_limpo(texto))


def _com_acento(texto: str) -> str:
    """Mesma limpeza, com os subitens recuados (1.7.10), minúsculo e com acento (NFC), para a regra de alcance."""
    return unicodedata.normalize('NFC', _limpo(texto, subitens=True).casefold())


def _titulo(linha: str):
    """Título de seção (`## ...`), ou None. Regex linear: sem preguiçoso antes de espaço final. Com 4 ou mais espaços
    de recuo não é título (1.7.10): o subitem recuado passou a chegar à regra de alcance, e um "## Escopo" recuado
    dentro de uma lista não pode desligá-la nas linhas seguintes."""
    if linha.expandtabs(4).startswith('    '):
        return None
    m = re.match(r'^[ \t]*##[ \t]+(\S.*)$', linha)
    return m[1].strip() if m else None


def _campo(linha: str):
    """(rótulo, valor) de uma linha de lista `- rótulo: valor`, pelo primeiro ':'; None se não é campo. Linear."""
    resto = linha.lstrip(' \t')
    if not resto.startswith('-') or resto[1:2] not in (' ', '\t'):
        return None
    rotulo, sep, valor = resto[1:].partition(':')
    return (rotulo, valor) if sep else None


def _valor(corpo: str, padrao: str) -> str:
    """Texto depois do primeiro ':' na linha `- <campo> ...: valor`; vazio se o campo falta ou está vazio."""
    m = re.search(r'^[ \t]*-[ \t]+' + padrao + r'\b[^:\n]*:(.*)$', corpo, re.MULTILINE)
    return m[1].strip(' \t') if m else ''


def _celulas(linha: str) -> list:
    return [c.strip() for c in linha.strip().strip('|').split('|')]


def _alcance(texto: str, erros: _Erros | None = None) -> _Erros:
    """Afirmação de alcance sem cobertura declarada, onde o relatório põe afirmações; seção fora do modelo, toda.

    Recebe o texto de _com_acento. Antes da primeira seção, confere o título e o texto fora de citação (o aviso
    do modelo é citação). No quadro, a coluna da afirmação, na tabela, e o item de lista com as linhas que o
    continuam (recuadas, ou coladas a ele sem linha vazia); o parágrafo entre as linhas do quadro é texto do modelo.
    Nos achados, o campo Correção é recomendação e fica fora, com as linhas recuadas que o continuam (um ou mais
    espaços, ou tab), salvo a que é ela mesma outro campo do achado (CAMPOS_DO_ACHADO) ou título de achado
    (TITULO_RECUADO); a linha na margem encerra o campo.
    Acrescenta a `erros` (com teto: o resto só é contado, F4).
    """
    erros = _Erros() if erros is None else erros
    modo, rotulo_pendencia, rotulo_achado, no_item, vazia = 'preambulo', '', '', False, False
    for linha in texto.splitlines():
        anterior_vazia, vazia = vazia, not linha.strip()
        titulo = _titulo(linha)
        if titulo is not None:
            rotulo_pendencia, rotulo_achado, no_item = '', '', False
            sem_acento = _normal(titulo)
            if POSITIVA.search(sem_acento):
                erros.append(f'seção de avaliação positiva ("{titulo[:60]}"): retire-a ou leve cada item ao quadro '
                             'de afirmações, com a fonte')
            modo = next((m for prefixo, m in SECOES if sem_acento.startswith(prefixo)), 'linhas')
            alvo = ISENTOS.sub(' ', ESCOPO_NO_TITULO.sub(' ', titulo))  # título de seção também é texto publicado
            achado = QUANTIFICADOR.search(alvo)
            if achado and not COBERTURA.search(alvo):
                erros.append(f'afirmação de alcance ("{achado[0]}") sem cobertura declarada no título "{titulo[:80]}": '
                             'retire-a do título ou declare a cobertura')
            continue
        if modo is None or vazia:
            continue
        tabela = linha.lstrip().startswith('|')
        if tabela and re.match(r'^[ \t]*\|[ \t]*(?:id[ \t]*\||:?-{3})', linha):
            continue  # cabeçalho ou separador do quadro
        campo = _campo(linha)
        if modo == 'preambulo':
            if linha.lstrip().startswith('>'):
                continue  # aviso citado do modelo
            alvo = ESCOPO_NO_TITULO.sub(' ', linha) if linha.lstrip().startswith('#') else linha
        elif modo == 'quadro':
            if tabela:
                celulas = _celulas(linha)
                alvo, no_item = (celulas[1] if len(celulas) > 1 else ''), False  # só a coluna da afirmação
            elif ITEM_DE_LISTA.match(linha) or (no_item and (linha[0].isspace() or not anterior_vazia)):
                # Afirmação do quadro em lista, e a linha que a continua: conferidas desde a 1.7.10 (R179-26, limite
                # 1); antes, só a tabela era, e o quadro escrito em lista escapava da regra.
                alvo, no_item = REGRA_DO_QUADRO.sub(' ', linha), True
            else:
                alvo, no_item = '', False  # parágrafo do modelo entre as linhas do quadro
        elif modo == 'pendencias':
            if not linha.startswith((' ', '\t')):  # linha recuada continua o campo de cima; as outras, não
                rotulo_pendencia = _normal(campo[0]).strip() if campo is not None else ''
            if rotulo_pendencia.startswith(('endurecimento', 'hipotese')):
                continue  # recomendação e hipótese rotulada, com as linhas que as continuam
            achado = RESTRITIVO.search(ISENTOS_PENDENCIAS.sub(' ', linha))
            if achado:
                erros.append(f'pendência descreve o que foi feito ("{achado[0]}") em "{linha.strip()[:80]}": diga o que '
                             'não foi verificado e por quê; o que foi feito está na tabela de comandos')
            continue
        elif modo == 'achados':
            rotulo = _normal(campo[0]).strip() if campo is not None else ''
            if (not linha.startswith((' ', '\t')) or CAMPOS_DO_ACHADO.match(rotulo)
                    or TITULO_RECUADO.match(linha)):
                # a linha na margem, o campo do achado e o título de achado, mesmo recuados, têm o próprio rótulo
                # (reconferência do AJUSTES-179: " ### F2 — ..." logo depois da Correção herdava o rótulo dela)
                rotulo_achado = rotulo
            if rotulo_achado.startswith('correcao'):
                # Recomendação, não afirmação de fato, com as linhas recuadas que a continuam: desde a 1.7.10 a linha
                # com 4 ou mais espaços chega aqui (subitem), e a continuação da Correção virava falso positivo
                # (revisão do AJUSTES-179); a de 2 espaços já virava antes.
                continue
            alvo = campo[1] if campo is not None else linha
        else:
            alvo = linha
        alvo = ISENTOS.sub(' ', alvo)
        achado = QUANTIFICADOR.search(alvo)
        if achado and not COBERTURA.search(alvo):
            erros.append(f'afirmação de alcance ("{achado[0]}") sem cobertura declarada em "{linha.strip()[:80]}": '
                         'cite a busca sem corte sobre o conjunto, ou escreva "não localizado nas fontes ..." '
                         'ou "condicional"')
    return erros


def _hashes_abreviados(texto: str, erros: _Erros | None = None):
    """Hash abreviado, fora de bloco de código, sem hash inteiro do relatório com o mesmo começo e o mesmo fim.

    O subitem de lista recuado não é bloco de código (1.7.10): a abreviação nele é conferida. O hash inteiro vale
    também dentro de bloco de código, não em comentário. Índice pelos 6 primeiros dígitos,
    memória por abreviação e teto de comparações: tempo limitado mesmo com entrada feita para ser lenta. Acrescenta
    a `erros` até MAX_ERROS + 1 mensagens no total e devolve (erros, quantas abreviações sem par ficaram sem
    mensagem), para a contagem final."""
    sem_comentario = re.sub(r'<!--[\s\S]*?(?:-->|$)', '', texto)
    por_inicio = {}
    for h in set(HEX_INTEIRO.findall(sem_comentario.casefold())):
        por_inicio.setdefault(h[:6], []).append(h)
    limpo = _limpo(texto, subitens=True).casefold()
    erros = _Erros() if erros is None else erros
    vistos, orcamento, ocultos = {}, 2_000_000, 0
    for m in HEX_ABREVIADO.finditer(limpo):
        inicio, reticencias, fim = m[1], m[2], m[3] or ''  # sem fim: confere só o começo
        antes = limpo[max(0, m.start() - 400):m.start()]  # janela limitada: tempo linear
        corte = max([antes.rfind('\n')] + [b.start() for b in re.finditer(r'(?<!\\)\|', antes)])
        if (reticencias == '...' and len(inicio) >= 7 and len(fim) >= 7
                and re.search(r'\bgit\b', antes[corte + 1:])):
            continue  # intervalo do git na mesma linha e na mesma célula, como em git diff A...B
        if (inicio, fim) not in vistos:
            candidatos = por_inicio.get(inicio[:6], ())
            orcamento -= len(candidatos) + 1
            if orcamento < 0:
                erros.append('hashes abreviados demais para conferir: cite os hashes inteiros')
                break
            vistos[inicio, fim] = any(h.startswith(inicio) and h.endswith(fim) and len(h) > len(inicio) + len(fim)
                                      for h in candidatos)
        if not vistos[inicio, fim]:
            if len(erros) > MAX_ERROS:
                ocultos += 1
                continue
            erros.append(f'hash abreviado ("{m[0][:40]}") não confere com nenhum hash inteiro do relatório: copie o '
                         'hash inteiro da saída; a abreviação só vale com o hash inteiro em outro ponto do relatório')
    return erros, ocultos


def _resultado(erros, achados=0, recibo=None, ocultos=0):
    ocultos += getattr(erros, 'ocultos', 0)  # os que a lista com teto só contou (F4)
    erros = list(erros)
    if len(erros) + ocultos > MAX_ERROS:
        erros = erros[:MAX_ERROS] + [f'mais {len(erros) + ocultos - MAX_ERROS} erros: corrija estes e confira de novo']
    return {'preenchimento_ok': not erros, 'merito_verificado': False,
            'achados_conferidos': achados, 'recibo_observado': recibo,
            'erros': erros, 'alcance': ALCANCE}


def validar(dados) -> dict:
    erros = _Erros()
    if not isinstance(dados, dict) or set(dados) - {'relatorio', 'recibo_texto'}:
        return _resultado(['entrada deve conter somente relatorio e recibo_texto opcional'])
    texto = dados.get('relatorio')
    if not isinstance(texto, str) or not texto.strip() or len(texto.encode('utf-8')) > MAX_ENTRADA:
        return _resultado(['relatorio deve ser texto não vazio dentro do teto'])
    formal = _formal(texto)
    dentro, secoes, linhas = False, 0, []
    for linha in formal.splitlines():
        titulo = _titulo(linha)
        if titulo is not None:
            dentro = titulo == 'achados'
            secoes += dentro
        elif dentro:
            linhas.append(linha)
    if secoes != 1:
        erros.append('use exatamente uma seção ## Achados')
    grupos = []
    for linha in linhas:
        if re.match(r'^\s*###\s+\S', linha):
            grupos.append([])
        elif grupos:
            grupos[-1].append(linha)
    if not grupos and not re.search(r'^[ \t]*nenhum achado comprovado(?: no escopo)?\.?[ \t]*$',
                                    '\n'.join(linhas), re.MULTILINE):
        erros.append('declare achados ou Nenhum achado comprovado no escopo')
    for i, grupo in enumerate(grupos, 1):
        corpo = '\n'.join(grupo)
        valores = re.findall(r'^[ \t]*-[ \t]+confianca:[ \t]*(alta|media|baixa)(?=[ \t]*(?:[.;(]|$))',
                             corpo, re.MULTILINE)
        declaracoes = re.findall(r'^[ \t]*-[ \t]+confianca:', corpo, re.MULTILINE)
        if len(valores) != 1 or len(declaracoes) != 1:
            erros.append(f'achado {i}: declare exatamente uma confiança alta, média ou baixa')
        for nome, padrao in CAMPOS:
            valor = _valor(corpo, padrao)
            if not valor:
                erros.append(f'achado {i}: preencha {nome} na mesma linha do campo')
            elif MODELO.search(valor):
                erros.append(f'achado {i}: substitua o texto do modelo no campo {nome}')
        local = _valor(corpo, 'local')
        if local and not LOCAL_OK.search(local):
            erros.append(f'achado {i}: o local precisa de arquivo:linha, registro ou "metadado"')
    _alcance(_com_acento(texto), erros)
    _, ocultos = _hashes_abreviados(texto, erros)
    hashes = [h.strip(' \t') for h in re.findall(r'^[ \t]*-[ \t]+recibo sha-256:(.*)$', formal, re.MULTILINE)]
    quantidades = [q.strip(' \t') for q in re.findall(r'^[ \t]*-[ \t]+operacoes no recibo:(.*)$', formal,
                                                      re.MULTILINE)]
    observado = None
    if 'recibo_texto' in dados:
        bruto = dados['recibo_texto']
        if not isinstance(bruto, str) or len(bruto.encode('utf-8')) > MAX_ENTRADA:
            erros.append('recibo_texto deve ser literal textual dentro do teto')
        else:
            try:
                recibo = _json(bruto)
                if not isinstance(recibo, dict) or recibo.get('formato') != 'fundacao.operacoes-observadas/1':
                    raise ValueError('formato de recibo inválido')
                ops = recibo.get('operacoes')
                if not isinstance(ops, list):
                    raise ValueError('operações devem ser lista')
                ids = [op.get('id') if isinstance(op, dict) else None for op in ops]
                if not all(isinstance(x, str) and x for x in ids) or len(set(ids)) != len(ids):
                    raise ValueError('IDs de operação ausentes ou repetidos')
                observado = {'operacoes': len(ops), 'sha256': hashlib.sha256(bruto.encode('utf-8')).hexdigest()}
            except (ValueError, TypeError, RecursionError):
                erros.append('recibo literal inválido: confira JSON, formato e IDs únicos')
        if observado is not None:
            if len(hashes) != 1 or hashes[0] != observado['sha256']:
                erros.append('declare um único Recibo SHA-256 igual ao literal recebido')
            if (len(quantidades) != 1 or not re.fullmatch(r'0|[1-9][0-9]*', quantidades[0])
                    or quantidades[0] != str(observado['operacoes'])):
                erros.append('quantidade em Operações no recibo difere do literal recebido')
    elif hashes or quantidades:
        erros.append('recibo declarado sem literal recebido: conferência não medida')
    return _resultado(erros, len(grupos), observado, ocultos)


def processar(bruto: bytes) -> dict:
    if len(bruto) > MAX_ENTRADA:
        return _resultado(['entrada acima de 2MiB'])
    try:
        return validar(_json(bruto.decode('utf-8')))
    except (ValueError, TypeError, RecursionError, UnicodeError):
        return _resultado(['entrada UTF-8/JSON inválida, duplicada ou fora dos tipos esperados'])


def main() -> int:
    argparse.ArgumentParser(description=__doc__).parse_args()
    resultado = processar(sys.stdin.buffer.read(MAX_ENTRADA + 1))
    print(json.dumps(resultado, ensure_ascii=False))
    return 0 if resultado['preenchimento_ok'] else 1


if __name__ == '__main__':
    try:
        sys.stdout.reconfigure(encoding='utf-8')
    except (AttributeError, ValueError):
        pass
    raise SystemExit(main())
