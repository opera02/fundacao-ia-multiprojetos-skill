#!/usr/bin/env python3
"""Perfil de execução aprovado pelo SHA-256, do fluxo B (1.7.10, desenho §8.4; escopo 0.10, respostas G3b e E1 do
titular). O titular aprova o SHA-256 que o `conferir-perfil` mostra, com o texto para a folha de decisões, e o `rodar`
o recebe na linha de comando; a seção `execucao` da ficha de aberturas, que o prenderia numa assinatura, fica para a
1.7.11 [revisão da terceira rodada da integração da 1.7.10, defeito 3: o texto dizia "assinado" e a folha prometia a
ficha].

Dividido de `execucao_isolada.py` (a regra de tamanho e o precedente da 1.7.7, que tirou `codigo_do_plano.py` e
`folha_do_plano.py` do mesmo arquivo): aqui ficam o esquema do perfil, a leitura conferida, o plano de uma execução,
as máscaras de segredo, a conferência antes e depois e o registro. O ponto de entrada (`main`) continua em
`execucao_isolada.py`, que carrega este módulo e injeta nos globais dele as primitivas da caixa (o "motor"), antes de
executá-lo, para este módulo não reimportar a caixa (o que faria um ciclo) e partilhar a mesma classe `Recusa`, o
mesmo `CODIGO` e as mesmas montagens. As primitivas injetadas (ver `execucao_isolada._carregar_perfil`): `Recusa`,
`_dentro`, `CODIGO`, `_sha256_de`, `_programa`, `montagens_do_sistema`, `sondar_bwrap`, `_montavel`, `_rodar`, `limites`,
`PATH_ISOLADO`, `_MIB`, `NOMES_DE_SEGREDO`, `REDE_NEGADA` e `_FIXOS`.

O perfil (`fundacao.perfil_execucao/1`, dentro de `projects/<P>/` de uma fundação) diz o tipo — `comandos-do-projeto`
(código NÃO preso, por decisão do titular) ou `ferramentas-de-terceiros` (código preso pelo manifesto, inclusive a
venv) —, os modelos de argv (marcadores `{caminho}`, `{caminhos}` no fim e `{saida}`, só para caminhos do projeto), as
montagens (árvore de trabalho ou código e alvos só leitura, uma pasta de saída gravável; a raiz nunca; nenhuma passa
por pasta ou nome de segredo), a rede (negada; a rede da caixa pela jaula do porteiro, com a lista de domínios da
ficha de aberturas, fica para a 1.7.11), o ambiente, os limites e a validade. O lançador confere o SHA-256 do perfil,
a validade, o argv contra os modelos e, no segundo tipo, o manifesto antes e depois; roda pela mesma caixa bubblewrap,
com os caminhos de segredo das árvores montadas escondidos (fora do código preso, os nomes fortes e as pastas de
segredo; dentro dele, só os nomes fortes; as negações por caminho do perfil do host ainda não chegam à caixa), e
registra cada execução em `projects/<P>/outputs/execucao/registro.jsonl` (argv, código, duração e SHA-256 das saídas).
A pasta de saída e o registro, na pasta do projeto que a sessão grava, são criados e abertos descendo da pasta do
projeto por descritor, sem atravessar ligação, no Linux (revisão de segurança da 1.7.10, FLUXB-F2).

Integração da 1.7.10 (pacote INTEG-FLUXOB do lote 2; contratos do lote 2, §3; pendências do FLUXOB-B):
- máscaras pela regra única (`regras_de_segredo.py`, NFKC e sem caixa): dentro do código preso (a raiz do código de
  terceiros, com a venv) só os nomes fortes; fora dele, os nomes fortes e as pastas de segredo; os nomes fracos nunca.
  O padrão forte vale também para o exemplo (`.env.example` casa `.env.*`), como nos perfis do host. O plano
  (`mascaras`, `mascaras_regra`) e a folha dizem o que fica escondido. Pasta de segredo de nome não forte (`.ssh`,
  `.aws`, `.kube`, `segredos`...) dentro do código preso recusa (no plano, no `conferir-perfil` e na conferência de
  antes): lá a máscara não a cobre (§3) e a caixa a leria [revisão do pacote INTEG-FLUXOB, defeito 1];
- o código preso só vale preso se a caixa não vê nele nada que o manifesto não prende: o nome fraco fora dele (B7:
  `segredos.py conferir` e, com código 0, o manifesto refeito com `--incluir-fraco`), a pasta ignorada, o `.git`, a
  exclusão, o nome fora do UTF-8, o arquivo especial (FIFO, socket ou dispositivo: por ele um processo de fora fala
  com a caixa; segunda revisão do pacote) e a ligação para fora do sistema ou do que ele prende recusam com o passo
  pronto; o que fica fora sem efeito no que roda (nome forte, que a caixa vê vazio; o `__pycache__`, que o Python da
  caixa não lê; a ligação para o sistema, para um arquivo preso ou para uma pasta do código preso fora do que o
  manifesto não prende, conferida antes e depois) vai para o plano, o `conferir-perfil` e a folha [revisão do pacote
  INTEG-FLUXOB, defeito 2];
- o passo pronto do B7 é um comando só, para o terminal do titular, que confere cada nome fraco e, só com código 0 em
  todos, refaz o manifesto levando-os; cada caminho e nome vai citado para o shell de destino
  (`codigo_do_plano.citar_no_terminal`), e o que não dá para citar com segurança recusa sem comando (renomeie-o). O
  nome fraco que o `segredos.py` não examina, separado pelos metadados (vínculo físico, acima do teto do conferir ou
  biblioteca compilada, como o `.so` do tiktoken), sai dessa cadeia, que pararia nele: levá-lo sem a conferência é
  decisão do titular, com um comando à parte; o binário de outro nome (`token.pickle`) fica na cadeia, que para nele
  (terceira revisão do pacote). O arquivo comum cujo nome termina em ' (ligação)' ou ' (especial)', o mesmo texto da
  ligação ou do especial do nome-base, também é conferido (terceira revisão);
- `rodar` amarrado ao projeto do lançador (`FUNDACAO_PROJECT`, ou `FUNDACAO_PROJETO_TRAVADO` do porteiro): o perfil
  tem de ser desse projeto, e o `--projeto` não troca de projeto; sem a variável, o `--projeto` é obrigatório.
"""

from __future__ import annotations

import glob
import hashlib
import importlib.util
import json
import os
import re
import stat
import subprocess
import sys
import time
from datetime import date, datetime, timezone
from pathlib import Path

AQUI = Path(__file__).resolve().parent


def _carregar(nome: str):
    """Um script ao lado deste, pelo caminho (sem mexer no `sys.path`)."""
    spec = importlib.util.spec_from_file_location(f"_perfil_execucao_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


GRAVACAO = _carregar("gravacao_segura")  # pasta de saída e registro sem seguir ligação
REGRAS = _carregar("regras_de_segredo")  # a regra única de segredo (contratos do lote 2, §3)
SEGREDOS = _carregar("segredos")  # o teto do conferir do B7 (TETO_BYTES): acima dele, o arquivo não é examinado

ESQUEMA_PERFIL = "fundacao.perfil_execucao/1"
ESQUEMA_PLANO_PERFIL = "fundacao.plano-perfil/1"
COMANDOS_DO_PROJETO, FERRAMENTAS_DE_TERCEIROS = "comandos-do-projeto", "ferramentas-de-terceiros"
CAMPOS_DO_PERFIL = {"schema_version", "perfil_id", "projeto", "tipo", "motivo", "validade", "modelos", "codigo",
                    "montagens", "cwd", "rede", "ambiente", "limites"}
OBRIGATORIOS_DO_PERFIL = CAMPOS_DO_PERFIL - {"cwd", "rede", "ambiente", "limites"}
MARCADORES = ("{caminhos}", "{caminho}", "{saida}")  # só caminhos do projeto; {caminhos} é o último, inteiro
ID_DO_PERFIL = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]{0,99}$")
ID_PROJETO = re.compile(r"^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$")  # o identificador do kit (fundacao/core/paths.py)
NOME_DE_VARIAVEL = re.compile(r"^[A-Za-z_][A-Za-z0-9_]{0,63}$")
RESERVADAS = {"PATH", "HOME", "TMPDIR", "TMP", "TEMP", "PYTHONPYCACHEPREFIX", "PYTHONDONTWRITEBYTECODE"}
LIMITES_DO_PERFIL = {"tempo_s": (600, 86_400), "saida_mb": (32, 1024), "memoria_mb": (4096, 65_536),
                     "arquivo_mb": (512, 65_536), "processos": (256, 4096)}  # (padrão, teto)
FORA_DA_SAIDA = {".git", ".claude", ".porteiro", ".navegador", "_browser_profile", "decisoes"}
PYCACHE_DA_CAIXA = "/tmp/pycache"  # ferramentas de terceiros: o Python não lê o __pycache__ da pasta presa
MASCARAS_REGRA = ("escondidos da caixa (ela os vê vazios), pela regra única de segredo: no código preso (a raiz do "
                  "código de terceiros, com a venv), só os arquivos e pastas de nome forte (chave, credencial ou "
                  "cofre: .env, *.pem, *.key, id_rsa, *credentials*, *secret*...), e uma pasta de segredo de outro "
                  "nome (.ssh, .aws, segredos...) nele recusa a execução; nas outras montagens, também as pastas de "
                  "segredo (.ssh, .aws, secrets, .segredos...); os nomes fracos (token, senha, password) nunca")
LANCADOR = ("FUNDACAO_PROJECT", "FUNDACAO_PROJETO_TRAVADO")  # o projeto do lançador da sessão e o do porteiro (§2)
MOSTRADAS_NA_FOLHA = 20  # máscaras citadas pelo caminho na folha; acima disso, a contagem
# Biblioteca compilada (binária, que o `segredos.py conferir` não examina): numa venv de IA, `_tiktoken...so`,
# `tokenizers.abi3.so` têm nome fraco (terceira revisão do pacote INTEG-FLUXOB).
BIBLIOTECAS_COMPILADAS = (".so", ".pyd", ".dll", ".dylib")
NAO_PRESO_POR_DECISAO = ("NÃO PRESO, por decisão do titular (perfil comandos-do-projeto, G3b): o código da árvore de "
                         "trabalho pode mudar entre uma execução e outra; roda no bubblewrap, sem rede, sem a raiz e "
                         "sem os outros projetos")
