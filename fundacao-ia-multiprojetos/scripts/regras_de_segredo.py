#!/usr/bin/env python3
"""Regra única de segredo da skill: nomes fortes, nomes fracos e pastas de segredo (1.7.10; DESENHO-1.7.10 §5.1 e
§7.1; MELHORIAS-1.7.10, seção 1, item 10).

Até a 1.7.9, o mesmo critério existia em seis listas divergentes (manifesto, codigo_conferido, matriz, retomada,
sinais_compatibilidade e perfis do host) e olhava só o NOME do arquivo: pastas como `.segredos/` e `.envs/` com
arquivos de nome comum, e nomes como `setup_token`, passavam e eram lidos para o hash. Esta é a fonte única, usada
pelo manifesto, pelo importador (`importar.py`) e pelo conferidor (`segredos.py`); o kit e os perfis do host repetem
as listas (eles não importam scripts da skill) e um teste confere a igualdade com `python regras_de_segredo.py
listas`.

Classes (`classificar`, sobre o caminho RELATIVO, sem ler nada nem tocar no disco):
- 'pasta-de-segredo': algum componente do caminho, inclusive o último, é uma pasta de segredo (`PASTAS_DE_SEGREDO`
  ou as extras do projeto, como `.omniroute`, passadas com `--pasta-segredo`): a pasta inteira fica fora, sem
  listar o que tem dentro;
- 'forte': o nome casa `NOMES_FORTES` (chave, credencial, cofre de senhas): nunca é lido; só entra numa cópia como
  opaco autorizado pelo titular (`importar.py --opaco`);
- 'fraco': o nome (ou o fim do caminho, nos padrões com '/', como `.git/config`) casa `NOMES_FRACOS`: fica fora por
  padrão e é candidato à conferência de conteúdo (`segredos.py conferir`), que pode liberá-lo. Exemplo de segredo
  (`EXEMPLOS_DE_SEGREDO`, como `.env.example`) é fraco mesmo quando um nome forte também casa (`.env.*`);
- None: nada casa.

Falsos positivos conhecidos, de propósito (a regra prefere deixar fora a ler): `*token*` pega `tokenizer.py` e
`tokens.css`, e `*password*` pega `password_reset.py` (fracos: a conferência de conteúdo os libera); `*.example`
pega modelos que não têm segredo; `*secret*` pega `secret_santa.py` e `*credentials*` pega `credentials_test.py`
(fortes, herdados do manifesto até a 1.7.9); `*.key` pega apresentações do Keynote; `id_rsa*` e `id_ed25519*` pegam
a chave pública `.pub`; `.docker/` pega pasta de Dockerfiles. Fica fora, por cautela, e não aparece como lido.

Comparação: texto normalizado (NFKC) e sem caixa (casefold), com `fnmatchcase`, para o resultado não depender do
sistema; a barra invertida conta como separador (mais casos, nunca menos). Só biblioteca padrão.

  python regras_de_segredo.py listas
  python regras_de_segredo.py classificar CAMINHO [CAMINHO ...] [--pasta-segredo NOME ...]
"""

from __future__ import annotations

import argparse
import json
import sys
import unicodedata
from fnmatch import fnmatchcase
from typing import Iterable

ESQUEMA = "fundacao.regras_de_segredo/1"

# Os do manifesto.py até a 1.7.9 (formato 2), mais os da 1.7.10 (chaves SSH de outros tipos, chaves da PuTTY, Java e
# Apple, VPN, arquivos de login de rede e de registros de pacote, Terraform, Kubernetes e conta de serviço).
NOMES_FORTES = (
    ".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "*credentials*", "*secret*", "auth.json",
    "*.kdbx",
    "id_ed25519*", "id_ecdsa*", "id_dsa*", "*.ppk", "*.jks", "*.keystore", "*.p8", "*.ovpn", ".netrc", "_netrc",
    ".npmrc", ".pypirc", ".pgpass", ".htpasswd", "*.tfvars", "*.tfstate*", "kubeconfig*", "service-account*.json",
    ".git-credentials",
)
# Exemplos de segredo: fracos mesmo quando um nome forte casa (`.env.example` casa `.env.*`).
EXEMPLOS_DE_SEGREDO = (".env.example", "*.example", "*.sample")
NOMES_FRACOS = (
    "*token*", "*senha*", "*password*", "*passwd*", "*api_key*", "*apikey*", *EXEMPLOS_DE_SEGREDO,
    ".mcp.json", "settings.local.json", ".git/config",
)
# `_browser_profile` (perfil de navegador copiado, DESENHO §1.3) e `.omniroute` (pasta de credenciais de um dos
# projetos) eram extras só da cópia do kit; entram na regra única para todos (contratos do lote 2 da 1.7.10, §3).
PASTAS_DE_SEGREDO = (
    ".segredos", "segredos", ".secrets", "secrets", ".envs", ".ssh", ".gnupg", ".aws", ".azure", ".kube", ".docker",
    "credentials", "_browser_profile", ".omniroute",
)
CLASSES = ("pasta-de-segredo", "forte", "fraco")
MOTIVOS = {
    "pasta-de-segredo": "pasta de segredo: podada sem ler nem listar o que tem dentro",
    "forte": "nome forte de segredo (chave, credencial ou cofre): não lido",
    "fraco": "nome fraco de segredo: fora por padrão, candidato à conferência de conteúdo (segredos.py conferir)",
}


