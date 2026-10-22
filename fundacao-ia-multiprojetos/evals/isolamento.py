#!/usr/bin/env python3
r"""Bancada do avaliador × área do executor nas avaliações com subagentes (apoio de preparar_avaliacoes.py).

[Decisão; harness2, P2] Método adaptado de Harness² (arXiv:2610.14224, github.com/google-research/harness2,
commit 1cfe254, Apache-2.0); texto e código próprios. Quem é avaliado não alcança o gabarito nem deduz, pelo
caminho, o caso ou o braço:
- a bancada (formato do skill-creator: eval_metadata.json, prompts.json, _referencias/, notas) e a área do
  executor (`<área>/<id>/ambiente`, com `<id>` neutro tirado de uma semente) são raízes separadas;
- a skill entregue ao executor é uma cópia sem `evals/`, com a exclusão do pacote instalável, e a cópia nunca
  segue ligação;
- `conferir_isolamento` é o alarme antes de entregar os pedidos: acusa nome do gabarito, de caso ou de braço na
  área, frase de expectativa (30 caracteres ou mais, comparação literal depois de normalizar) no ambiente e nas
  saídas, palavra de medição no pedido resolvido, caminho fora da pasta da própria execução e a área perto do
  gabarito (`conferir_vizinhanca`). Se disparar, procure o caminho que vazou em vez de ampliar a lista. A cópia da
  skill pode repetir o comportamento esperado (é o que ela ensina): `repeticoes_na_skill` lista esses trechos como
  informação para o papel treino × teste do P4.
- Revisão de segurança da 1.7.7 (R177-VAL-06): a área padrão (`area_padrao`) fica na pasta temporária do sistema,
  fora do repositório e do pai do workspace (no padrão do skill-creator, o workspace fica ao lado da skill, e a
  área antiga caía ao lado de `evals/`); `conferir_vizinhanca` recusa a área (ou a pasta cega do `cegar.py`) dentro
  de uma zona do gabarito, com uma raiz do gabarito dentro dela ou com nome do gabarito ao lado das pastas acima —
  o repositório, de nome qualquer, conta como nome do gabarito ao lado (segunda passada da revisão).
- Terceira passada da revisão (R177C-B-08): os caminhos eram comparados pelo texto depois do `resolve()`, que mantém
  o prefixo de dispositivo do Windows (`\\?\`): a área escrita com ele ao lado do repositório, dentro dele ou na
  bancada passava. Agora a comparação (`resolvido`, `mesmo_lugar`, `dentro`) tira o prefixo e, nas pastas que
  existem, confere a identidade no sistema de arquivos (pega `\\localhost\C$\...` e outros nomes do mesmo lugar).
- Terceira passada da revisão (R177C-B-07): a fixture vai para o ambiente por `copiar_fixture`, que copia o que a
  identidade do preparo descreve (tudo) e recusa ligação; o `copytree` seguia a junção e levava o outro lado.
[Decisão; harness2, P4] `impressao_do_ambiente` compara os ambientes dos braços: só a skill pode diferir.
"""
from __future__ import annotations

import hashlib
import json
import os
import re
import secrets
import shutil
import sqlite3
import stat
import subprocess
import sys
import tempfile
import unicodedata
from pathlib import Path

SKILL = Path(__file__).resolve().parents[1]
# Arquivos e pastas da bancada (e a pasta evals/ da skill): nenhum deles pode aparecer na área do executor.
NOMES_DO_GABARITO = frozenset({"eval_metadata.json", "evals.json", "trigger-evals.json", "prompts.json",
                               "grading.json", "_referencias", "isolamento.json", "benchmark.json", "timing.json",
                               "evals"})
BRACOS_FIXOS = ("with_skill", "without_skill")
# O pedido descreve o trabalho, não a medição: estas marcas (sem acento e sem caixa) não podem aparecer nele.
MARCAS_DE_MEDICAO = ("eval-", "evals", "with_skill", "without_skill", "iteration-", "_referencias", "gabarito",
                     "avaliac", "benchmark", "rubrica", "grading")
MIN_FRASE = 30
EXCLUIR_PASTAS = frozenset({"__pycache__", "node_modules"})  # as do pacote instalável (package_skill)
EXCLUIR_ARQUIVOS = frozenset({".DS_Store"})
TEXTO = {".md", ".txt", ".json", ".jsonl", ".py", ".csv", ".yaml", ".yml", ".toml", ".html", ".log", ".sql",
         ".ps1", ".sh", ""}