PRESO_PELO_PERFIL = ("preso pelo manifesto do perfil (SHA-256 aprovado), inclusive a venv, conferido antes e depois "
                     "da execução; o __pycache__ da pasta não é lido (PYTHONPYCACHEPREFIX na caixa); fora do manifesto "
                     "fica só o que a caixa vê vazio (nome forte), esse __pycache__ e a ligação para o sistema, para "
                     "um arquivo preso ou para uma pasta do código preso fora do que o manifesto não prende, conferida "
                     "antes e depois (codigo_do_plano.fora_do_manifesto); o resto que ele não prende, inclusive o "
                     "arquivo especial (FIFO, socket ou dispositivo), recusa a execução")
SOLTO_NA_FOLHA = ("ATENÇÃO: o manifesto não prende {itens}; a caixa vê vazio o de nome forte, o Python dela não lê o "
                  "__pycache__ (PYTHONPYCACHEPREFIX) e cada ligação aponta para o sistema, para um arquivo preso ou "
                  "para uma pasta do código preso fora do que o manifesto não prende, conferida antes e depois de cada "
                  "execução; qualquer outra coisa fora do manifesto (o arquivo especial também) recusa a execução")
SEM_CAIXA_PARA_O_PERFIL = (  # revisão de segurança da 1.7.10, FLUXB-F5: o rodar pelo porteiro é da 1.7.11
    "recusado: o perfil de execução só roda no bubblewrap, e ele não abre aqui ({motivo}). No Ubuntu (WSL), se a "
    "caixa não abrir dentro do sandbox da sessão, o titular roda o mesmo comando no terminal dele; a operação rodar do "
    "porteiro fica para a 1.7.11. No Windows não há caixa")


def _rel_do_perfil(valor, campo: str, *, ponto: bool = False) -> str:
    """Caminho relativo à pasta do projeto, com /, sem '..' e sem ser absoluto (com `ponto`, '.' é a pasta toda)."""
    if not isinstance(valor, str) or not valor or "\\" in valor or "\0" in valor or len(valor) > 1024:
        raise Recusa(f"perfil: {campo} é um caminho relativo à pasta do projeto, com /")
    if valor == "." and ponto:
        return valor
    if valor.startswith("/") or re.match(r"^[A-Za-z]:", valor) or any(p in ("", ".", "..") for p in valor.split("/")):
        raise Recusa(f"perfil: {campo} {valor!r} sai do projeto, tem '..' ou é absoluto")
    return valor


def _no_projeto_do_perfil(pasta: str, rel: str) -> str:
    return pasta if rel == "." else os.path.normpath(os.path.join(pasta, *rel.split("/")))


def _de_segredo(nome: str) -> bool:
    """Nome (um componente) forte ou de pasta de segredo, pela regra única; o exemplo que casa um forte também conta
    (`.env.example` casa `.env.*`), como nas negações dos perfis do host (contratos do lote 2, §3)."""
    return REGRAS.classificar(nome, exemplos=()) in ("forte", "pasta-de-segredo")


def _nome_forte(nome: str) -> bool:
    """Só os nomes fortes da regra única, sem as pastas de segredo: o que se esconde dentro do código preso."""
    return REGRAS.classificar(nome, pastas=(), exemplos=()) == "forte"


def _modelos_do_perfil(modelos) -> list[dict]:
    if not isinstance(modelos, list) or not 1 <= len(modelos) <= 50:
        raise Recusa("perfil: modelos é uma lista de 1 a 50 modelos de argv")
    nomes = set()
    for i, item in enumerate(modelos):
        if (not isinstance(item, dict) or set(item) != {"nome", "argv"} or not isinstance(item["nome"], str)
                or not ID_DO_PERFIL.match(item["nome"]) or item["nome"] in nomes):
            raise Recusa(f"perfil: modelo {i} precisa de \"nome\" (único: letras, números, ponto, hífen) e \"argv\"")
        nomes.add(item["nome"])
        argv = item["argv"]
        if (not isinstance(argv, list) or not 1 <= len(argv) <= 100
                or not all(isinstance(a, str) and a and "\0" not in a for a in argv)):
            raise Recusa(f"perfil: modelo {item['nome']}: argv é uma lista de 1 a 100 textos")
        if "{" in argv[0] or "}" in argv[0]:
            raise Recusa(f"perfil: modelo {item['nome']}: o programa (argv[0]) é fixo, sem marcador")
        for j, elemento in enumerate(argv):
            limpo, marcas = elemento, 0
            for marca in MARCADORES:
                marcas += limpo.count(marca)
                limpo = limpo.replace(marca, "")
            if "{" in limpo or "}" in limpo or marcas > 1:
                raise Recusa(f"perfil: modelo {item['nome']}, elemento {j}: um marcador só ({', '.join(MARCADORES)})")
            if "{caminhos}" in elemento and (elemento != "{caminhos}" or j != len(argv) - 1):
                raise Recusa(f"perfil: modelo {item['nome']}: {{caminhos}} é um elemento inteiro e o último do argv")
    return modelos


def _codigo_do_perfil(tipo: str, codigo) -> dict:
    if tipo == COMANDOS_DO_PROJETO:
        if codigo != {"preso": False}:
            raise Recusa('perfil comandos-do-projeto: "codigo" é {"preso": false} (código não preso, por decisão do '
                         "titular)")
        return {"preso": False}
    if (not isinstance(codigo, dict) or codigo.get("preso") is not True
            or not {"raiz", "manifesto", "manifesto_sha256"} <= set(codigo)
            or not set(codigo) <= {"preso", "raiz", "manifesto", "manifesto_sha256", "venv"}):
        raise Recusa('perfil ferramentas-de-terceiros: "codigo" é {"preso": true, "raiz", "manifesto", '
                     '"manifesto_sha256"[, "venv"]}')
    if not isinstance(codigo["manifesto_sha256"], str) or not re.fullmatch(r"[0-9a-f]{64}", codigo["manifesto_sha256"]):
        raise Recusa("perfil: codigo.manifesto_sha256 é o SHA-256 do manifesto (64 dígitos hexadecimais)")
    out = {"preso": True, "raiz": _rel_do_perfil(codigo["raiz"], "codigo.raiz"),
           "manifesto": _rel_do_perfil(codigo["manifesto"], "codigo.manifesto"),
           "manifesto_sha256": codigo["manifesto_sha256"]}
    if "venv" in codigo:
        out["venv"] = _rel_do_perfil(codigo["venv"], "codigo.venv")
        if not out["venv"].startswith(out["raiz"] + "/"):
            raise Recusa("perfil: codigo.venv fica dentro de codigo.raiz (o manifesto do código a prende)")
    for campo in ("raiz", "venv"):  # a raiz do código e a venv montadas não passam por pasta ou nome de segredo
        if campo in out and any(_de_segredo(p) for p in out[campo].split("/")):
            raise Recusa(f"perfil: codigo.{campo} {out[campo]} passa por pasta ou nome de segredo")
    return out


def _montagens_do_perfil(tipo: str, montagens, perfil_rel: str | None = None) -> dict:
    permitidas = {"saida", "somente_leitura"} | ({"trabalho"} if tipo == COMANDOS_DO_PROJETO else set())
    if (not isinstance(montagens, dict) or not set(montagens) <= permitidas or "saida" not in montagens
            or (tipo == COMANDOS_DO_PROJETO and "trabalho" not in montagens)):
        raise Recusa(f"perfil {tipo}: montagens tem " + ('"trabalho", ' if tipo == COMANDOS_DO_PROJETO else "")
                     + '"saida" e, se quiser, "somente_leitura" (no outro tipo, o código entra pelo codigo.raiz)')
    leitura = montagens.get("somente_leitura", [])
    if not isinstance(leitura, list) or len(leitura) > 50:
        raise Recusa("perfil: montagens.somente_leitura é uma lista de até 50 caminhos")
    out = {"saida": _rel_do_perfil(montagens["saida"], "montagens.saida"),
           "somente_leitura": [_rel_do_perfil(r, "montagens.somente_leitura", ponto=True) for r in leitura]}
    if "trabalho" in montagens:
        out["trabalho"] = _rel_do_perfil(montagens["trabalho"], "montagens.trabalho", ponto=True)
    partes = out["saida"].split("/")  # NTFS/WSL não distinguem maiúsculas: compara em minúsculas
    if partes[0].lower() in {"data", "decisoes"} or any(p.lower() in FORA_DA_SAIDA for p in partes):
        raise Recusa("perfil: a pasta de saída não fica em data/ (cópia de referência), decisoes/, .git, .claude, "
                     ".porteiro, .navegador nem _browser_profile")
    # Cada montagem (trabalho, somente_leitura, saída) recusa pasta ou nome de segredo em QUALQUER componente, não só
    # no último: senão uma árvore sob `secrets/` entraria sem máscara (a máscara só varre dentro da raiz montada).
    alvos = [("montagens.saida", out["saida"]), *(("montagens.somente_leitura", r) for r in out["somente_leitura"])]
    if "trabalho" in out:
        alvos.append(("montagens.trabalho", out["trabalho"]))
    for campo, rel in alvos:
        if rel != "." and any(_de_segredo(p) for p in rel.split("/")):
            raise Recusa(f"perfil: {campo} {rel} passa por pasta ou nome de segredo (acima do último componente "
                         "também): não é montada")
    reservados = ["outputs/execucao/registro.jsonl"] + ([perfil_rel] if perfil_rel else [])
    for alvo in reservados:  # a caixa grava na saída: ela não pode conter o registro das execuções nem o próprio perfil
        if alvo == out["saida"] or alvo.startswith(out["saida"] + "/"):
            raise Recusa(f"perfil: a pasta de saída {out['saida']} conteria o registro das execuções ou o próprio "
                         "perfil: use uma subpasta própria, fora deles")
    return out


