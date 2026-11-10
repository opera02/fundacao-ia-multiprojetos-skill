#!/usr/bin/env python3
"""Monta o plugin `codigo-enxuto` da skill como candidato de um projeto, pelo fluxo que já existe.

  python plugin_codigo_enxuto.py montar --raiz R --projeto P [--plugin codigo-enxuto]

[Decisão; ponytail, P2 — as skills do plugin vêm de textos do ponytail (MIT; AVISOS-DE-TERCEIROS.md).] No pacote da
skill, as quatro skills do plugin se chamam `SKILL.modelo.md` (`assets/plugins/codigo-enxuto/skills/<nome>/`): o pacote
tem um único `SKILL.md` (a verificação "um único SKILL.md no pacote" do CEN-11, que também protege o envio do zip ao
claude.ai), e o Markdown entra na varredura de injeção como qualquer outro. Este script é o jeito único de levar o plugin
a um projeto: copia as skills, com o nome `SKILL.md`, e o `LICENSE` para uma pasta de origem nova em
`projects/<P>/outputs/plugins/codigo-enxuto/origem/`, chama o `montar` do `plugin_candidato.py` sobre ela (que confere
tudo e grava `projects/<P>/plugins-candidatos/<P>-codigo-enxuto/`) e apaga a origem. O `conferir` não muda: o candidato
montado passa por ele como qualquer outro (revisão, ficha assinada e canário seguem iguais).

Fronteiras: só lê o pacote da skill e só grava dentro de `projects/<P>/`; nada de rede nem de processo. A lista de
arquivos é fixa (`ARQUIVOS`): a pasta do plugin no pacote com um arquivo fora da lista, uma ligação ou um nome fora do
esperado recusa antes de gravar. Cada cópia usa a leitura que não segue ligação nem vínculo físico (`copia_segura`); o
caminho até a origem não pode passar por ligação (`gravacao_segura`); uma origem que já existe recusa; na sessão de um
projeto (FUNDACAO_PROJECT), outro projeto ou outra raiz recusam. Só o plugin `codigo-enxuto` existe (`--plugin`).
Saída JSON, a do `montar` do plugin_candidato. Códigos: 0 feito; 2 recusado (com cada motivo) ou uso incorreto.
"""

from __future__ import annotations

import argparse
import importlib.util
import json
import os
import stat
import sys
from pathlib import Path

AQUI = Path(__file__).resolve().parent
FONTE = AQUI.parent / "assets" / "plugins" / "codigo-enxuto"
PLUGINS = ("codigo-enxuto",)
SKILLS = ("enxuto", "enxuto-auditoria", "enxuto-dividas", "enxuto-revisao")
# {arquivo no pacote: arquivo na origem}. O plugin.json do pacote é do conferir direto; o montar gera o do projeto.
ARQUIVOS = {**{f"skills/{n}/SKILL.modelo.md": f"skills/{n}/SKILL.md" for n in SKILLS}, "LICENSE": "LICENSE"}
NO_PACOTE = frozenset({*ARQUIVOS, ".claude-plugin/plugin.json"})


def _carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_plugin_codigo_enxuto_{nome}", AQUI / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


PC = _carregar("plugin_candidato")
COPIA, GRAVACAO = PC.COPIA, PC.GRAVACAO


def conferir_fonte(fonte: Path) -> None:
    """A pasta do plugin no pacote tem exatamente os arquivos da lista (e o plugin.json), sem ligação nem nome a mais."""
    achados, pendentes = set(), [(fonte, "")]
    while pendentes:
        pasta, rel = pendentes.pop()
        try:
            with os.scandir(pasta) as it:
                entradas = list(it)
        except OSError as exc:
            raise PC.CandidatoRecusado(f"{pasta}: não deu para listar o plugin do pacote ({exc.strerror or exc})") from None
        for entrada in entradas:
            caminho = f"{rel}{entrada.name}"
            st = entrada.stat(follow_symlinks=False)
            if COPIA.e_ligacao(st):
                raise PC.CandidatoRecusado(f"{caminho}: ligação no plugin do pacote")
            if stat.S_ISDIR(st.st_mode):
                pendentes.append((Path(entrada.path), caminho + "/"))
            elif stat.S_ISREG(st.st_mode):
                achados.add(caminho)
            else:
                raise PC.CandidatoRecusado(f"{caminho}: não é arquivo comum no plugin do pacote")
    if achados != NO_PACOTE:
        raise PC.CandidatoRecusado([f"{c}: fora da lista do plugin do pacote" for c in sorted(achados - NO_PACOTE)]
                                   + [f"{c}: falta no plugin do pacote" for c in sorted(NO_PACOTE - achados)])