# Windows: etiqueta "substituta de nome" (bit 29) — junção, link simbólico e afins (como scripts/manifesto.py).
SUBSTITUTA_DE_NOME = 0x20000000


def e_ligacao(caminho: Path) -> bool:
    """Link simbólico ou junção, conferido sem seguir a ligação."""
    try:
        st = os.lstat(caminho)
    except OSError:
        return False
    return stat.S_ISLNK(st.st_mode) or bool(getattr(st, "st_reparse_tag", 0) & SUBSTITUTA_DE_NOME)


def percorrer(base: Path) -> list[tuple[Path, bool]]:
    """(caminho, é_ligação) de tudo sob `base`, em ordem, sem atravessar ligação: a ligação vem marcada e o que
    há do outro lado não é listado."""
    itens = []
    for pasta, subpastas, nomes in os.walk(base):
        atual = Path(pasta)
        for nome in list(subpastas):
            ligacao = e_ligacao(atual / nome)
            if ligacao:
                subpastas.remove(nome)
            itens.append((atual / nome, ligacao))
        itens.extend((atual / nome, e_ligacao(atual / nome)) for nome in nomes)
    return sorted(itens)


def id_neutro(semente: str, avaliacao: int, braco: str, execucao: int) -> str:
    """Id da pasta do executor: não leva "eval", o braço nem o nome do caso; estável com a mesma semente."""
    return hashlib.sha256(f"{semente}|{avaliacao}|{braco}|{execucao}".encode("utf-8")).hexdigest()[:10]


def copiar_skill(origem: Path, destino: Path) -> None:
    """Cópia da skill para o executor: sem `evals/` na raiz, sem bytecode, `node_modules` nem `.DS_Store` (a
    exclusão do pacote instalável). Ligação recusa a cópia: seguida, levaria o conteúdo de fora da árvore."""
    origem = Path(origem)
    ligacoes = [p.relative_to(origem).as_posix() for p, lig in percorrer(origem) if lig]
    if e_ligacao(origem) or ligacoes:
        raise RuntimeError(f"ligação na skill a copiar ({', '.join(ligacoes[:5]) or origem.name}): use arquivos comuns")
    for caminho, _ in percorrer(origem):
        rel = caminho.relative_to(origem)
        if rel.parts[0] == "evals" or EXCLUIR_PASTAS & set(rel.parts) or caminho.name in EXCLUIR_ARQUIVOS \
                or caminho.suffix == ".pyc":
            continue
        alvo = Path(destino) / rel
        if caminho.is_dir():
            alvo.mkdir(parents=True, exist_ok=True)
        else:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(caminho, alvo)


def copiar_fixture(origem: Path, destino: Path) -> None:
    """Cópia de uma fixture de evals/fixtures/ para o ambiente: cada pasta e cada arquivo, sem exclusão, que é o que
    a identidade do preparo descreve (livro_avaliacoes.identidade_das_fixtures). Ligação recusa a cópia: seguida,
    levaria o conteúdo do outro lado (terceira passada da revisão de segurança da 1.7.7, R177C-B-07)."""
    origem, destino = Path(origem), Path(destino)
    itens = percorrer(origem)
    ligacoes = [p.relative_to(origem).as_posix() for p, lig in itens if lig]
    if e_ligacao(origem) or ligacoes:
        raise RuntimeError(f"ligação na fixture a copiar ({', '.join(ligacoes[:5]) or origem.name}): use arquivos "
                           "comuns")
    destino.mkdir(parents=True)  # como o copytree: o destino é novo
    for caminho, _ in itens:
        alvo = destino / caminho.relative_to(origem)
        if caminho.is_dir():
            alvo.mkdir(parents=True, exist_ok=True)
        else:
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(caminho, alvo)


def copiar_arquivos(origem: Path, destino: Path) -> list[str]:
    """Copia só arquivos comuns (recolher as saídas do executor, montar a pasta cega). Ligação não é seguida nem
    copiada: um atalho plantado para fora da área fica de fora e vai na lista devolvida."""
    ignorados: list[str] = []
    if not Path(origem).is_dir() or e_ligacao(origem):
        return ignorados
    for caminho, ligacao in percorrer(origem):
        rel = caminho.relative_to(origem)
        if ligacao:
            ignorados.append(rel.as_posix())
        elif caminho.is_file():
            alvo = Path(destino) / rel
            alvo.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy2(caminho, alvo)
    return ignorados