def _ambiente_do_perfil(tipo: str, ambiente) -> dict:
    if not isinstance(ambiente, dict):
        raise Recusa("perfil: ambiente é um objeto NOME: valor")
    for nome, valor in ambiente.items():
        if not NOME_DE_VARIAVEL.match(nome) or not isinstance(valor, str) or "\0" in valor or len(valor) > 4096:
            raise Recusa(f"perfil: ambiente {nome!r}: nome ou valor inválido")
        if any(s in nome.upper() for s in NOMES_DE_SEGREDO):  # FLUXB-F5: a operação executar é da 1.7.11
            raise Recusa(f"perfil: ambiente {nome}: nome de segredo não passa ao código executado (segredo pelo "
                         "porteiro, na operação executar, fica para a 1.7.11)")
        if nome.upper().startswith("FUNDACAO_") or nome.upper() in RESERVADAS:
            raise Recusa(f"perfil: ambiente {nome}: reservado ao lançador")
        if tipo == FERRAMENTAS_DE_TERCEIROS and CODIGO.carrega_codigo(nome):
            raise Recusa(f"perfil: ambiente {nome} muda de onde o código é carregado e o deixaria NÃO PRESO")
    return dict(sorted(ambiente.items()))


def _limites_do_perfil(dados) -> dict:
    if not isinstance(dados, dict) or set(dados) - set(LIMITES_DO_PERFIL):
        raise Recusa("perfil: limites aceita " + ", ".join(LIMITES_DO_PERFIL))
    valores = {}
    for nome, (padrao, teto) in LIMITES_DO_PERFIL.items():
        valor = dados.get(nome, padrao)
        if not isinstance(valor, int) or isinstance(valor, bool) or not 1 <= valor <= teto:
            raise Recusa(f"perfil: limites.{nome} é um inteiro de 1 a {teto}")
        valores[nome] = valor
    return limites(valores["tempo_s"], valores["saida_mb"], valores["memoria_mb"], valores["arquivo_mb"],
                   valores["processos"])


def ler_perfil(arquivo, sha256_aprovado: str | None, *, projeto: str | None = None, hoje: date | None = None) -> dict:
    """O perfil conferido: o SHA-256 dos bytes lidos contra o aprovado (None: só mostra), o projeto pela pasta onde
    ele fica (`projects/<P>/` de uma fundação, com `state/state.sqlite`), a validade e o esquema inteiro (campo
    desconhecido recusa: o titular lê tudo o que vale)."""
    arquivo = Path(os.path.abspath(arquivo))
    if os.path.realpath(arquivo) != str(arquivo):
        raise Recusa(f"o perfil {arquivo} passa por ligação (link simbólico ou junção): use o caminho real")
    try:
        bruto = arquivo.read_bytes()
    except OSError as exc:
        raise Recusa(f"perfil ilegível: {arquivo} ({type(exc).__name__})") from None
    sha = hashlib.sha256(bruto).hexdigest()
    if sha256_aprovado is not None and sha != sha256_aprovado.strip().lower():
        raise Recusa(f"o perfil não tem o SHA-256 aprovado (tem {sha}): o SHA-256 aprovado prende o arquivo exato; "
                     "mostre o perfil novo (conferir-perfil) e peça nova aprovação")
    try:
        dados = json.loads(bruto.decode("utf-8"))
    except (UnicodeDecodeError, ValueError):
        raise Recusa("perfil ilegível (não é JSON em UTF-8)") from None
    if not isinstance(dados, dict) or dados.get("schema_version") != ESQUEMA_PERFIL:
        raise Recusa(f"perfil fora do esquema {ESQUEMA_PERFIL}")
    faltam, sobram = sorted(OBRIGATORIOS_DO_PERFIL - set(dados)), sorted(set(dados) - CAMPOS_DO_PERFIL)
    if faltam or sobram:
        raise Recusa(f"perfil: faltam {faltam} ou sobram campos desconhecidos {sobram}")
    # Ancorado na raiz de uma fundação: a pasta cujo pai se chama `projects` e cujo avô tem `state/state.sqlite`;
    # uma pasta `projects/` solta, fora de uma fundação, não vale como projeto.
    pasta = next((p for p in arquivo.parents if p.parent.name == "projects"
                  and (p.parent.parent / "state" / "state.sqlite").exists()), None)
    if pasta is None:
        raise Recusa(f"o perfil {arquivo} fica fora de projects/<projeto>/ de uma fundação (com state/state.sqlite): "
                     "perfil é sempre de um projeto de uma fundação")
    if (not isinstance(dados["projeto"], str) or not ID_PROJETO.match(dados["projeto"])
            or dados["projeto"] != pasta.name):
        raise Recusa(f"perfil do projeto {dados['projeto']!r} guardado em {pasta}: vale só no projeto dele")
    if projeto is not None and projeto != pasta.name:
        raise Recusa(f"o perfil é do projeto {pasta.name}, não de {projeto}")
    if not isinstance(dados["perfil_id"], str) or not ID_DO_PERFIL.match(dados["perfil_id"]):
        raise Recusa("perfil: perfil_id com letras, números, ponto, hífen e sublinhado")
    if dados["tipo"] not in (COMANDOS_DO_PROJETO, FERRAMENTAS_DE_TERCEIROS):
        raise Recusa(f"perfil: tipo {COMANDOS_DO_PROJETO} ou {FERRAMENTAS_DE_TERCEIROS}")
    if not isinstance(dados["motivo"], str) or not dados["motivo"].strip():
        raise Recusa("perfil: motivo com as palavras do titular")
    # A validade é estritamente AAAA-MM-DD: o `date.fromisoformat` do Python 3.11+ aceitaria formatos básicos
    # (20991231) e de semana, que o titular não espera de uma data do perfil.
    if not isinstance(dados["validade"], str) or not re.fullmatch(r"\d{4}-\d{2}-\d{2}", dados["validade"]):
        validade = None
    else:
        try:
            validade = date.fromisoformat(dados["validade"])
        except ValueError:
            validade = None
    if validade is None:
        raise Recusa("perfil: validade é uma data AAAA-MM-DD (o último dia em que vale)")
    if (hoje or date.today()) > validade:
        raise Recusa(f"perfil vencido em {validade.isoformat()}: nada foi executado; peça um perfil novo ao titular")
    rede = dados.get("rede", {"dominios": []})
    if not isinstance(rede, dict) or set(rede) - {"dominios"} or rede.get("dominios", []) != []:
        # FLUXB-F5: a seção rede da ficha vale para os comandos da sessão; a da caixa, pela jaula, é da 1.7.11.
        raise Recusa("perfil: a caixa roda sem rede; a seção rede da ficha de aberturas vale para os comandos da "
                     "sessão, e a rede da caixa, pela jaula do porteiro (desenho §8.1), fica para a 1.7.11")
    return {"arquivo": str(arquivo), "sha256": sha, "pasta_projeto": str(pasta), "projeto": pasta.name,
            "perfil_id": dados["perfil_id"], "tipo": dados["tipo"], "motivo": dados["motivo"].strip(),
            "validade": validade.isoformat(), "modelos": _modelos_do_perfil(dados["modelos"]),
            "codigo": _codigo_do_perfil(dados["tipo"], dados["codigo"]),
            "montagens": _montagens_do_perfil(dados["tipo"], dados["montagens"], arquivo.relative_to(pasta).as_posix()),
            "cwd": _rel_do_perfil(dados["cwd"], "cwd", ponto=True) if "cwd" in dados else None,
            "ambiente": _ambiente_do_perfil(dados["tipo"], dados.get("ambiente", {})),
            "limites": _limites_do_perfil(dados.get("limites", {}))}


def _arvores(perfil: dict) -> tuple[list[str], str, str | None, str]:
    """(árvores só leitura, pasta de saída, raiz do código preso ou None, pasta de trabalho), em caminho absoluto."""
    pasta, m, codigo = perfil["pasta_projeto"], perfil["montagens"], perfil["codigo"]
    raiz_codigo = _no_projeto_do_perfil(pasta, codigo["raiz"]) if codigo["preso"] else None
    leitura = [_no_projeto_do_perfil(pasta, m["trabalho"]) if "trabalho" in m else raiz_codigo]
    leitura += [_no_projeto_do_perfil(pasta, r) for r in m["somente_leitura"]]
    leitura = list(dict.fromkeys(leitura))
    cwd = _no_projeto_do_perfil(pasta, perfil["cwd"]) if perfil["cwd"] else leitura[0]
    return leitura, _no_projeto_do_perfil(pasta, m["saida"]), raiz_codigo, cwd


def _mascarar(nome: str, caminho: str, presa: str | None) -> bool:
    """Dentro do código preso (`presa`), só o nome forte; fora dele, o forte e a pasta de segredo (contratos do lote 2,
    §3: senão as pastas e os nomes de biblioteca da venv quebrariam a ferramenta). O fraco, nunca."""
    return _nome_forte(nome) if presa is not None and _dentro(caminho, presa) else _de_segredo(nome)


def _recusar_pasta_de_segredo_no_codigo(nome: str, caminho: str, presa: str | None) -> None:
    """Dentro do código preso, o nome de pasta de segredo que não é forte (`.ssh`, `.aws`, `.kube`, `.docker`,
    `segredos`, `_browser_profile`...) não fica escondido (§3: lá só os fortes) e a caixa o leria e o devolveria pela
    saída: recusa, sem mudar as máscaras do §3 [revisão do pacote INTEG-FLUXOB, defeito 1]. `credentials/` e
    `secrets/` casam os fortes `*credentials*` e `*secret*` e continuam escondidas."""
    if (presa is not None and _dentro(caminho, presa) and not _nome_forte(nome)
            and REGRAS.e_pasta_de_segredo(nome)):
        raise Recusa(f"o código preso tem a pasta de segredo {caminho}: dentro dele só os nomes fortes ficam "
                     "escondidos (contratos do lote 2, §3) e a caixa a leria; tire-a da raiz do código")


