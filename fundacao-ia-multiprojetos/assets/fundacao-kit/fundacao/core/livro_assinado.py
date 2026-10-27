"""Âncoras de cópia assinadas pelo titular, com chave fora do executor.

Entradas antigas continuam legíveis; só envelope criptograficamente verificado
vale em ancora_do_livro. O modo legado do backup mantém seu aviso até o titular
adotar --exigir-livro-assinado. Preparar nunca assina nem registra por conta própria.
"""
import base64
import json
import os
import re
import tempfile
from pathlib import Path

from . import decisoes, preparo, publicacao
from .canon import canonical_json, sha256_bytes
from .contracts import ValidationError
from .db import utcnow

SCHEMA = "fundacao.copia_assinada/1"
NAMESPACE = "fundacao-copia"
TETO = 5_000_000
SHA = re.compile(r"[0-9a-f]{64}\Z")


def _ler(path):
    path = Path(path)
    if preparo.ligacao_no_caminho(path):
        raise ValidationError("livro/assinatura com ligação: recusado")
    fd, st = preparo._abrir(path, os.lstat(path))
    try:
        if st.st_nlink != 1 or st.st_size > TETO:
            raise ValidationError("arquivo com vínculo físico ou acima do teto: recusado")
        partes, total = [], 0
        while b := os.read(fd, min(65536, TETO + 1 - total)):
            partes.append(b); total += len(b)
            if total > TETO:
                raise ValidationError("arquivo acima do teto")
        return b"".join(partes)
    finally:
        os.close(fd)


def _json(bruto):
    def objeto(pares):
        res = {}
        for chave, valor in pares:
            if chave in res: raise ValueError("chave duplicada")
            res[chave] = valor
        return res
    try:
        return json.loads(bruto, object_pairs_hook=objeto, parse_constant=lambda _: (_ for _ in ()).throw(ValueError()))
    except (ValueError, TypeError, UnicodeError, RecursionError):
        raise ValidationError("registro de cópia ilegível") from None


def _linhas(livro):
    return [_json(linha) for linha in _ler(livro).splitlines() if linha.strip()]


def _documento(doc):
    if (not isinstance(doc, dict) or set(doc) != {"schema_version", "assinante", "registrado_em", "entrada"}
            or doc["schema_version"] != SCHEMA or not isinstance(doc["assinante"], str)
            or not re.fullmatch(r"[a-z0-9-]{1,40}", doc["assinante"])
            or not isinstance(doc["registrado_em"], str) or not doc["registrado_em"]
            or not isinstance(doc["entrada"], dict)
            or not isinstance(doc["entrada"].get("sha256_manifesto"), str)
            or not SHA.fullmatch(doc["entrada"]["sha256_manifesto"])):
        raise ValidationError("forma do documento de cópia inválida")
    return (canonical_json(doc) + "\n").encode("utf-8")


def preparar(livro, sha, assinante, arquivo):
    entradas = [r for r in _linhas(livro) if isinstance(r, dict) and r.get("sha256_manifesto") == sha]
    if len(entradas) != 1:
        raise ValidationError("a cópia deve ter exatamente uma entrada original no livro")
    doc = {"schema_version": SCHEMA, "assinante": assinante, "registrado_em": utcnow(), "entrada": entradas[0]}
    bruto = _documento(doc)
    arquivo = Path(arquivo)
    if preparo.ligacao_no_caminho(arquivo):
        raise ValidationError("destino da assinatura com ligação")
    arquivo.parent.mkdir(parents=True, exist_ok=True)
    # Exclusivo: nem arquivo existente, nem vínculo físico são sobrescritos.
    with arquivo.open("xb") as f:
        f.write(bruto)
    return {"arquivo": str(arquivo), "sha256_documento": sha256_bytes(bruto), "namespace": NAMESPACE,
            "sha256_manifesto": sha, "assinar": "o titular assina o arquivo com ssh-keygen -Y sign -n fundacao-copia"}


def _verificar(doc, assinatura):
    bruto = _documento(doc)
    if not decisoes.ssh_keygen_do_sistema():
        raise ValidationError("OpenSSH do sistema ausente: nenhum verificador do PATH é aceito")
    ancora = decisoes.ancora_padrao()
    if ancora is None or not decisoes.conferir_ancora(ancora).get("protegida"):
        raise ValidationError("âncora do titular ausente ou não protegida")
    with tempfile.TemporaryDirectory(prefix="fundacao-copia-assinada-") as tmp:
        path = Path(tmp) / "copia.json"
        path.write_bytes(bruto); Path(str(path) + ".sig").write_bytes(assinatura)
        res = decisoes.verificar_assinatura(path, ancora, doc["assinante"], dados=bruto, namespace=NAMESPACE)
    if not res.get("ok") or res.get("ssh_keygen_do_sistema") is not True:
        raise ValidationError("assinatura da cópia não confere")
    return res


def registrar(livro, arquivo):
    bruto = _ler(arquivo)
    doc = _json(bruto)
    if _documento(doc) != bruto:
        raise ValidationError("documento não está na forma canônica preparada")
    try:
        assinatura = _ler(str(arquivo) + ".sig")
    except OSError:
        raise ValidationError("assinatura ausente") from None
    _verificar(doc, assinatura)
    envelope = {"documento": doc, "assinatura_base64": base64.b64encode(assinatura).decode("ascii")}
    linhas = _linhas(livro)
    if envelope in linhas:
        return {"ja_registrada": True, "sha256_manifesto": doc["entrada"]["sha256_manifesto"]}
    if doc["entrada"] not in linhas:
        raise ValidationError("entrada original mudou desde a preparação")
    publicacao.anexar(Path(livro), (canonical_json(envelope) + "\n").encode("utf-8"))
    return {"registrada": True, "sha256_manifesto": doc["entrada"]["sha256_manifesto"]}


def ancora_do_livro(livro, manifesto):
    sha = sha256_bytes(manifesto)
    for rec in _linhas(livro):
        if not isinstance(rec, dict) or set(rec) != {"documento", "assinatura_base64"}:
            continue
        doc = rec["documento"]
        if not isinstance(doc, dict) or not isinstance(doc.get("entrada"), dict) or doc["entrada"].get("sha256_manifesto") != sha:
            continue
        try:
            assinatura = base64.b64decode(rec["assinatura_base64"], validate=True)
            _verificar(doc, assinatura)
        except (ValueError, TypeError, ValidationError):
            continue
        return sha
    raise ValidationError("nenhuma assinatura válida autentica esta cópia; use o hash guardado fora da cópia")