def montar(raiz, projeto: str, plugin: str = "codigo-enxuto", fonte: Path = FONTE) -> dict:
    """Prepara a origem em `projects/<projeto>/outputs/plugins/<plugin>/origem/`, monta o candidato e apaga a origem."""
    if plugin not in PLUGINS:
        raise PC.CandidatoRecusado(f"--plugin {plugin!r}: só {', '.join(PLUGINS)}")
    if not isinstance(projeto, str) or not PC.ID_PROJETO.fullmatch(projeto):
        raise PC.CandidatoRecusado(f"projeto {projeto!r}: identificador inválido (minúsculas, números e hífen)")
    raiz = Path(os.path.abspath(raiz))
    PC._sessao(projeto, raiz)
    conferir_fonte(fonte)
    rel = f"projects/{projeto}/outputs/plugins/{plugin}/origem"
    if GRAVACAO.com_ligacao(raiz, rel):
        raise PC.CandidatoRecusado(f"{rel}: o caminho passa por ligação (link simbólico ou junção)")
    if not (raiz / "projects" / projeto).is_dir():
        raise PC.CandidatoRecusado(f"{raiz / 'projects' / projeto}: o projeto não existe")
    try:
        origem = GRAVACAO.pasta_nova(raiz, rel)  # recusa se já existir: uma origem antiga não é aproveitada
    except OSError as exc:
        raise PC.CandidatoRecusado(f"{rel}: não deu para criar a origem nova ({exc.strerror or exc})") from None
    try:
        for do_pacote, na_origem in ARQUIVOS.items():
            destino = origem / na_origem
            destino.parent.mkdir(parents=True, exist_ok=True)
            # modo fixo 0o444, nunca o da origem (modo=None guardaria o bit de execução): no Ubuntu a árvore da skill pode
            # estar no DrvFs, onde todo arquivo aparece 0777
            COPIA.copiar_conferindo(fonte / do_pacote, destino, modo=0o444, dentro_de=fonte)
        res = PC.montar(raiz, projeto, plugin, origem)
    except OSError as exc:  # CopiaRecusada é um OSError
        raise PC.CandidatoRecusado(f"a preparação da origem falhou e nada foi montado ({exc})") from None
    finally:
        PC._apagar_sem_seguir(origem)
        try:
            for pasta in (origem.parent, origem.parent.parent):
                os.rmdir(pasta)  # só as pastas vazias que este script criou; as que têm algo ficam
        except OSError:
            pass
    return {**res, "feito": "montar-codigo-enxuto", "origem": "pacote da skill: assets/plugins/codigo-enxuto"}


def main(argv: list | None = None) -> int:
    for fluxo in (sys.stdout, sys.stderr):
        try:
            fluxo.reconfigure(encoding="utf-8")
        except (AttributeError, ValueError):
            pass
    ap = argparse.ArgumentParser(prog="plugin_codigo_enxuto.py", allow_abbrev=False,
                                 description="Monta o plugin codigo-enxuto da skill como candidato de um projeto.")
    sub = ap.add_subparsers(dest="acao", required=True)
    m = sub.add_parser("montar", allow_abbrev=False, help="monta projects/P/plugins-candidatos/P-codigo-enxuto/")
    m.add_argument("--raiz", required=True)
    m.add_argument("--projeto", required=True)
    m.add_argument("--plugin", default="codigo-enxuto", help="só codigo-enxuto")
    try:
        args = ap.parse_args(argv)
    except SystemExit as exc:
        return 2 if exc.code else 0
    try:
        print(json.dumps(montar(args.raiz, args.projeto, args.plugin), ensure_ascii=False, indent=1))
        return 0
    except PC.CandidatoRecusado as exc:
        print(json.dumps({"erro": "recusado", "motivos": exc.motivos}, ensure_ascii=False, indent=1))
        return 2


if __name__ == "__main__":
    sys.exit(main())