def mascaras(arvores: list[str], presa: str | None = None) -> list[list[str]]:
    """Os caminhos de segredo dentro das árvores montadas, pela regra única e sem seguir ligação: a caixa os vê vazios
    (`--ro-bind /dev/null` no arquivo, `--tmpfs` na pasta). Fora do código preso, os nomes fortes e as pastas de
    segredo; dentro dele (`presa`, a raiz do código de terceiros), só o nome forte (`_mascarar`), e a pasta de segredo
    de outro nome recusa (`_recusar_pasta_de_segredo_no_codigo`). As negações por caminho do perfil do host ainda não
    chegam aqui (pendência). Árvore que é ela mesma de segredo: recusa."""
    achados = set()
    for arvore in arvores:
        if _de_segredo(os.path.basename(arvore)):
            raise Recusa(f"{arvore} tem nome de segredo: não é montada")
        if not os.path.isdir(arvore):
            continue
        for atual, subpastas, arquivos in os.walk(arvore):
            for nome in list(subpastas):
                caminho = os.path.join(atual, nome)
                if CODIGO.MANIFESTO.e_ligacao(Path(caminho)):
                    subpastas.remove(nome)  # não segue: a caixa monta só a árvore conferida
                    continue
                _recusar_pasta_de_segredo_no_codigo(nome, caminho, presa)
                if _mascarar(nome, caminho, presa):
                    subpastas.remove(nome)
                    achados.add(("pasta", caminho))
            for nome in arquivos:
                caminho = os.path.join(atual, nome)
                if CODIGO.MANIFESTO.e_ligacao(Path(caminho)):
                    continue  # a ligação fica para a conferência do código preso (`soltos_do_codigo`)
                _recusar_pasta_de_segredo_no_codigo(nome, caminho, presa)
                if _mascarar(nome, caminho, presa):
                    achados.add(("arquivo", caminho))
    return [list(a) for a in sorted(achados, key=lambda a: a[1])]


def _caminho_do_marcador(texto: str, marca: str, *, cwd: str, leitura: list[str], saida: str) -> str:
    if not texto or texto.startswith("-") or any(c in texto for c in "\0\n\r"):
        raise Recusa(f"{marca}: {texto[:80]!r} não é um caminho (vazio, começa com '-' ou tem quebra de linha)")
    caminho = os.path.normpath(os.path.join(cwd, texto))
    areas = [saida] if marca == "{saida}" else [*leitura, saida]
    dentro = next((area for area in areas if _dentro(caminho, area)), None)
    if dentro is None:
        raise Recusa(f"{marca}: {caminho} fica fora das montagens do perfil")
    rel = os.path.relpath(caminho, dentro)
    if any(_de_segredo(p) for p in rel.replace(os.sep, "/").split("/") if p not in ("", ".", "..")):
        raise Recusa(f"{marca}: {caminho} passa por pasta ou nome de segredo")
    if marca != "{saida}" and not os.path.lexists(caminho):
        raise Recusa(f"{marca}: {caminho} não existe")
    return caminho


def casar_argv(modelos: list[dict], argv: list[str], *, cwd: str, leitura: list[str],
               saida: str) -> tuple[str, list[str], list[str]]:
    """(nome do modelo, comando com os caminhos absolutos, comando para conferir com cada caminho como {entrada}). Um
    elemento sem marcador casa só com ele mesmo; com marcador, o valor é um caminho dentro das montagens."""
    motivos = []
    for modelo in modelos:
        molde = modelo["argv"]
        if molde[-1] == "{caminhos}":
            if len(argv) < len(molde):
                motivos.append(f"{modelo['nome']}: argumentos a menos")
                continue
            pares = list(zip(molde[:-1], argv)) + [("{caminho}", a) for a in argv[len(molde) - 1:]]
        elif len(argv) != len(molde):
            motivos.append(f"{modelo['nome']}: {len(argv)} argumentos, o modelo tem {len(molde)}")
            continue
        else:
            pares = list(zip(molde, argv))
        try:
            comando, para_conferir = [], []
            for elemento, valor in pares:
                marca = next((m for m in MARCADORES if m in elemento), None)
                if marca is None:
                    if valor != elemento:
                        raise Recusa(f"{valor[:80]!r} no lugar de {elemento[:80]!r}")
                    comando.append(valor)
                    para_conferir.append(valor)
                    continue
                antes, _, depois = elemento.partition(marca)
                if not (valor.startswith(antes) and valor.endswith(depois) and len(valor) > len(antes) + len(depois)):
                    raise Recusa(f"{valor[:80]!r} não tem a forma {elemento!r}")
                meio = valor[len(antes):len(valor) - len(depois)]
                caminho = _caminho_do_marcador(meio, "{caminho}" if marca == "{caminhos}" else marca, cwd=cwd,
                                               leitura=leitura, saida=saida)
                comando.append(antes + caminho + depois)
                para_conferir.append(antes + CODIGO.MARCAS[0] + depois)
            return modelo["nome"], comando, para_conferir
        except Recusa as exc:
            motivos.append(f"{modelo['nome']}: {exc}")
    raise Recusa("o comando não casa com nenhum modelo do perfil: " + "; ".join(motivos)[:800])


def _manifesto_do_perfil(perfil: dict, raiz_codigo: str) -> tuple[dict, dict, dict]:
    """O manifesto do código preso, com o SHA-256 do perfil, lido pela regra do `manifesto.py verificar`; com a venv,
    ela tem de estar no que ele prende (nenhuma pasta dela entre as ignoradas e algum arquivo dela na lista).
    (resumo para o plano, manifesto, política)."""
    codigo = perfil["codigo"]
    arquivo = _no_projeto_do_perfil(perfil["pasta_projeto"], codigo["manifesto"])
    try:
        dados = Path(arquivo).read_bytes()
    except OSError as exc:
        raise Recusa(f"manifesto do código ilegível: {arquivo} ({type(exc).__name__})") from None
    sha = hashlib.sha256(dados).hexdigest()
    if sha != codigo["manifesto_sha256"]:
        raise Recusa(f"o manifesto do código não tem o SHA-256 do perfil (tem {sha}): o código mudou depois do aceite; "
                     "refaça manifesto e perfil e peça novo aceite")
    ref, politica, antigos = CODIGO.ler_manifesto(dados)
    if "venv" in codigo:
        venv = codigo["venv"][len(codigo["raiz"]) + 1:]
        if any(p in politica["pastas_ignoradas"] for p in venv.split("/")):
            raise Recusa(f"o manifesto ignora a venv {codigo['venv']}: refaça-o com ela incluída (a pasta dela fora "
                         "das ignoradas), para o código e as bibliotecas ficarem presos")
        if not any(f["path"].startswith(venv + "/") for f in ref["arquivos"]):
            raise Recusa(f"o manifesto não prende nenhum arquivo da venv {codigo['venv']}")
    fora = CODIGO.fora_do_manifesto(raiz_codigo, politica, antigos, arquivo, None)
    resumo = {"arquivo": arquivo, "sha256": sha, "fora_do_manifesto": fora, "pasta_gravavel_na_copia": None}
    return resumo, ref, politica


def _do_fora(item: str) -> tuple[str, str]:
    """(tipo, caminho relativo) de um item de `codigo_do_plano.fora_do_manifesto`: 'ligacao', 'especial' (FIFO, socket
    ou dispositivo), 'pasta', 'arquivo' ou 'fora-do-utf8' (o item é o `ascii` do nome, que não volta a ser caminho)."""
    if item.endswith(CODIGO.LIGACAO):
        return "ligacao", item[:-len(CODIGO.LIGACAO)]
    if item.endswith(CODIGO.ESPECIAL):
        return "especial", item[:-len(CODIGO.ESPECIAL)]
    if item[:1] in ("'", '"') and item[-1:] == item[:1] and "\\udc" in item:
        return "fora-do-utf8", item
    if item.endswith("/"):
        return "pasta", item[:-1]
    return "arquivo", item


def _ligacao_conferida(caminho: str, raiz: str, presos: set[str], fora: list[str], sistema: list) -> bool:
    """A ligação do código preso aponta, pelo caminho real, para o sistema que a caixa monta só leitura (o `bin/python`
    da venv) ou para o que o manifesto prende (um arquivo da lista dele, ou uma pasta do código fora do que ele não
    prende, como o `lib64 -> lib` da venv). Conferida no plano e antes e depois de cada execução."""
    alvo = os.path.realpath(caminho)
    if any(_dentro(alvo, os.path.realpath(m[1])) for m in sistema if m[0] == "ro-bind"):
        return True
    base = os.path.realpath(raiz)
    if not _dentro(alvo, base):
        return False
    rel = Path(alvo).relative_to(base).as_posix()
    if rel != "." and CODIGO.nao_preso(rel, fora):
        return False
    if os.path.isfile(alvo):
        return os.path.normcase(rel) in presos
    return os.path.isdir(alvo)


def _arquivo_comum(caminho: str) -> bool:
    """O caminho é um arquivo comum, pelo `lstat` (sem seguir ligação); erro conta como não."""
    try:
        return stat.S_ISREG(os.lstat(caminho).st_mode)
    except OSError:
        return False


def soltos_do_codigo(raiz: str, ref: dict, fora: list[str], mascaradas: list, sistema: list, *,
                     ligacoes: bool = True) -> list[tuple[str, str]]:
    """Ferramentas de terceiros: o que o código preso tem fora do manifesto e a caixa vê sem máscara, (tipo, item):
    cada um deixaria o código NÃO PRESO (trocado depois do aceite, rodaria na caixa com o plano dizendo preso). Ficam
    de fora só o que a máscara esconde (nome forte: a caixa o vê vazio), o `__pycache__` (o Python da caixa não o lê:
    PYTHONPYCACHEPREFIX) e a ligação conferida (`_ligacao_conferida`) [revisão do pacote INTEG-FLUXOB, defeito 2]. O
    arquivo especial (FIFO, socket ou dispositivo) fica sempre: a máscara não muda o que ele é, e por ele um processo de
    fora entrega à caixa o que quiser a cada execução (um FIFO `x.pth` no site-packages é lido pelo `site` do Python)
    [segunda revisão do pacote]. `ligacoes=False` (o conferir-perfil fora do Linux, onde a caixa não roda e a ligação
    criada no WSL nem se resolve): a ligação fica para o Linux, conferida no plano e antes e depois de cada execução.
    O sufixo ' (ligação)' ou ' (especial)' do item também pode ser o fim do nome de um arquivo comum de verdade, que
    dá o mesmo texto da ligação ou do especial do nome-base: se esse arquivo comum existe (pelo `lstat`; a pasta e a
    ligação desse nome não dão esse texto), fora do manifesto e sem máscara, ele também fica solto, como arquivo, e cai
    no passo do nome fraco ou da exclusão; depois de levado ao manifesto, não volta. A ligação ou o especial do
    nome-base continua conferido sempre que o nome-base existe [terceira revisão do pacote]."""
    presos = {os.path.normcase(f["path"]) for f in ref["arquivos"]}
    normal = [(t, os.path.normcase(os.path.normpath(c))) for t, c in mascaradas]
    arquivos = {c for t, c in normal if t == "arquivo"}
    pastas = [c for t, c in normal if t != "arquivo"]
    ilegiveis = {ascii(Path(c).relative_to(raiz).as_posix()) for _t, c in mascaradas if _dentro(c, raiz)}

    def escondido(caminho: str) -> bool:  # a máscara o cobre: a caixa o vê vazio
        alvo = os.path.normcase(caminho)
        return alvo in arquivos or any(_dentro(alvo, c) for c in pastas)

    soltos = []
    for item in fora:
        tipo, rel = _do_fora(item)
        if (tipo in ("ligacao", "especial") and _arquivo_comum(real := _no_projeto_do_perfil(raiz, item))
                and os.path.normcase(item) not in presos):  # o texto pode vir desse arquivo comum, fora do manifesto
            if not escondido(real):
                soltos.append(("arquivo", item))
            if not os.path.lexists(_no_projeto_do_perfil(raiz, rel)):
                continue  # e vem só dele: não há ligação nem especial com o nome-base
        if tipo == "fora-do-utf8":
            if item not in ilegiveis:
                soltos.append((tipo, item))
            continue
        if tipo == "especial":
            soltos.append((tipo, rel))
            continue
        if tipo == "pasta" and rel.rsplit("/", 1)[-1] == "__pycache__":
            continue  # o Python da caixa não lê o __pycache__ da pasta (PYTHONPYCACHEPREFIX)
        caminho = _no_projeto_do_perfil(raiz, rel)
        if tipo == "ligacao":
            if ligacoes and not _ligacao_conferida(caminho, raiz, presos, fora, sistema):
                soltos.append((tipo, rel))
            continue
        if escondido(caminho):
            continue  # a caixa o vê vazio
        soltos.append((tipo, rel))
    return list(dict.fromkeys(soltos))  # a ligação e o arquivo do mesmo texto repetem o item em `fora`


