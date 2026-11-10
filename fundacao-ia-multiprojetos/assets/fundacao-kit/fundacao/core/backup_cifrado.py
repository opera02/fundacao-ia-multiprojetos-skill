"""Cópia de segurança cifrada (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, lotes 1 e 2 em parte): a pasta de uma cópia
(manifest.json, files/, state/state.sqlite) vira partes de ~1 GiB, cada uma um tar PAX cifrado para a chave PÚBLICA do
titular (cifra_copia.py), mais um manifesto externo em claro SEM nomes de arquivo. Sem senha na criação nem na conferência.

    <destino>/manifesto-cifrado.json  quem confere a âncora: destinatário, SHA-256 e tamanho de cada parte, contagens
    <destino>/parte-001.gpg ...       pastas e arquivos de files/ (um arquivo nunca se divide entre partes)
    <destino>/parte-final.gpg         state/state.sqlite e manifest.json (o manifesto interno de hoje)
    <destino>/LEIA-ME.txt             como restaurar à mão; sem segredo (o hash dele vai no manifesto)

Decifradas e extraídas na ordem, as partes remontam a pasta da cópia (a decifra é de outro lote). A âncora é o SHA-256 do
manifesto externo; a do conteúdo (`sha256_manifesto_interno`) é a do manifest.json de hoje. Cada arquivo é lido preso ao
objeto listado e seu SHA-256 é conferido contra o manifesto da cópia ENQUANTO entra no tar: arquivo trocado, ligação ou
arquivo a mais na pasta recusam a cifra, e nada é promovido. A conferência sem senha (`verificar_cifrada`) vê âncora, tamanho
e SHA-256 de cada parte e o destinatário de cada uma (cabeçalho OpenPGP), sem chamar o gpg; que as partes decifram e que o
conteúdo bate só se vê com a senha (conferir-copia, do titular). Limite: a conferência não prova a origem — quem tem a chave
pública monta outra cópia válida; é a âncora, guardada fora, que prova.
"""

from __future__ import annotations

import hashlib
import io
import json
import os
import re
import stat
import tarfile
from pathlib import Path

from .. import KIT_VERSION
from . import leia_me_cifrada, limpeza, preparo
from .ancora_copia import (_fundacao_viva, anotar_ancora, aviso_da_ancora, conferir_ancora, dentro_da_copia,
                           ler_manifesto)
from .canon import sha256_bytes
from .cifra_copia import PREFIXO, SessaoDeCifra, conferir_cabecalho, ids_do_destinatario
from .contracts import AccessDenied, FundacaoError, ValidationError
from .db import utcnow

SCHEMA = "fundacao.backup_cifrado/1"
FORMATO = "tar-pax+openpgp-seipd"
MANIFESTO, LEIA_ME, PARTE_FINAL = "manifesto-cifrado.json", "LEIA-ME.txt", "parte-final.gpg"
TAMANHO_PARTE = 1 << 30
CONTEUDO_NAO_CONFERIDO = ("conferido na criação; ler o conteúdo exige a senha: conferir-copia na ferramenta do titular")
_NOME = re.compile(r"^parte-(\d{3})\.gpg$")
_HEX64, _FPR = re.compile(r"^[0-9a-f]{64}$"), re.compile(r"^[0-9A-F]{40,64}$")
_DO_SO = ("Thumbs.db", "ehthumbs.db", "desktop.ini", ".DS_Store")  # como backup.METADADOS_DO_SO: nem cifrados nem conferidos
_TAR_POR_ARQUIVO = 1024  # cabeçalho e enchimento do tar, na conta do tamanho da parte


def _lista(origem: Path, manifest: dict) -> tuple[list, list]:
    """(pastas, arquivos) da cópia em `origem`, presos ao `lstat` da listagem; recusa ligação, item a mais, arquivo do
    manifesto ausente ou de tamanho diferente. Arquivo: (nome no tar, caminho, lstat, SHA-256 esperado)."""
    esperado = {f"files/{f['path']}": (f["sha256"], f.get("size")) for f in manifest["files"]}
    if manifest.get("db_sha256"):
        esperado["state/state.sqlite"] = (manifest["db_sha256"], None)
    pastas, arquivos, ruins, vistos = [], [], [], set()
    for caminho, ligacao, st in preparo.percorrer(origem):
        rel = caminho.relative_to(origem).as_posix()
        if ligacao or not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
            ruins.append(rel)
        elif stat.S_ISDIR(st.st_mode):
            if rel in ("files", "state") or rel.startswith("files/"):
                pastas.append(rel)
            else:
                ruins.append(rel)
        elif rel == "manifest.json":
            continue
        elif rel in esperado:
            sha, tamanho = esperado[rel]
            if tamanho is not None and tamanho != st.st_size:
                ruins.append(rel)
            vistos.add(rel)
            arquivos.append((rel, caminho, st, sha))
        elif caminho.name not in _DO_SO:
            ruins.append(rel)
    ruins += [rel for rel in esperado if rel not in vistos]
    if ruins:
        raise ValidationError("a pasta da cópia não é a que o manifesto descreve (ligação, item a mais, ausente ou de "
                              "tamanho diferente): nada foi cifrado", itens=len(ruins), exemplos=sorted(set(ruins))[:5])
    return pastas, arquivos