def normalizar(texto: str) -> str:
    """Forma de comparação: sem acentos, sem caixa e com os espaços colapsados."""
    sem_acento = "".join(c for c in unicodedata.normalize("NFKD", texto) if not unicodedata.combining(c))
    return " ".join(sem_acento.casefold().split())


def frases_por_avaliacao(evals: list[dict]) -> dict[str, set[int]]:
    """Cada expectativa inteira e cada trecho dela entre ':' ';' '(' ')' com 30 caracteres ou mais, normalizados,
    com as avaliações de onde vêm."""
    frases: dict[str, set[int]] = {}
    for ev in evals:
        for exp in ev.get("expectations", []):
            for trecho in (exp, *re.split(r"[:;()]", exp)):
                t = normalizar(trecho).strip(" .,")
                if len(t) >= MIN_FRASE:
                    frases.setdefault(t, set()).add(ev["id"])
    return frases


def frases_de_expectativa(evals: list[dict]) -> set[str]:
    return set(frases_por_avaliacao(evals))


def repeticoes_na_skill(pasta: Path, evals: list[dict]) -> list[dict]:
    """Trechos das expectativas que a própria skill repete. Não é vazamento da bancada — a skill ensina o
    comportamento esperado —, mas mostra que o caso serviu para escrever o texto (papel "treino" no P4)."""
    frases = frases_por_avaliacao(evals)
    achados = []
    for caminho, ligacao in percorrer(pasta):
        rel = caminho.relative_to(pasta)
        if ligacao or not caminho.is_file() or rel.parts[0] == "evals" or caminho.suffix.lower() not in TEXTO:
            continue
        texto = normalizar(caminho.read_text(encoding="utf-8", errors="replace"))
        achados += [{"arquivo": rel.as_posix(), "avaliacoes": sorted(ids), "trecho": frase[:80]}
                    for frase, ids in sorted(frases.items()) if frase in texto]
    return achados


def _nome_proibido(parte: str, casos: list[str]) -> bool:
    n = parte.casefold()
    return (n in NOMES_DO_GABARITO or any(c in n for c in casos) or any(b in n for b in BRACOS_FIXOS)
            or re.match(r"eval-\d", n) is not None)


# --------------------------------------------------------------- caminhos comparáveis (R177C-B-08)
# Prefixo de dispositivo do Windows antes de uma letra de unidade (`\\?\E:\`, `\\.\E:\`) ou de um caminho de rede
# (`\\?\UNC\servidor\`): o Path.resolve() o mantém quando ele já vem no caminho.
_PREFIXO_DE_DISPOSITIVO = re.compile(r"^[\\/]{2}[?.][\\/](?:(?P<unc>UNC[\\/])|(?=[A-Za-z]:))", re.IGNORECASE)


def resolvido(caminho) -> Path:
    r"""`Path.resolve()` sem o prefixo de dispositivo do Windows: `\\?\E:\x` vira `E:\x` e `\\?\UNC\s\c\x` vira
    `\\s\c\x`. Com o prefixo, a comparação pelo texto (`is_relative_to`, `==`) tratava o mesmo lugar como outro
    (terceira passada da revisão de segurança da 1.7.7, R177C-B-08)."""
    texto = str(Path(caminho).resolve())
    m = _PREFIXO_DE_DISPOSITIVO.match(texto) if os.name == "nt" else None
    return Path(("\\\\" if m.group("unc") else "") + texto[m.end():]) if m else Path(texto)


def _identidade(caminho: Path) -> tuple[int, int] | None:
    """(volume, número do arquivo) do que existe em `caminho`; None se não existe ou se o sistema de arquivos não
    dá o número (0: nada a comparar)."""
    try:
        st = os.stat(caminho)
    except (OSError, ValueError):
        return None
    return (st.st_dev, st.st_ino) if st.st_ino else None


def _endereco(caminho: Path) -> tuple[tuple[int, int] | None, tuple[str, ...]]:
    """(identidade da pasta mais funda de `caminho` que existe, nomes abaixo dela; no Windows, sem caixa): dois nomes
    do mesmo lugar dão o mesmo endereço, exista ele ou não. `caminho` já vem de `resolvido`."""
    abaixo = []
    for pasta in (caminho, *caminho.parents):
        ident = _identidade(pasta)
        if ident is not None:
            return ident, tuple(os.path.normcase(nome) for nome in reversed(abaixo))
        abaixo.append(pasta.name)
    return None, ()