def _classe_do_solto(tipo: str, rel: str, politica: dict) -> str:
    """Por que o manifesto não o prende, para o passo da recusa."""
    if tipo in ("ligacao", "fora-do-utf8", "especial"):
        return tipo
    partes = rel.split("/")
    if any(REGRAS.normalizar(p) == ".git" for p in partes):
        return "git"
    pastas = politica.get("pastas_de_segredo", REGRAS.PASTAS_DE_SEGREDO)
    if tipo == "pasta":
        if REGRAS.e_pasta_de_segredo(partes[-1], (), pastas):
            return "pasta-de-segredo"
        return "pasta-ignorada" if partes[-1] in CODIGO.MANIFESTO.EXCLUDE_DIRS else "outro"
    regra = CODIGO.MANIFESTO._regra_da_politica(politica) if "modo_git" in politica else {}
    return {"fraco": "fraco", "forte": "segredo", "pasta-de-segredo": "pasta-de-segredo"}.get(
        REGRAS.classificar(rel, **regra), "outro")


PASSOS_DOS_SOLTOS = {
    "pasta-ignorada": "pasta que o manifesto ignora (node_modules, venv...): refaça-o com --incluir-pasta-ignorada "
                      "<nome> ou tire-a da raiz do código",
    "git": "o .git: tire-o da raiz do código (o perfil de terceiros não monta repositório Git; o importar.py o leva "
           "como .git.zip)",
    "ligacao": "ligação: aponte-a para o sistema (/usr), para um arquivo que o manifesto prende ou para uma pasta do "
               "código preso fora do que ele não prende, ou tire-a",
    "especial": "arquivo especial (FIFO, socket ou dispositivo): o manifesto não o lê nem o prende, e por ele um "
                "processo de fora falaria com a caixa; tire-o da raiz do código",
    "fora-do-utf8": "nome fora do UTF-8: renomeie-o (o manifesto não o lê)",
    "pasta-de-segredo": "pasta de segredo: tire-a da raiz do código",
    "segredo": "nome de segredo: tire-o da raiz do código",
    "outro": "o que o manifesto exclui (--excluir): refaça-o sem a exclusão ou tire o arquivo da raiz do código"}


def _refazer_manifesto(raiz: str, manifesto: str, politica: dict, fracos: list[str], powershell: bool) -> str:
    """O `manifesto.py criar` com as opções da política gravada e mais os nomes fracos conferidos (B7), cada caminho e
    valor citado para o terminal do titular (`codigo_do_plano.citar_no_terminal`: ValueError se não dá). O `modo_git`
    vai sem aspas: `manifesto.politica_efetiva` só aceita um dos três modos."""
    def citar(valor) -> str:
        return CODIGO.citar_no_terminal(valor, powershell=powershell)

    if "modo_git" in politica:
        canonicas = {REGRAS.normalizar(p) for p in REGRAS.PASTAS_DE_SEGREDO}
        opcoes = ["--git", politica["modo_git"]]
        opcoes += [f"--pasta-segredo {citar(p)}" for p in politica["pastas_de_segredo"]
                   if REGRAS.normalizar(p) not in canonicas]
        incluidas, levados = politica["pastas_incluidas"], politica["fracos_incluidos"]
    else:  # formato 2: o refeito é do formato 3, com as pastas que ele já levava
        opcoes, levados = [], []
        incluidas = sorted(set(CODIGO.MANIFESTO.EXCLUDE_DIRS) - {".git"} - set(politica["pastas_ignoradas"]))
    opcoes = (["--texto-canonico"] if politica.get("texto_canonico") else []) + opcoes
    opcoes += [f"--incluir-pasta-ignorada {citar(p)}" for p in incluidas]
    opcoes += [f"--excluir {citar(g)}" for g in politica["exclusoes_extras"]]
    opcoes += [f"--incluir-fraco {citar(g)}" for g in sorted({*levados, *map(glob.escape, fracos)})]
    return (f"{'python' if powershell else 'python3'} -I -B {citar(AQUI / 'manifesto.py')} criar --raiz {citar(raiz)} "
            f"--saida {citar(manifesto)} " + " ".join(opcoes))


def comando_do_b7(raiz: str, manifesto: str, politica: dict, fracos: list[str], *, sem_conferir: list[str] = (),
                  powershell: bool | None = None) -> str:
    """O B7 num comando só, para o terminal do titular [segunda revisão do pacote INTEG-FLUXOB]: `segredos.py conferir`
    de cada nome fraco (um arquivo por vez, para o código 0 valer para ele) e, só com código 0 em todos, o manifesto
    refeito levando todos (`--incluir-fraco`). No sh/bash, `&&`; no PowerShell (padrão no Windows), que na versão 5.1
    não tem `&&`, `if ($LASTEXITCODE -eq 0)`. Assim, nenhum nome fraco entra no manifesto sem a conferência dele, e a
    conferência e o manifesto saem juntos. `sem_conferir`: os que o `segredos.py` não examina (`nao_examinado`), que o
    titular decidiu levar sem a conferência: vão só para o manifesto [terceira revisão]. ValueError: um caminho ou nome
    não dá para citar com segurança."""
    powershell = os.name == "nt" if powershell is None else powershell
    segredos = CODIGO.citar_no_terminal(AQUI / "segredos.py", powershell=powershell)
    passos = [f"{'python' if powershell else 'python3'} -I -B {segredos} conferir "
              + CODIGO.citar_no_terminal(_no_projeto_do_perfil(raiz, r), powershell=powershell) for r in fracos]
    passos.append(_refazer_manifesto(raiz, manifesto, politica, [*fracos, *sem_conferir], powershell))
    if powershell:
        return passos[0] + "".join(f"; if ($LASTEXITCODE -eq 0) {{ {p} }}" for p in passos[1:])
    return " && ".join(passos)


def _lista_curta(itens: list[str]) -> str:
    """Os primeiros itens e quantos mais; nome com caractere invisível sai como `ascii` (`codigo_do_plano.visivel`)."""
    return ", ".join(map(CODIGO.visivel, itens[:MOSTRADAS_NA_FOLHA])) + (
        f" e mais {len(itens) - MOSTRADAS_NA_FOLHA}" if len(itens) > MOSTRADAS_NA_FOLHA else "")


def nao_examinado(caminho: str) -> str | None:
    """Por que o `segredos.py conferir` não examinaria o arquivo (código 1: o B7 pararia nele e o manifesto nunca seria
    refeito), só pelos metadados (`os.lstat`, sem ler conteúdo) [terceira revisão do pacote INTEG-FLUXOB]: vínculo
    físico, acima do teto do conferir (`segredos.TETO_BYTES`) ou biblioteca compilada (`BIBLIOTECAS_COMPILADAS`). None:
    ele o examina, ou o lstat falha (fica na conferência, que falha fechada). O binário de outro nome (`token.pickle`)
    também fica na conferência, que para nele: pode ser segredo, e a decisão sobre ele é do titular, sem comando."""
    try:
        st = os.lstat(caminho)
    except OSError:
        return None
    if st.st_nlink > 1:
        return "vínculo físico: o outro nome pode ser um arquivo de fora"
    if st.st_size > SEGREDOS.TETO_BYTES:
        return f"acima do teto do conferir, {SEGREDOS.TETO_BYTES // 1_000_000} MB"
    if os.path.basename(caminho).lower().endswith(BIBLIOTECAS_COMPILADAS):
        return "biblioteca compilada, binária"
    return None


def _sem_comando(oque: str, quantos: int, exc: ValueError) -> str:
    return (f"{oque}, {quantos} arquivo(s), mas {exc}, e o comando pronto não o cita com segurança no terminal: "
            "renomeie-o (ou tire-o da raiz do código) e peça o plano de novo, que traz o comando")