def _partes(pastas: list, arquivos: list, limite: int) -> list[list]:
    """Grupos de membros: pastas e arquivos de files/ em ordem, uma parte nova quando o próximo estouraria `limite` (arquivo
    maior que o limite fica só); a parte final leva o banco. Membro: (nome, caminho ou None se pasta, lstat, SHA-256)."""
    grupos, atual, soma = [], [(rel, None, None, None) for rel in pastas], 0
    for membro in (m for m in arquivos if m[0] != "state/state.sqlite"):
        custo = membro[2].st_size + _TAR_POR_ARQUIVO
        if atual and soma + custo > limite and any(m[1] for m in atual):
            grupos.append(atual)
            atual, soma = [], 0
        atual.append(membro)
        soma += custo
    grupos.append(atual)
    return grupos


class _Leitura:
    """Arquivo preso ao objeto listado (sem seguir ligação), com o SHA-256 do que foi lido, para o `tarfile`."""

    def __init__(self, caminho: Path, listado: os.stat_result):
        self.fd, _ = preparo._abrir(caminho, listado)
        self.sha, self.lido = hashlib.sha256(), 0

    def read(self, n: int = 1 << 20) -> bytes:
        partes, falta = [], n
        while falta > 0 and (bloco := os.read(self.fd, falta)):
            partes.append(bloco)
            falta -= len(bloco)
        dados = b"".join(partes)
        self.sha.update(dados)
        self.lido += len(dados)
        return dados

    def fechar(self) -> None:
        os.close(self.fd)


def _escrever_parte(sessao: SessaoDeCifra, saida: Path, membros: list, bruto_manifesto: bytes | None) -> dict:
    with sessao.cifrador(saida) as cifrador:
        with tarfile.open(fileobj=cifrador, mode="w|", format=tarfile.PAX_FORMAT) as tar:
            for nome, caminho, st, sha in membros:
                info = tarfile.TarInfo(nome)
                info.mtime = int(st.st_mtime) if st else 0
                if caminho is None:
                    info.type, info.mode = tarfile.DIRTYPE, 0o755
                    tar.addfile(info)
                    continue
                info.size, info.mode = st.st_size, 0o644
                arquivo = _Leitura(caminho, st)
                try:
                    tar.addfile(info, arquivo)
                    if arquivo.lido != st.st_size or arquivo.sha.hexdigest() != sha:
                        raise ValidationError("um arquivo da cópia mudou ou não confere com o manifesto: nada foi cifrado",
                                              caminho=nome)
                finally:
                    arquivo.fechar()
            if bruto_manifesto is not None:
                info = tarfile.TarInfo("manifest.json")
                info.size, info.mode = len(bruto_manifesto), 0o644
                tar.addfile(info, io.BytesIO(bruto_manifesto))
    return {"nome": saida.name, "tamanho": cifrador.tamanho, "sha256": cifrador.sha256,
            "membros": len(membros) + (bruto_manifesto is not None)}