def normalizar(texto: str) -> str:
    """O texto como a regra o compara: NFKC e sem caixa."""
    return unicodedata.normalize("NFKC", str(texto)).casefold()


def partes_do_caminho(caminho) -> list[str]:
    """Os componentes do caminho relativo, com '/' e '\\' como separadores e sem '' nem '.'."""
    return [p for p in str(caminho).replace("\\", "/").split("/") if p not in ("", ".")]


def validar_pasta_extra(nome: str) -> str:
    """Uma pasta de segredo extra do projeto é UM nome de pasta (sem separador, sem '.' nem '..', sem controle)."""
    texto = str(nome)
    if (not texto.strip() or texto in (".", "..") or "/" in texto or "\\" in texto
            or any(unicodedata.category(c) in ("Cc", "Cf") for c in texto)):
        raise ValueError(f"pasta de segredo extra inválida: {nome!r} (use um nome de pasta, como .omniroute)")
    return texto


def _casa(partes: list[str], padrao: str) -> bool:
    """`padrao` (já normalizado) casa o nome; com '/', casa os últimos componentes do caminho, um a um."""
    if "/" in padrao:
        alvo = [p for p in padrao.split("/") if p]
        return len(partes) >= len(alvo) and all(fnmatchcase(p, a) for p, a in zip(partes[-len(alvo):], alvo))
    return fnmatchcase(partes[-1], padrao)


def e_pasta_de_segredo(nome: str, pastas_extras: Iterable[str] = (), pastas: Iterable[str] = PASTAS_DE_SEGREDO) -> bool:
    """O nome (um componente) é de pasta de segredo: para podar a pasta durante a varredura."""
    return normalizar(nome) in {normalizar(p) for p in (*pastas, *pastas_extras)}


def classificar(caminho_relativo, pastas_extras: Iterable[str] = (), *, fortes: Iterable[str] = NOMES_FORTES,
                fracos: Iterable[str] = NOMES_FRACOS, exemplos: Iterable[str] = EXEMPLOS_DE_SEGREDO,
                pastas: Iterable[str] = PASTAS_DE_SEGREDO) -> str | None:
    """'pasta-de-segredo', 'forte', 'fraco' ou None, nessa precedência (exemplo de segredo antes do forte). As listas
    podem vir de uma política gravada (o manifesto do formato 3 confere com as listas do dia em que foi criado)."""
    partes = [normalizar(p) for p in partes_do_caminho(caminho_relativo)]
    if not partes:
        return None
    nomes_de_pasta = {normalizar(p) for p in (*pastas, *pastas_extras)}
    if any(p in nomes_de_pasta for p in partes):
        return "pasta-de-segredo"
    exemplos = [normalizar(g) for g in exemplos]
    if any(_casa(partes, g) for g in exemplos):
        return "fraco"
    if any(_casa(partes, normalizar(g)) for g in fortes):
        return "forte"
    if any(_casa(partes, normalizar(g)) for g in fracos):
        return "fraco"
    return None


def motivo(classe: str | None) -> str | None:
    return MOTIVOS.get(classe) if classe else None


def listas() -> dict:
    """As listas canônicas, para o kit e os perfis do host repetirem e um teste conferir a igualdade."""
    return {"schema_version": ESQUEMA, "nomes_fortes": list(NOMES_FORTES), "nomes_fracos": list(NOMES_FRACOS),
            "exemplos_de_segredo": list(EXEMPLOS_DE_SEGREDO), "pastas_de_segredo": list(PASTAS_DE_SEGREDO)}


def main(argv: list | None = None) -> int:
    ap = argparse.ArgumentParser(description=__doc__.splitlines()[0])
    sub = ap.add_subparsers(dest="cmd", required=True)
    sub.add_parser("listas", help="as listas canônicas em JSON")
    c = sub.add_parser("classificar", help="a classe de cada caminho relativo (sem tocar no disco)")
    c.add_argument("caminhos", nargs="+")
    c.add_argument("--pasta-segredo", action="append", default=[], help="pasta de segredo extra do projeto")
    args = ap.parse_args(argv)
    if args.cmd == "listas":
        print(json.dumps(listas(), ensure_ascii=False, indent=1))
        return 0
    try:
        extras = [validar_pasta_extra(n) for n in args.pasta_segredo]
    except ValueError as exc:
        print(json.dumps({"erro": str(exc)}, ensure_ascii=False), file=sys.stderr)
        return 2
    print(json.dumps({c: classificar(c, extras) for c in args.caminhos}, ensure_ascii=False, indent=1))
    return 0


if __name__ == "__main__":
    for _s in (sys.stdout, sys.stderr):
        try:
            _s.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    raise SystemExit(main())