def recusar_soltos(soltos: list[tuple[str, str]], raiz: str, politica: dict, manifesto: str) -> None:
    """Recusa, com o passo pronto, o código preso que a caixa vê fora do manifesto (`soltos_do_codigo`); para o nome
    fraco, o B7 (`comando_do_b7`): um comando só, que confere todos e, com código 0 em todos, refaz o manifesto com
    `--incluir-fraco`. O nome fraco que o `segredos.py` não examina (`nao_examinado`: vínculo físico, acima do teto ou
    biblioteca compilada) sai dessa cadeia, que senão pararia nele: a recusa diz quais são e que levá-los sem a
    conferência é decisão do titular, com um comando à parte, que confere os outros do mesmo jeito e leva também esses
    [terceira revisão do pacote INTEG-FLUXOB]. Nome que não dá para citar com segurança no terminal: a recusa pede para
    renomeá-lo, sem comando."""
    if not soltos:
        return
    classes = {_classe_do_solto(tipo, rel, politica): None for tipo, rel in soltos}
    fracos = [rel for tipo, rel in soltos if _classe_do_solto(tipo, rel, politica) == "fraco"]
    motivos = {rel: motivo for rel in fracos if (motivo := nao_examinado(_no_projeto_do_perfil(raiz, rel)))}
    conferidos = [rel for rel in fracos if rel not in motivos]
    passos = []
    if conferidos:
        try:
            comando = comando_do_b7(raiz, manifesto, politica, conferidos)
        except ValueError as exc:
            passos.append(_sem_comando("nome fraco (token, senha, password...)", len(conferidos), exc))
        else:
            passos.append(f"nome fraco (token, senha, password...), {len(conferidos)} arquivo(s): rode no seu "
                          f"{CODIGO.TERMINAL} este comando, que confere o conteúdo de cada um (segredos.py conferir: "
                          "com código 1, por indício ou por arquivo que ele não examina, ele para e nada muda) e, só "
                          f"com código 0 em todos, refaz o manifesto levando-os (--incluir-fraco): {comando}")
    if motivos:
        oque = "nome fraco que o segredos.py não examina (código 1 em qualquer conferência)"
        try:
            comando = comando_do_b7(raiz, manifesto, politica, conferidos, sem_conferir=list(motivos))
        except ValueError as exc:
            passos.append(_sem_comando(oque, len(motivos), exc))
        else:
            fim = ("no lugar do comando acima, este outro, que confere os demais do mesmo jeito e refaz o manifesto "
                   "levando também esses" if conferidos else "este comando, que refaz o manifesto levando-os")
            passos.append(f"{oque}, {len(motivos)} arquivo(s): "
                          + _lista_curta([f"{rel} ({motivo})" for rel, motivo in motivos.items()])
                          + ". Levá-los ao manifesto sem a conferência do conteúdo é decisão sua; se decidir, rode no "
                          f"seu {CODIGO.TERMINAL} {fim} (--incluir-fraco, sem conferir): {comando}")
    passos += [PASSOS_DOS_SOLTOS[c] for c in classes if c != "fraco"]
    raise Recusa("perfil de ferramentas de terceiros (código preso), mas o código tem o que o manifesto não prende e "
                 f"a caixa veria e poderia carregar: {_lista_curta([rel for _t, rel in soltos])}. "
                 + "; ".join(passos) + ". Depois, ponha o manifesto_sha256 novo no perfil e peça novo aceite; nada foi "
                 "executado")


def _conferir_soltos_do_plano(plano: dict) -> None:
    """Antes e depois da execução, de novo pelo manifesto do plano (o SHA-256 dele conferido): uma ligação trocada
    depois do plano, para fora do sistema e do que ele prende, para a execução."""
    man = plano["manifesto"]
    try:
        dados = Path(man["arquivo"]).read_bytes()
    except OSError as exc:
        raise Recusa(f"manifesto do código ilegível: {man['arquivo']} ({type(exc).__name__})") from None
    if hashlib.sha256(dados).hexdigest() != man["sha256"]:
        raise Recusa(f"o manifesto {man['arquivo']} não tem mais o SHA-256 do plano: foi trocado depois do aceite")
    ref, politica, _antigos = CODIGO.ler_manifesto(dados)
    recusar_soltos(soltos_do_codigo(plano["copia"], ref, man["fora_do_manifesto"], plano["mascaras"],
                                    montagens_do_sistema()), plano["copia"], politica, man["arquivo"])


def _conferir_preso(raiz_codigo: str, ref: dict, fora: list[str], para_conferir: list[str], programa: str, cwd: str,
                    ambiente: dict, sistema: list, *, com_programa: bool = True) -> None:
    """Ferramentas de terceiros: o que o comando cita fica no código preso, o programa é do sistema ou um arquivo preso,
    e nada deixa o código NÃO PRESO (a regra de `codigo_do_plano.motivos_nao_preso`). `com_programa=False`: o
    programa não existe aqui (conferência do perfil fora do Linux) e só o resto é conferido."""
    CODIGO.conferir_citados(para_conferir, cwd, raiz_codigo)
    CODIGO.conferir_presos(para_conferir, cwd, raiz_codigo, ref, fora)
    real = os.path.realpath(programa)
    if com_programa and not any(_dentro(real, os.path.realpath(m[1])) for m in sistema if m[0] == "ro-bind"):
        presos = {os.path.normcase(f["path"]) for f in ref["arquivos"]}
        rel = Path(real).relative_to(raiz_codigo).as_posix() if _dentro(real, raiz_codigo) else None
        if rel is None or os.path.normcase(rel) not in presos or CODIGO.nao_preso(rel, fora):
            raise Recusa(f"o programa {programa} ({real}) não é do sistema nem um arquivo que o manifesto prende")
    motivos = CODIGO.motivos_nao_preso(para_conferir, cwd, raiz_codigo, programa, fora, list(ambiente))
    if motivos:
        raise Recusa("perfil de ferramentas de terceiros (código preso), mas este comando o deixaria NÃO PRESO: "
                     + "; ".join(motivos))


def plano_do_perfil(perfil: dict, argv: list[str], *, bwrap: str | None = None) -> dict:
    """O plano de uma execução pelo perfil já conferido (`ler_perfil`): montagens, máscaras de segredo, comando casado
    com um modelo, programa e, no tipo de terceiros, o manifesto do código. Só lê, salvo criar a pasta de saída."""
    if not argv:
        raise Recusa("informe o comando depois de --")
    if bwrap is None:
        bwrap, motivo = sondar_bwrap()
        if not bwrap:
            raise Recusa(SEM_CAIXA_PARA_O_PERFIL.format(motivo=motivo))
    pasta = perfil["pasta_projeto"]
    leitura, saida, raiz_codigo, cwd = _arvores(perfil)
    for arvore in leitura:
        if not os.path.exists(arvore):
            raise Recusa(f"montagem {arvore} não existe")
        _montavel(arvore)
    if any(_dentro(arvore, saida) for arvore in leitura):
        raise Recusa(f"a pasta de saída {saida} contém uma árvore só leitura, que deixaria de ser só leitura")
    if raiz_codigo and _dentro(saida, raiz_codigo):
        raise Recusa(f"a pasta de saída {saida} fica dentro do código preso {raiz_codigo}: use uma pasta fora dele")
    _criar_pasta(pasta, perfil["montagens"]["saida"])  # sem atravessar ligação (FLUXB-F2)
    _montavel(saida)
    if not os.path.isdir(cwd) or not any(_dentro(cwd, p) for p in [*leitura, saida]):
        raise Recusa(f"a pasta de trabalho {cwd} não existe ou fica fora das montagens do perfil")
    nome, comando, para_conferir = casar_argv(perfil["modelos"], [str(a) for a in argv], cwd=cwd, leitura=leitura,
                                              saida=saida)
    amb = {"PATH": PATH_ISOLADO, "HOME": "/tmp", "TMPDIR": "/tmp", "LANG": "C.UTF-8", **perfil["ambiente"]}
    if raiz_codigo:
        amb.update(PYTHONPYCACHEPREFIX=PYCACHE_DA_CAIXA, PYTHONDONTWRITEBYTECODE="1")
    programa = _programa(comando[0], amb["PATH"], cwd)
    sistema = montagens_do_sistema()
    real = os.path.realpath(programa["caminho"])
    if not any(_dentro(real, os.path.realpath(m[1])) for m in sistema + [["ro-bind", p] for p in leitura]
               if m[0] == "ro-bind"):
        raise Recusa(f"o programa {programa['caminho']} fica fora do que a caixa vê só leitura (o sistema e as árvores "
                     "do perfil)")
    plano = {"schema_version": ESQUEMA_PLANO_PERFIL, "acao": "rodar", "sistema": sys.platform, "isolamento": "bwrap",
             "perfil": {k: perfil[k] for k in ("arquivo", "sha256", "perfil_id", "tipo", "validade")},
             "projeto": perfil["projeto"], "modelo": nome, "comando": comando, "programa": programa, "cwd": cwd,
             "copia": raiz_codigo, "manifesto": None, "entradas": [], "leitura": leitura,
             "gravavel": {"tipo": "pasta-saida", "caminho": saida}, "ambiente": dict(sorted(amb.items())),
             "rede": REDE_NEGADA, "limites": perfil["limites"], "bwrap": bwrap,
             "montagens": sistema + [["ro-bind", p, p] for p in leitura] + [["bind", saida, saida]],
             "mascaras": mascaras([*leitura, saida], raiz_codigo), "mascaras_regra": MASCARAS_REGRA,
             "codigo_executado": NAO_PRESO_POR_DECISAO, "codigo_nao_preso": ["decisão do titular (G3b)"]}
    if raiz_codigo:
        plano["manifesto"], ref, politica = _manifesto_do_perfil(perfil, raiz_codigo)
        fora = plano["manifesto"]["fora_do_manifesto"]
        recusar_soltos(soltos_do_codigo(raiz_codigo, ref, fora, plano["mascaras"], sistema), raiz_codigo, politica,
                       plano["manifesto"]["arquivo"])
        _conferir_preso(raiz_codigo, ref, fora, para_conferir, programa["caminho"], cwd, perfil["ambiente"], sistema)
        plano.update(codigo_executado=PRESO_PELO_PERFIL, codigo_nao_preso=[])
    return plano


def conferir_plano_do_perfil(plano: dict, *, antes: bool) -> None:
    """Antes e depois da execução: o programa e (terceiros) o código preso continuam os do plano, e a caixa não vê
    nele nada que o manifesto não prende (`soltos_do_codigo`: uma ligação trocada para fora para a execução); antes,
    também as montagens e nenhum caminho de segredo novo nelas (a máscara é feita pela varredura do plano), conferidos
    primeiro: a pasta de segredo nova no código preso recusa com o motivo dela, e não só como item novo fora do
    manifesto."""
    if _sha256_de(plano["programa"]["caminho"]) != plano["programa"]["sha256"]:
        raise Recusa(f"o programa {plano['programa']['caminho']} não tem mais o SHA-256 do plano: foi trocado")
    if antes:
        for caminho in [*plano["leitura"], plano["gravavel"]["caminho"]]:
            _montavel(caminho)
        agora = mascaras([*plano["leitura"], plano["gravavel"]["caminho"]], plano["copia"])
        novas = [m[1] for m in agora if m not in plano["mascaras"]]
        if novas:
            raise Recusa("apareceu caminho de segredo nas montagens depois do plano: " + ", ".join(novas[:5]))
    if plano["manifesto"]:
        CODIGO.conferir_copia(plano)
        _conferir_soltos_do_plano(plano)