def cifrar_copia(origem, destino, chave_publica, *, label: str | None = None, tamanho_parte: int = TAMANHO_PARTE,
                 livro: Path | None = None, exe: str | None = None, criado_em_livro: str | None = None) -> dict:
    """Cifra a cópia em claro de `origem` para a chave pública em `destino` (pasta nova, promovida inteira). `livro`: se dado,
    a âncora vai nele. Devolve sha256_manifesto (a âncora), sha256_manifesto_interno, destinatário, partes e contagens."""
    origem, destino = Path(os.path.abspath(origem)), Path(os.path.abspath(destino))
    if tamanho_parte < 1 << 12:
        raise ValidationError("tamanho da parte pequeno demais")
    if destino.exists() and any(destino.iterdir()):
        raise FileExistsError("destino de backup não vazio: não substitua uma referência anterior")
    ligada = preparo.ligacao_no_caminho(destino) or preparo.ligacao_no_caminho(origem)
    if ligada:
        raise ValidationError("o caminho da origem ou do destino passa por ligação (link simbólico ou junção): informe o "
                              "caminho real", caminho=ligada)
    if dentro_da_copia(destino, origem):
        raise ValidationError("o destino da cópia cifrada fica dentro da cópia em claro", destino=str(destino))
    bruto = preparo.ler(origem / "manifest.json")  # lido uma vez: o hash dele é a âncora do conteúdo
    manifest = ler_manifesto(bruto)
    pastas, arquivos = _lista(origem, manifest)
    grupos = _partes(pastas, arquivos, tamanho_parte)
    if len(grupos) > 999:
        raise ValidationError("partes demais para o nome parte-NNN.gpg: aumente o tamanho da parte", partes=len(grupos))
    banco = [m for m in arquivos if m[0] == "state/state.sqlite"]
    pasta = preparo.criar_preparo(destino)
    with limpeza.contada(pasta, destino.parent):
        with SessaoDeCifra(chave_publica, exe) as sessao:
            partes = [_escrever_parte(sessao, pasta / f"parte-{n:03d}.gpg", g, None) for n, g in enumerate(grupos, 1)]
            partes.append(_escrever_parte(sessao, pasta / PARTE_FINAL, banco, bruto))
            leia_me = leia_me_cifrada.texto(FORMATO).encode("utf-8")
            externo = {"schema_version": SCHEMA, "label": label or manifest.get("label"), "created_at": utcnow(),
                       "kit_version": KIT_VERSION, "gpg_versao": sessao.gpg["versao"], "formato": FORMATO,
                       "destinatario": sessao.destinatario, "sha256_manifesto_interno": sha256_bytes(bruto),
                       "arquivos": len(manifest["files"]), "bytes": sum(f.get("size") or 0 for f in manifest["files"]),
                       "tamanho_parte": tamanho_parte, "partes": partes,
                       "leia_me": {"tamanho": len(leia_me), "sha256": sha256_bytes(leia_me)}}
            texto = json.dumps(externo, ensure_ascii=False, indent=2).encode("utf-8")
            for nome, dados in ((MANIFESTO, texto), (LEIA_ME, leia_me)):
                with open(pasta / nome, "xb") as arq:
                    arq.write(dados)
        preparo.promover(pasta, destino)
    resultado = {**externo, "cifrada": True, "destino": str(destino), "sha256_manifesto": sha256_bytes(texto)}
    if livro is not None:
        try:  # como no `backup criar`: livro que é ligação ou vínculo físico não derruba a cópia, avisa
            anotar_ancora(livro, {"rotulo": externo["label"], "criado_em": criado_em_livro or externo["created_at"],
                                  "destino": str(destino),
                                  "sha256_manifesto": resultado["sha256_manifesto"], "cifrada": True,
                                  "sha256_manifesto_interno": externo["sha256_manifesto_interno"],
                                  "destinatario": externo["destinatario"]})
        except (OSError, FundacaoError) as exc:
            resultado["avisos"] = [f"a âncora não foi anotada no livro de cópias ({type(exc).__name__}): guarde o "
                                   "sha256_manifesto; a restauração vai pedi-lo"]
    return resultado


def _ler_externo(bruto: bytes) -> dict:
    """Manifesto externo com a estrutura esperada (partes numeradas em ordem e a final por último, hashes e impressões
    digitais no formato); senão, ValidationError."""
    try:
        m = json.loads(bruto.decode("utf-8"))
        partes, d = m["partes"], m["destinatario"]
        nomes = [p["nome"] for p in partes]
        ok = (m["schema_version"] == SCHEMA and isinstance(m["partes"], list) and partes
              and nomes[-1] == PARTE_FINAL and nomes[:-1] == [f"parte-{n:03d}.gpg" for n in range(1, len(nomes))]
              and all(_HEX64.match(p["sha256"]) and isinstance(p["tamanho"], int) and p["tamanho"] > 0 for p in partes)
              and _FPR.match(d["principal"]) and isinstance(d["subchaves_de_cifra"], list) and d["subchaves_de_cifra"]
              and all(_FPR.match(f) for f in d["subchaves_de_cifra"]) and _HEX64.match(m["sha256_manifesto_interno"])
              and (m.get("leia_me") is None or (_HEX64.match(m["leia_me"]["sha256"]) and isinstance(m["leia_me"]["tamanho"], int))))
    except (UnicodeDecodeError, ValueError, KeyError, TypeError, IndexError):
        ok = False
    if not ok:
        raise ValidationError("manifesto da cópia cifrada com estrutura inválida: não é uma cópia cifrada desta fundação")
    return m


def _prefixo(caminho: Path, st: os.stat_result) -> bytes:
    fd, _ = preparo._abrir(caminho, st)
    try:
        return os.read(fd, PREFIXO)
    finally:
        os.close(fd)