def mesmo_lugar(a, b) -> bool:
    r"""`a` e `b` são o mesmo lugar: pela forma de `resolvido` (no Windows, sem caixa) ou pelo endereço a partir da
    identidade no sistema de arquivos, que pega outros nomes do mesmo lugar (`\\localhost\C$\...`, unidade mapeada)
    [R177C-B-08]."""
    a, b = resolvido(a), resolvido(b)
    if a == b:
        return True
    endereco = _endereco(a)
    return endereco[0] is not None and endereco == _endereco(b)


def dentro(alvo, zona) -> bool:
    """`alvo` é `zona` ou fica abaixo dela, qualquer que seja o nome usado para os dois: pela forma de `resolvido` ou
    pela identidade no sistema de arquivos — da zona que existe, numa pasta de `alvo` para cima; da que ainda não
    existe, pela mesma pasta existente e os nomes abaixo dela [R177C-B-08]."""
    a, z = resolvido(alvo), resolvido(zona)
    if a.is_relative_to(z):
        return True
    (ident_z, abaixo_z), (ident_a, abaixo_a) = _endereco(z), _endereco(a)
    if ident_z is None or ident_a is None:
        return False
    if abaixo_z:
        return ident_a == ident_z and abaixo_a[:len(abaixo_z)] == abaixo_z
    return any(_identidade(p) == ident_z for p in (a, *a.parents))


# --------------------------------------------------------------- vizinhança do gabarito (R177-VAL-06)
VIZINHO_DO_GABARITO = re.compile(r"iteration-\d+|eval-\d+(?:-.*)?|.+-workspace")
NIVEIS_ACIMA = 3  # pastas acima conferidas pelo que têm ao lado (o que `ls ..` a `ls ../../..` mostram)


def area_padrao() -> Path:
    """Área do executor padrão: pasta de nome neutro e aleatório na pasta temporária do sistema."""
    return resolvido(tempfile.gettempdir()) / f"trabalho-{secrets.token_hex(4)}"


def raizes_do_gabarito(bancada: Path, fontes=()) -> list[Path]:
    """A bancada, a árvore desta skill (com evals/), o repositório dela (pasta com `.git` ou `entrega/`) e as
    `fontes` (as skills dos braços e o livro-caixa), sem repetir, na forma de `resolvido`."""
    skill = resolvido(SKILL)
    raizes = [resolvido(bancada), skill]
    if (skill.parent / ".git").exists() or (skill.parent / "entrega").is_dir():
        raizes.append(skill.parent)
    raizes += [resolvido(f) for f in fontes if f]
    return list(dict.fromkeys(raizes))


def conferir_vizinhanca(alvo: Path, bancada: Path, fontes=(), papel: str = "a área do executor") -> list[str]:
    r"""Problemas de `alvo` (a área do executor ou a pasta cega) perto do gabarito (lista vazia = nada achado): dentro
    de uma raiz do gabarito ou da pasta-mãe de uma delas (menos a do repositório), dentro do workspace ou do pai
    dele, com uma raiz dentro dele ou com nome do gabarito ao lado de uma das `NIVEIS_ACIMA` pastas acima. Raiz do
    disco não conta como zona. A mãe do repositório não é zona inteira (pode ser a pasta do usuário, que no
    Windows contém a pasta temporária da área padrão): o repositório, de nome qualquer, conta como nome do gabarito
    ao lado (segunda passada da revisão de segurança da 1.7.7, limite do R177-VAL-06). Os caminhos são comparados
    por `dentro` e `mesmo_lugar`: com o prefixo `\\?\` (ou por outro nome do mesmo lugar), a área ao lado do
    repositório, dentro dele ou na bancada passava (terceira passada, R177C-B-08)."""
    a, b = resolvido(alvo), resolvido(bancada)
    raizes = raizes_do_gabarito(b, fontes)
    repositorio = resolvido(SKILL).parent
    repositorio = repositorio if repositorio in raizes else None
    zonas = {b.parent, b.parent.parent} | {r for r in raizes} | {r.parent for r in raizes if r != repositorio}
    problemas = [f"{papel} fica dentro de {z} (perto do gabarito)" for z in sorted(zonas)
                 if z != Path(z.anchor) and dentro(a, z)]
    problemas += [f"{papel} contém {r} (gabarito)" for r in raizes if dentro(r, a)]
    for acima in list(a.parents)[:NIVEIS_ACIMA]:
        try:
            nomes = sorted(e.name for e in os.scandir(acima))
        except OSError:
            nomes = []  # o repositório ao lado conta mesmo sem listar a pasta
        ao_lado = repositorio is not None and mesmo_lugar(repositorio.parent, acima)
        perto = [f"{repositorio.name} (o repositório)"] if ao_lado else []
        perto += [n for n in nomes if n.casefold() in NOMES_DO_GABARITO or VIZINHO_DO_GABARITO.fullmatch(n.casefold())]
        if perto:
            problemas.append(f"{acima}, acima de {papel}, tem ao lado nomes do gabarito: {', '.join(perto[:5])}")
    return problemas