def argv_bwrap_perfil(plano: dict, descritores: dict | None = None) -> list[str]:
    """O argv do bubblewrap. Com `descritores` (caminho -> descritor aberto por `abrir_sem_seguir`), as árvores do
    projeto entram por `--ro-bind-fd`/`--bind-fd`: a caixa monta exatamente a pasta conferida, mesmo que a sessão a
    troque por uma ligação depois da conferência; sem eles (só para mostrar o plano), pelo caminho."""
    args = [plano["bwrap"], *_FIXOS]
    for nome, valor in plano["ambiente"].items():
        args += ["--setenv", nome, valor]
    for tipo, *caminhos in plano["montagens"]:
        if descritores and tipo in ("ro-bind", "bind") and caminhos[0] in descritores:
            args += [f"--{tipo}-fd", str(descritores[caminhos[0]]), caminhos[1]]
        else:
            args += [f"--{tipo}", *caminhos]
    for tipo, caminho in plano["mascaras"]:  # depois das árvores: cobre o caminho de segredo dentro delas
        args += ["--ro-bind", "/dev/null", caminho] if tipo == "arquivo" else ["--tmpfs", caminho]
    return [*args, "--chdir", plano["cwd"], "--", plano["programa"]["caminho"], *plano["comando"][1:]]


def abrir_sem_seguir(pasta: str, caminho: str) -> int:
    """Linux: descritor O_PATH de `caminho`, aberto componente a componente a partir da pasta do projeto, sem seguir
    ligação em nenhum deles."""
    fd = os.open(pasta, os.O_PATH | os.O_DIRECTORY | os.O_CLOEXEC)
    try:
        rel = os.path.relpath(caminho, pasta)
        partes = [] if rel == "." else rel.split(os.sep)
        for i, parte in enumerate(partes):
            pasta_do_meio = os.O_DIRECTORY if i < len(partes) - 1 else 0
            novo = os.open(parte, os.O_PATH | os.O_NOFOLLOW | os.O_CLOEXEC | pasta_do_meio, dir_fd=fd)
            os.close(fd)
            fd = novo
        if stat.S_ISLNK(os.fstat(fd).st_mode):
            raise Recusa(f"{caminho} virou ligação depois da conferência: nada foi executado")
        return fd
    except BaseException as exc:
        os.close(fd)
        if isinstance(exc, OSError):
            raise Recusa(f"{caminho} não abriu sem seguir ligação ({exc.strerror}): nada foi executado") from None
        raise


def bwrap_monta_por_descritor(bwrap: str) -> bool:
    """O bubblewrap aceita --ro-bind-fd e --bind-fd (0.8 ou mais novo; o Ubuntu 24.04 tem o 0.9)?"""
    try:
        r = subprocess.run([bwrap, "--help"], capture_output=True, text=True, errors="replace", env={}, timeout=30)
    except (OSError, subprocess.SubprocessError):
        return False
    return "--ro-bind-fd" in r.stdout + r.stderr and "--bind-fd" in r.stdout + r.stderr


def _escondidos(mascaradas: list[str] | None) -> str:
    """O que fica escondido da caixa: a regra e, quando a conferência os achou, os caminhos (os primeiros e quantos)."""
    if mascaradas is None:
        return f"arquivos e pastas de segredo ficam {MASCARAS_REGRA}"
    return (f"arquivos e pastas de segredo ficam {MASCARAS_REGRA}; hoje, {len(mascaradas)}"
            + (f": {_lista_curta(mascaradas)}" if mascaradas else " (nenhum caminho de segredo nas montagens)"))


def folha_do_perfil(perfil: dict, mascaradas: list[str] | None = None, fora: list[str] | None = None) -> str:
    """O texto para o titular ler antes de aprovar o SHA-256 do perfil (na folha de decisões; a seção `execucao` da
    ficha de aberturas, que o prenderia numa assinatura, é da 1.7.11). `mascaradas`: os caminhos que a conferência achou
    para esconder (None: só a regra); `fora`: o que o manifesto do código preso não prende
    (`manifesto.fora_do_manifesto`), dito na folha como no fluxo B (`folha_do_plano.codigo`)."""
    leitura, saida, _raiz, cwd = _arvores(perfil)
    codigo = perfil["codigo"]
    preso = (f"preso pelo manifesto {codigo['manifesto']} (SHA-256 {codigo['manifesto_sha256'][:12]}...)"
             + (f", inclusive a venv {codigo['venv']}" if "venv" in codigo else "")
             + ", conferido antes e depois de cada execução" if codigo["preso"] else
             "NÃO PRESO, por decisão sua (G3b): o código da árvore de trabalho pode mudar entre uma execução e outra")
    if codigo["preso"] and fora:
        preso += ". " + SOLTO_NA_FOLHA.format(itens=_lista_curta(fora))
    lim = perfil["limites"]
    modelos = "; ".join(f"{m['nome']}: {' '.join(m['argv'])}" for m in perfil["modelos"])
    ambiente = ", ".join(f"{k}={v}" for k, v in perfil["ambiente"].items()) or "nenhum"
    return (f"Perfil de execução {perfil['perfil_id']} do projeto {perfil['projeto']} ({perfil['tipo']}), válido até "
            f"{perfil['validade']}. Motivo: {perfil['motivo']}. Roda no bubblewrap, sem rede, sem a raiz da fundação e "
            f"sem os outros projetos, só estes comandos: {modelos}. Lê, só leitura: {', '.join(leitura)}; grava só em "
            f"{saida}; {_escondidos(mascaradas)}. Pasta de trabalho: {cwd}. Ambiente: "
            f"{ambiente}. Código: {preso}. Limites: {lim['tempo_s']} s, {lim['memoria_bytes'] // _MIB} MB de memória, "
            f"saída até {lim['saida_bytes'] // _MIB} MB, arquivo até {lim['arquivo_bytes'] // _MIB} MB, "
            f"{lim['processos']} processos. SHA-256 do perfil: {perfil['sha256']}. Para valer, você aprova este SHA-256 "
            "na folha de decisões; a seção execucao da ficha de aberturas, que o prenderia numa assinatura, fica para a "
            "1.7.11.")


def conferir_perfil(arquivo, projeto: str | None = None, *, hoje: date | None = None) -> dict:
    """Confere o perfil sem rodar nada (também onde não há bubblewrap): esquema, validade, montagens e, no tipo de
    terceiros, o manifesto, a venv, o que a caixa veria fora dele (`soltos_do_codigo`) e cada modelo preso. Devolve o
    SHA-256 que o titular aprova, o que fica escondido, o que o manifesto não prende e o texto da folha."""
    perfil = ler_perfil(arquivo, None, projeto=projeto, hoje=hoje)
    leitura, saida, raiz_codigo, cwd = _arvores(perfil)
    faltam = [p for p in leitura if not os.path.exists(p)]
    if faltam:
        raise Recusa("montagem inexistente: " + ", ".join(faltam))
    if any(_dentro(arvore, saida) for arvore in leitura) or (raiz_codigo and _dentro(saida, raiz_codigo)):
        raise Recusa(f"a pasta de saída {saida} contém uma árvore só leitura ou fica dentro do código preso")
    achadas = mascaras([*leitura, saida], raiz_codigo)  # pasta de segredo no código preso recusa aqui também
    avisos, fora = [], []
    if raiz_codigo:
        man, ref, politica = _manifesto_do_perfil(perfil, raiz_codigo)
        sistema, no_linux = montagens_do_sistema(), sys.platform.startswith("linux")
        fora = man["fora_do_manifesto"]
        recusar_soltos(soltos_do_codigo(raiz_codigo, ref, fora, achadas, sistema, ligacoes=no_linux), raiz_codigo,
                       politica, man["arquivo"])
        ligacoes = [item.removesuffix(" (ligação)") for item in fora if item.endswith(" (ligação)")]
        if ligacoes and not no_linux:
            avisos.append(f"o código preso tem ligação ({_lista_curta(ligacoes)}): ela é conferida no Linux, no plano "
                          f"e antes e depois de cada execução ({sys.platform})")
        for modelo in perfil["modelos"]:
            para_conferir = [e.replace("{caminhos}", CODIGO.MARCAS[0]).replace("{caminho}", CODIGO.MARCAS[0])
                             .replace("{saida}", CODIGO.MARCAS[0]) for e in modelo["argv"]]
            try:
                try:
                    programa, com_programa = _programa(para_conferir[0], PATH_ISOLADO, cwd)["caminho"], True
                except Recusa:
                    if sys.platform.startswith("linux"):
                        raise
                    programa, com_programa = os.path.join(cwd, para_conferir[0]), False
                    avisos.append(f"modelo {modelo['nome']}: o programa {para_conferir[0]} não existe aqui "
                                  f"({sys.platform}); ele é conferido no Linux, a cada execução")
                _conferir_preso(raiz_codigo, ref, fora, para_conferir, programa, cwd, perfil["ambiente"], sistema,
                                com_programa=com_programa)
            except Recusa as exc:
                raise Recusa(f"modelo {modelo['nome']}: {exc}") from None
    escondidos = [m[1] for m in achadas]
    return {"valido": True, "sha256": perfil["sha256"], "perfil_id": perfil["perfil_id"], "projeto": perfil["projeto"],
            "tipo": perfil["tipo"], "validade": perfil["validade"], "modelos": perfil["modelos"],
            "montagens": {"so_leitura": leitura, "saida": saida}, "avisos": avisos,
            "mascaras": escondidos, "mascaras_regra": MASCARAS_REGRA, "fora_do_manifesto": fora,
            "para_a_folha": folha_do_perfil(perfil, escondidos, fora)}