def e_cifrada(origem) -> bool:
    """A pasta é uma cópia cifrada (tem o manifesto externo) e não uma cópia comum (sem manifest.json)."""
    origem = Path(origem)
    return os.path.lexists(origem / MANIFESTO) and not os.path.lexists(origem / "manifest.json")


def autorizar_cifrada(raiz, origem) -> dict:
    """Quem pode verificar uma cópia cifrada: a administração da fundação VIVA. O banco da cópia está dentro da cifra, então
    a política da cópia só vale depois de o titular decifrar (decifrar-copia); sem fundação viva, ninguém é autorizado."""
    viva, motivo = _fundacao_viva(Path(raiz), Path(origem))
    if viva is None:
        raise AccessDenied(f"a raiz {Path(raiz).resolve()} não vale como fundação viva ({motivo}) e o banco da cópia "
                           "cifrada só se lê depois de decifrar: rode na pasta da fundação, ou peça ao titular o "
                           "decifrar-copia", action="admin", resource="foundation")
    return {**viva, "raiz": str(Path(raiz).resolve())}


def verificar_cifrada(origem, *, sha256_manifesto: str | None = None, livro: Path | None = None,
                      destinatario_esperado: str | None = None, bruto: bytes | None = None) -> dict:
    """Conferência SEM a senha e sem chamar o gpg: âncora do manifesto externo; cada parte existe, é arquivo comum, tem o
    tamanho e o SHA-256 do manifesto e o cabeçalho de uma cifra para o destinatário anotado; nada a mais na pasta. Com
    `destinatario_esperado` (impressão digital da principal, vinda da âncora protegida), o do manifesto tem de ser ele."""
    origem = Path(origem)
    bruto = preparo.ler(origem / MANIFESTO) if bruto is None else bruto  # `bruto`: os bytes que quem chama já leu
    m = _ler_externo(bruto)
    ancora = conferir_ancora(bruto, sha256_manifesto, livro, origem)
    comuns, ligacoes, extras = {}, [], []
    for caminho, ligacao, st in preparo.percorrer(origem):
        rel = caminho.relative_to(origem).as_posix()
        if ligacao:
            ligacoes.append(rel)
        elif stat.S_ISREG(st.st_mode):
            comuns[rel] = (caminho, st)
        else:
            extras.append(rel)
    itens = [(p["nome"], p["tamanho"], p["sha256"]) for p in m["partes"]]
    if m.get("leia_me"):
        itens.append((LEIA_ME, m["leia_me"]["tamanho"], m["leia_me"]["sha256"]))
    missing, changed, destino_errado, estrutura = [], [], [], []
    ids = ids_do_destinatario(m["destinatario"])
    for nome, tamanho, sha in itens:
        if nome not in comuns:
            missing.append(nome)
            continue
        caminho, st = comuns[nome]
        if st.st_size != tamanho or preparo.resumo(caminho, st) != sha:
            changed.append(nome)
        elif nome != LEIA_ME and (problema := conferir_cabecalho(_prefixo(caminho, st), st.st_size, ids)):
            (destino_errado if problema[0] == "destinatario" else estrutura).append(nome)
    conhecidos = {n for n, _, _ in itens} | {MANIFESTO, LEIA_ME}
    extras += [rel for rel, (c, _) in comuns.items() if rel not in conhecidos and c.name not in _DO_SO]
    divergente = bool(destinatario_esperado) and destinatario_esperado.strip().upper() != m["destinatario"]["principal"]
    resultado = {"ok": not (missing or changed or extras or ligacoes or destino_errado or estrutura or divergente)
                 and ancora["situacao"] != "divergente",
                 "cifrada": True, "conteudo_conferido": False, "conteudo": CONTEUDO_NAO_CONFERIDO,
                 "partes": len(m["partes"]), "destinatario": m["destinatario"], "gpg_versao": m.get("gpg_versao"),
                 "sha256_manifesto_interno": m["sha256_manifesto_interno"], "ancora": ancora,
                 "copia": {"rotulo": m.get("label"), "criada_em": m.get("created_at")}}
    resultado.update({k: v for k, v in (("missing", missing), ("changed", changed), ("extras", sorted(extras)),
                                        ("ligacoes", sorted(ligacoes)), ("destinatario_errado", destino_errado),
                                        ("estrutura_invalida", estrutura)) if v})
    if divergente:
        resultado["destinatario_divergente"] = {"esperado": destinatario_esperado, "no_manifesto": m["destinatario"]["principal"]}
    resultado.update(aviso_da_ancora(ancora))
    return resultado