def conferir_isolamento(bancada: Path, area: Path, pedidos: dict, evals: list[dict], bracos=(), fontes=()) -> list[str]:
    """Alarme antes de entregar os pedidos (lista vazia = nada achado). `pedidos`: as entradas do prompts.json
    (id, prompt, ambiente, outputs, skill); `bracos`: os nomes dos braços da rodada (inclusive variantes); `fontes`:
    as skills dos braços e o livro (raízes do gabarito além da bancada e desta skill). A frase de expectativa é
    procurada no ambiente e nas saídas; a cópia da skill (`<área>/<id>/skill/`) entra no exame de nomes, não no de
    frases (ela pode repetir o comportamento esperado — ver `repeticoes_na_skill`)."""
    a = resolvido(area)
    problemas: list[str] = conferir_vizinhanca(a, bancada, fontes)
    casos = sorted({ev["name"].casefold() for ev in evals})
    frases = sorted(frases_de_expectativa(evals))
    for caminho, ligacao in (percorrer(a) if a.is_dir() else []):
        rel = caminho.relative_to(a)
        if ligacao:
            problemas.append(f"ligação na área do executor: {rel.as_posix()}")
        elif any(_nome_proibido(parte, casos) for parte in rel.parts):
            problemas.append(f"nome do gabarito, de caso ou de braço na área do executor: {rel.as_posix()}")
        elif caminho.is_file() and caminho.suffix.lower() in TEXTO and caminho.stat().st_size < 5_000_000 \
                and rel.parts[1:2] != ("skill",):  # <área>/<id>/skill/: a cópia da skill (só o exame de nomes)
            texto = normalizar(caminho.read_text(encoding="utf-8", errors="replace"))
            achada = next((f for f in frases if f in texto), None)
            if achada:
                problemas.append(f"frase de expectativa na área do executor: {rel.as_posix()} ({achada[:60]}...)")
    nomes_bracos = {x.casefold() for x in (*BRACOS_FIXOS, *bracos)}
    for pedido in pedidos.values():
        ident = pedido.get("id", "?")
        texto = normalizar(pedido.get("prompt", ""))
        caminhos = [pedido[k] for k in ("ambiente", "outputs", "skill") if pedido.get(k)]
        partes = {parte.casefold() for c in caminhos for parte in Path(c).parts}
        marcas = [m for m in (*MARCAS_DE_MEDICAO, *casos) if m in texto] + sorted(nomes_bracos & partes)
        if marcas:
            problemas.append(f"pedido {ident}: o texto ou o caminho entregue revela a medição ({', '.join(marcas)})")
        propria = a / str(ident)  # cada execução só recebe caminhos da própria pasta, nunca os de outra
        problemas += [f"pedido {ident}: caminho fora da pasta da própria execução na área do executor: {c}"
                      for c in caminhos if not dentro(c, propria)]
    return problemas


# --------------------------------------------------------------- braços idênticos salvo a skill (P4)
_INSTANTE = re.compile(r"\d{4}-\d{2}-\d{2}[T ]\d{2}:\d{2}:\d{2}(?:\.\d+)?(?:Z|[+-]\d{2}:?\d{2})?")
_EPOCA = re.compile(r"(?<![\w.])1[5-9]\d{8}(?:\d{3})?(?:\.\d+)?(?!\w)")  # segundos ou ms desde 1970 (2017-2033)
_UUID = re.compile(r"[0-9a-fA-F]{8}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{4}-[0-9a-fA-F]{12}")
_HEX = re.compile(r"(?<![0-9a-fA-F])[0-9a-fA-F]{32,}(?![0-9a-fA-F])")