def _destino_do_registro(perfil: dict, registro) -> Path:
    pasta = Path(perfil["pasta_projeto"])
    destino = Path(os.path.abspath(registro)) if registro else pasta / "outputs" / "execucao" / "registro.jsonl"
    saida = _no_projeto_do_perfil(str(pasta), perfil["montagens"]["saida"])
    if not _dentro(str(destino), str(pasta)) or destino == pasta:
        raise Recusa(f"o registro {destino} fica fora do projeto ou fora de outputs/")
    rel = destino.relative_to(pasta).as_posix()
    if (not rel.startswith("outputs/") or destino.suffix != ".jsonl"
            or any(p.lower() in FORA_DA_SAIDA for p in rel.split("/")) or _dentro(str(destino), saida)):
        raise Recusa(f"o registro {destino} fica fora do projeto ou fora de outputs/ (precisa ser .jsonl, fora da "
                     "pasta gravável do perfil e fora de pastas reservadas)")
    if GRAVACAO.com_ligacao(pasta, rel):
        raise Recusa(f"o registro {destino} passa por ligação")
    return destino


# Revisão de segurança da 1.7.10, FLUXB-F2: a pasta de saída e o registro ficam na pasta do projeto, que a sessão grava,
# e o rodar pode ser do titular; pelo caminho, uma pasta acima trocada por ligação entre a conferência e a gravação
# levava a linha do registro (ou a pasta nova) para outro projeto. No POSIX, desce-se por descritor, como o Gravador do
# importar.py; no Windows (sem dir_fd, e sem caixa: o rodar não roda lá), pelo caminho conferido do gravacao_segura.py.
_POR_DESCRITOR = (os.name == "posix" and hasattr(os, "O_DIRECTORY") and hasattr(os, "O_NOFOLLOW")
                  and {os.open, os.mkdir} <= os.supports_dir_fd)
_PASTA = os.O_RDONLY | getattr(os, "O_DIRECTORY", 0) | getattr(os, "O_NOFOLLOW", 0) | getattr(os, "O_CLOEXEC", 0)


def _descer(pasta_projeto: str, rel: str) -> int:
    """POSIX: o descritor da pasta `rel` do projeto, aberta parte a parte a partir da pasta do projeto, cada uma com
    O_NOFOLLOW e O_DIRECTORY pelo descritor da de cima, criando a que falta pelo mesmo descritor: uma pasta do caminho
    trocada por ligação, antes ou durante, não é atravessada (GravacaoRecusada)."""
    fd = os.open(pasta_projeto, _PASTA)
    try:
        for parte in [p for p in rel.split("/") if p]:
            try:
                novo = os.open(parte, _PASTA, dir_fd=fd)
            except FileNotFoundError:
                try:
                    os.mkdir(parte, 0o755, dir_fd=fd)
                except FileExistsError:
                    pass
                novo = os.open(parte, _PASTA, dir_fd=fd)
            os.close(fd)
            fd = novo
        return fd
    except BaseException as exc:
        os.close(fd)
        if isinstance(exc, OSError) and not isinstance(exc, GRAVACAO.GravacaoRecusada):
            raise GRAVACAO.GravacaoRecusada(f"{rel} passa por ligação (link simbólico ou junção) ou por algo que não é "
                                            f"pasta ({exc.strerror}): nada foi gravado") from None
        raise


def _criar_pasta(pasta_projeto: str, rel: str) -> None:
    """A pasta `rel` do projeto, criada se falta, sem atravessar ligação (FLUXB-F2)."""
    if _POR_DESCRITOR:
        os.close(_descer(pasta_projeto, rel))
    else:
        GRAVACAO.pasta_sem_ligacao(Path(pasta_projeto), rel)


def _anexar_ao_registro(pasta_projeto: str, destino: Path, dados: bytes) -> None:
    """Acrescenta `dados` ao fim do registro das execuções (FLUXB-F2). POSIX: a pasta dele pelo descritor (`_descer`) e
    o arquivo aberto nela com O_NOFOLLOW e O_NONBLOCK (um FIFO no lugar dele não prende o rodar), conferido arquivo
    comum com um nome só antes de gravar; no Windows, `gravacao_segura.anexar` pelo caminho."""
    mae, _, nome = destino.relative_to(pasta_projeto).as_posix().rpartition("/")
    if not _POR_DESCRITOR:
        GRAVACAO.pasta_sem_ligacao(Path(pasta_projeto), mae)
        GRAVACAO.anexar(destino, dados)
        return
    fd_pasta = _descer(pasta_projeto, mae)
    try:
        try:
            fd = os.open(nome, os.O_WRONLY | os.O_APPEND | os.O_CREAT | os.O_NOFOLLOW | os.O_NONBLOCK | os.O_CLOEXEC,
                         0o666, dir_fd=fd_pasta)
        except OSError as exc:
            raise GRAVACAO.GravacaoRecusada(f"{nome}: é ligação, pasta ou arquivo especial ({exc.strerror}); nada foi "
                                            "gravado nele") from None
        try:
            aberto = os.fstat(fd)
            if not stat.S_ISREG(aberto.st_mode) or aberto.st_nlink != 1:
                raise GRAVACAO.GravacaoRecusada(f"{nome}: não é arquivo comum ou tem vínculo físico; nada foi gravado "
                                                "nele")
            vista = memoryview(dados)
            while vista:
                vista = vista[os.write(fd, vista):]
            os.fsync(fd)
        finally:
            os.close(fd)
    finally:
        os.close(fd_pasta)


def projeto_do_lancador(projeto: str | None) -> str:
    """O projeto em que o `rodar` vale: o do lançador (`FUNDACAO_PROJECT`, posto pelo lançador da sessão, ou
    `FUNDACAO_PROJETO_TRAVADO`, o do porteiro), com que o `--projeto` tem de concordar; sem nenhum deles, o `--projeto`
    é obrigatório (pendência do FLUXOB-B deferida à integração: sem isso, o `rodar` sem `--projeto` aceitava o perfil
    de qualquer projeto da raiz)."""
    definidos = {nome: os.environ[nome].strip() for nome in LANCADOR if os.environ.get(nome, "").strip()}
    if len(set(definidos.values())) > 1:
        raise Recusa("o lançador traz dois projetos diferentes (" + ", ".join(f"{k}={v}" for k, v in definidos.items())
                     + "): nada foi executado")
    if definidos:
        nome, do_lancador = next(iter(definidos.items()))
        if projeto is not None and projeto != do_lancador:
            raise Recusa(f"o projeto do lançador é {do_lancador} ({nome}): --projeto {projeto} não troca de projeto")
        return do_lancador
    if not projeto:
        raise Recusa("informe --projeto <id>: sem FUNDACAO_PROJECT, o rodar não sabe de que projeto é o lançador, e o "
                     "perfil tem de ser desse projeto")
    return projeto


def rodar_perfil(arquivo, sha256_aprovado: str, argv: list[str], *, projeto: str | None = None, registro=None,
                 bwrap: str | None = None, hoje: date | None = None) -> tuple[dict, int]:
    """Uma execução pelo perfil aprovado: confere, roda na caixa, confere de novo e registra. (resultado, código). O
    perfil tem de ser do projeto do lançador (`projeto_do_lancador`)."""
    perfil = ler_perfil(arquivo, sha256_aprovado, projeto=projeto_do_lancador(projeto), hoje=hoje)
    destino = _destino_do_registro(perfil, registro)
    plano = plano_do_perfil(perfil, argv, bwrap=bwrap)
    if not bwrap_monta_por_descritor(plano["bwrap"]):
        raise Recusa("o bubblewrap daqui não monta por descritor (--ro-bind-fd, versão 0.8 ou mais nova; o Ubuntu "
                     "24.04 tem o 0.9): sem isso a sessão poderia trocar uma pasta montada por ligação no meio; nada "
                     "foi executado")
    try:
        conferir_plano_do_perfil(plano, antes=True)
    except Recusa as exc:
        raise Recusa(f"{exc} (antes de rodar)") from None
    descritores = {}
    try:
        for caminho in [*plano["leitura"], plano["gravavel"]["caminho"]]:
            descritores[caminho] = abrir_sem_seguir(perfil["pasta_projeto"], caminho)
        inicio = time.monotonic()
        resultado = _rodar(argv_bwrap_perfil(plano, descritores), None, {}, plano["limites"],
                           pass_fds=tuple(descritores.values()))
        duracao = round(time.monotonic() - inicio, 3)
    finally:
        for fd in descritores.values():
            os.close(fd)
    try:
        conferir_plano_do_perfil(plano, antes=False)
        depois = "ok"
    except Recusa as exc:
        depois = str(exc)
    linha = {"quando": datetime.now(timezone.utc).isoformat(timespec="seconds"), "perfil_id": perfil["perfil_id"],
             "perfil_sha256": perfil["sha256"], "projeto": perfil["projeto"], "modelo": plano["modelo"],
             "argv": plano["comando"], "codigo": resultado["codigo"], "duracao_s": duracao,
             "stdout_sha256": hashlib.sha256(resultado["stdout"]).hexdigest(), "stdout_bytes": len(resultado["stdout"]),
             "stderr_sha256": hashlib.sha256(resultado["stderr"]).hexdigest(), "stderr_bytes": len(resultado["stderr"]),
             "mascaras": len(plano["mascaras"]), "conferencia_depois": depois}
    codigo = 0 if resultado["codigo"] == 0 else 1
    try:  # descendo por descritor, sem atravessar ligação (FLUXB-F2)
        _anexar_ao_registro(perfil["pasta_projeto"], destino,
                            (json.dumps(linha, ensure_ascii=False, sort_keys=True) + "\n").encode("utf-8"))
        registrado = str(destino)
    except OSError as exc:
        registrado, codigo = f"falhou: {exc}", 3
    if depois != "ok":
        codigo = 3
    return {"executado": True, "codigo": resultado["codigo"], "duracao_s": duracao, "perfil_id": perfil["perfil_id"],
            "modelo": plano["modelo"], "comando": plano["comando"], "codigo_executado": plano["codigo_executado"],
            "mascaras": [m[1] for m in plano["mascaras"]], "mascaras_regra": plano["mascaras_regra"],
            "conferencia_depois": depois, "registro": registrado,
            "stdout": resultado["stdout"].decode("utf-8", "replace"),
            "stderr": resultado["stderr"].decode("utf-8", "replace")}, codigo