def _sem_volateis(texto: str, execucao: Path) -> str:
    """Tira o que é próprio de cada preparação: o caminho da própria execução (nas formas nativa, com '/' e com
    barra escapada em JSON), instantes (data e hora ou época), ids no formato UUID e hashes."""
    bruto = str(execucao)
    formas = {bruto, execucao.as_posix(), json.dumps(bruto)[1:-1], json.dumps(bruto, ensure_ascii=False)[1:-1]}
    for forma in sorted(formas, key=len, reverse=True):
        texto = texto.replace(forma, "<execucao>")
    texto = _HEX.sub("<hash>", _UUID.sub("<id>", _INSTANTE.sub("<instante>", texto)))
    return _EPOCA.sub("<instante>", texto)  # depois dos hashes: um hash não perde os dígitos do fim


def _conteudo_sqlite(arquivo: Path, execucao: Path) -> str:
    """Tabelas e linhas do banco, sem os voláteis e sem ordem, lidas numa cópia (o ambiente não é tocado)."""
    with tempfile.TemporaryDirectory(prefix="impressao-") as td:
        copia = Path(td) / "copia.sqlite"
        shutil.copy2(arquivo, copia)
        if Path(f"{arquivo}-wal").is_file():
            shutil.copy2(f"{arquivo}-wal", f"{copia}-wal")
        con = sqlite3.connect(str(copia))
        try:
            partes = []
            for (tabela,) in con.execute("SELECT name FROM sqlite_master WHERE type = 'table' ORDER BY name"):
                linhas = sorted(_sem_volateis(json.dumps(list(linha), ensure_ascii=False, default=str), execucao)
                                for linha in con.execute(f'SELECT * FROM "{tabela}"'))
                partes.append(json.dumps([tabela, linhas], ensure_ascii=False))
        finally:
            con.close()
    return "\n".join(partes)


def impressao_do_ambiente(amb: Path, execucao: Path) -> dict[str, str]:
    """{caminho relativo sem os voláteis: hashes do conteúdo sem os voláteis} de cada arquivo do ambiente (o id de
    uma execução do kit também aparece em nomes de pasta); `-wal`/`-shm` entram pelo banco. Dois braços da mesma
    avaliação e execução têm de dar a mesma impressão."""
    impressao: dict[str, list[str]] = {}
    for caminho, ligacao in percorrer(amb):
        rel = _sem_volateis(caminho.relative_to(amb).as_posix(), execucao)
        if ligacao:
            impressao.setdefault(rel, []).append("ligação")
            continue
        if not caminho.is_file() or caminho.name.endswith(("-wal", "-shm", "-journal")) \
                or "__pycache__" in caminho.parts:
            continue
        dados = caminho.read_bytes()
        if dados.startswith(b"SQLite format 3\x00"):
            conteudo = _conteudo_sqlite(caminho, execucao).encode("utf-8")
        else:
            try:
                conteudo = _sem_volateis(dados.decode("utf-8"), execucao).encode("utf-8")
            except UnicodeDecodeError:
                conteudo = dados
        impressao.setdefault(rel, []).append(hashlib.sha256(conteudo).hexdigest())
    return {rel: ",".join(sorted(hashes)) for rel, hashes in impressao.items()}


# --------------------------------------------------------------- identidade da skill (P1 e P4)
def manifesto_da_skill(pasta: Path) -> dict[str, str]:
    """{caminho: sha256} da skill sem `evals/`, em texto canônico (LF e NFC), por scripts/manifesto.py. Arquivo
    que o manifesto não leria (ligação, nome de segredo) recusa: o hash não descreveria a skill inteira."""
    with tempfile.TemporaryDirectory(prefix="manifesto-skill-") as td:
        saida = Path(td) / "manifesto.json"
        r = subprocess.run([sys.executable, "-B", str(SKILL / "scripts" / "manifesto.py"), "criar", "--raiz",
                            str(pasta), "--saida", str(saida), "--texto-canonico", "--excluir", "evals/*"],
                           capture_output=True, text=True, encoding="utf-8", errors="replace", timeout=300)
        if r.returncode != 0 or not saida.is_file():
            raise RuntimeError(f"manifesto da skill em {pasta} falhou: {(r.stderr or r.stdout)[-300:]}")
        dados = json.loads(saida.read_text(encoding="utf-8"))
    fora = [e["path"] for e in dados.get("excluidos", []) if not e["path"].startswith("evals/")]
    if fora:
        raise RuntimeError(f"a skill em {pasta} tem arquivos que o manifesto não lê: {', '.join(fora[:5])}")
    return {f["path"]: f["sha256"] for f in dados["arquivos"]}


def hash_da_skill(manifesto: dict[str, str]) -> str:
    return hashlib.sha256(json.dumps(sorted(manifesto.items()), separators=(",", ":")).encode("utf-8")).hexdigest()
