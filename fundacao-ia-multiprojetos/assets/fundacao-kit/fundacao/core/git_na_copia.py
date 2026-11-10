"""O que a cópia de segurança leva do `.git` dos projetos (`RegraDaCopia`; 1.7.10, desenho §5.3 e §5.8), com a contagem
dos arquivos com cara de segredo (manutencao.com_cara_de_segredo, a regra única). Saiu de manutencao.py na revisão de
segurança da 1.7.10 (KITCOPIA, correções da revisão 1), para caber a regra dos gitdirs.

- O `.git` só dentro de projects/<projeto>/, fora de data/ e de pastas reconstruíveis, por cópia crua: o kit nunca
  executa git. `.git` e os nomes de dentro dele valem sem caixa e sem ponto ou espaço no fim (regras_da_copia._nome) em
  todos os sistemas: a raiz em /mnt/<letra> (DrvFs) e a restauração no NTFS não distinguem caixa (KIT-F3: o `.GIT` da
  cópia feita pelo Ubuntu entrava inteiro, com hooks e config).
- Gitdir: o .git levado e cada pasta dele com um HEAD na listagem, em qualquer profundidade — o submódulo `vendor/lib`
  mora em modules/vendor/lib, e um gitdir pode estar em objects/ (KIT-F3: os hooks deles entravam e rodavam) —, menos
  em refs/ e logs/ de um gitdir, onde HEAD é ref simbólica ou registro (refs/remotes/<r>/HEAD, logs/HEAD). Ficam fora
  os *.lock e, de cada gitdir, os hooks/ e o rebase em andamento (rebase-merge/ e rebase-apply/: o `exec` do todo
  rodaria no `git rebase --continue` da raiz restaurada; contados em operacoes_fora, correções da revisão 2). O config,
  o config.worktree, o commondir e o gitdir de worktrees/<id> (LIDOS) são lidos como o git lê (config_git.py) onde
  estiverem, também em objects/, menos em refs/ e logs/ de um gitdir: ali são um ramo, uma etiqueta ou o registro
  deles (feature/config, a etiqueta config), arquivo comum (revisão 2: saíam da cópia, e o repositório voltava sem
  eles). Os outros arquivos fora de objects/, só pela credencial em URL. O commondir só entra quando leva a um gitdir
  da listagem (a pasta comum não precisa de HEAD para o git, e os hooks e o config dela valem); o `.git` arquivo,
  quando leva a uma pasta de um .git levado fora de objects/, refs/, logs/, info/ e hooks/ de cada gitdir no caminho
  — o alvo sem HEAD na cópia não é gitdir na restauração, e o git o recusa —; e nenhum ponteiro com caminho absoluto
  (o `git worktree add` o grava): restaurado em outra pasta, ele levaria o git à raiz de origem (revisão 2). O que
  depende de saber quais pastas são gitdirs (o que fica abaixo do primeiro nível, os LIDOS e o `.git` arquivo) é
  decidido depois da listagem inteira (`listar`), com todos os HEAD dela: a ordem da listagem não decide.
- O manifesto conta os levados, os excluídos (com o motivo), os que mudaram na cópia e as pastas vazias que a
  restauração recria (KIT-F4; regras_da_copia.pastas_vazias), sem as de hooks/ e de rebase de nenhum gitdir.
"""

from __future__ import annotations

import os
from pathlib import Path, PurePath

from . import config_git, manutencao, preparo, regras_da_copia
from .contracts import ValidationError
from .regras_da_copia import _nome, chave

RECONSTRUIVEIS = frozenset({"node_modules", ".venv", "venv", "__pycache__", "site-packages", ".tox", ".mypy_cache",
                            ".pytest_cache"})
FORA_DO_ALVO = frozenset({"objects", "refs", "logs", "info", "hooks"})  # o .git arquivo não leva o git para dentro
SEM_CONTEUDO = {"hooks": "hooks", "rebase-merge": "operacoes", "rebase-apply": "operacoes"}  # pastas de gitdir: fora
LIDOS = {"config": "config", "config.worktree": "config", "commondir": "commondir", "gitdir": "gitdir"}  # e o tipo


class RegraDaCopia:
    """Decide e copia cada arquivo que o backup listou (ver o módulo). `copiar` devolve (sha256, tamanho) do que gravou
    em `destino` (a pasta files/ do preparo), ou None quando a regra deixa o arquivo fora (contado no relatório) ou o
    adia para o fim da listagem (`listar`)."""

    def __init__(self, destino: Path, criadas: set, root: Path):
        self.destino, self.criadas, self.root = Path(destino), criadas, Path(root)
        self.levados, self.mudaram = set(), []  # .git levados; .git de repositório vivo que mudou na cópia (#2)
        self.pastas, self.arquivos_git = set(), []  # KIT-F4: pastas vistas dentro de um .git; arquivos copiados dele
        self.heads: set[tuple] = set()  # KIT-F3: as pastas com HEAD na listagem (partes); delas saem os gitdirs
        self.gitdirs: set[str] = set()  # os gitdirs reconhecidos no fim da listagem (regras_da_copia.chave)
        self.adiados: list = []  # (origem, lstat da listagem): decididos no fim, com todos os HEAD
        self.no_fim = False
        self.excluidos: dict[str, str] = {}
        self.config_fora: dict[str, str] = {}
        self.hooks = self.operacoes = self.travas = self.segredos = 0

    @staticmethod
    def git(rel) -> tuple[str | None, str | None, list[str]]:
        """(o .git no caminho, o motivo de ficar fora ou None, as partes de dentro dele, por `_nome`); sem .git: (None,
        None, [])."""
        partes = list(PurePath(rel).parts)
        nomes = [_nome(p) for p in partes]
        if ".git" not in nomes:
            return None, None, []
        i = nomes.index(".git")
        raiz, dentro = "/".join(partes[:i + 1]), nomes[i + 1:]
        if nomes[0] != "projects" or i < 2:
            return raiz, "fora de projects/<projeto>/", dentro
        if nomes[2] == "data":
            return raiz, "em data/ do projeto (cópia de referência da origem)", dentro
        if RECONSTRUIVEIS.intersection(nomes[2:i]):
            return raiz, "dentro de pasta reconstruível", dentro
        return raiz, None, dentro

    def _gitdir(self, partes: list, dentro: list, k: int) -> bool:
        """A pasta das `k` primeiras partes de `dentro` (as do caminho `partes` depois do .git) é um gitdir: o próprio
        .git levado (k = 0) ou uma pasta com HEAD na listagem."""
        return k == 0 or chave(partes[:len(partes) - len(dentro) + k]) in self.gitdirs

    def _sob(self, partes: list, dentro: list, nomes) -> str | None:
        """O nome de `nomes` que é pasta (ou o próprio arquivo) de um gitdir no caminho — hooks/, rebase-merge/, refs/,
        logs/... —, ou None."""
        return next((n for k, n in enumerate(dentro) if n in nomes and self._gitdir(partes, dentro, k)), None)

    def _alvo_aceito(self, alvo: str, commondir: bool) -> bool:
        """Para onde o `.git` arquivo ou o commondir pode levar o git (`alvo`: relativo à raiz, com /): uma pasta de um
        .git levado, fora de objects/, refs/, logs/, info/ e hooks/ de cada gitdir no caminho; o commondir, só a um
        gitdir (o .git levado ou pasta com HEAD na listagem)."""
        raiz, motivo, dentro = self.git(alvo)
        partes = alvo.split("/")
        if raiz is None or motivo or any(n in FORA_DO_ALVO and self._gitdir(partes, dentro, k)
                                         for k, n in enumerate(dentro)):
            return False
        return not commondir or self._gitdir(partes, dentro, len(dentro))

    def _reconhecer(self) -> None:
        """Os gitdirs, das pastas mais rasas às mais fundas: cada pasta com HEAD na listagem, menos a que fica em refs/
        ou logs/ de um gitdir — ali, HEAD é ref simbólica ou registro de ref (refs/remotes/<r>/HEAD, logs/HEAD), e o
        .git arquivo e o commondir não levam o git para lá."""
        self.gitdirs = set()
        for partes in sorted(self.heads, key=len):
            if not self._sob(list(partes), self.git("/".join(partes))[2], ("refs", "logs")):
                self.gitdirs.add(chave(partes))

    def listar(self, itens):
        """Os itens da listagem (caminho, `lstat`) e, no fim, os adiados, decididos com todos os HEAD dela (KIT-F3)."""
        yield from itens
        self._reconhecer()
        self.no_fim = True
        yield from self.adiados

    def copiar(self, origem: Path, rel, listado: os.stat_result) -> tuple[str, int] | None:
        raiz, motivo, dentro = self.git(rel)
        if motivo:  # arquivo .git fora de projects/ etc. (o diretório já é podado na listagem: BAIXO #5)
            self.excluidos[raiz] = motivo
            return None
        posix, partes, tipo = PurePath(rel).as_posix(), list(PurePath(rel).parts), None
        if raiz:
            if dentro[-1:] == ["head"]:  # KIT-F3: um HEAD na listagem faz da pasta um gitdir (`_reconhecer`)
                self.heads.add(tuple(partes[:-1]))
            if dentro[:1] and dentro[0] in SEM_CONTEUDO:  # .git/hooks (código que rodaria depois), .git/rebase-merge...
                return self._fora(dentro[0])
            if dentro and dentro[-1].endswith(".lock"):  # trava de um git em andamento
                self.travas += 1
                return None
            if not self.no_fim and (not dentro or dentro[-1] in LIDOS or any(n in SEM_CONTEUDO for n in dentro[1:])):
                self.adiados.append((origem, listado))  # depende de saber quais pastas são gitdirs: no fim
                return None
            if fora := self._sob(partes, dentro, SEM_CONTEUDO):  # de um gitdir mais fundo (submódulo, objects/<x>/...)
                return self._fora(fora)
            tipo = "gitfile" if not dentro else LIDOS.get(dentro[-1])
            if tipo and dentro and self._sob(partes, dentro, ("refs", "logs")):  # revisão 2: ramo ou etiqueta config
                tipo = None
        dados = None
        try:
            if raiz and (tipo or "objects" not in dentro):  # #1: conferido em memória
                dados = preparo.ler(origem, listado) if listado.st_size <= manutencao.TETO_CONFIG else None
                fora = config_git.motivo_do_arquivo(posix, tipo, dados, self.root, self._alvo_aceito)
                if fora:
                    self.config_fora[posix] = fora
                    return None
            alvo = self.destino / rel
            preparo.criar_pasta(alvo.parent, self.criadas)
            copiado = preparo.copiar(origem, alvo, listado) if dados is None else preparo.gravar(alvo, dados, listado)
        except (FileNotFoundError, ValidationError):  # #2: .git de repositório vivo some/troca durante a cópia
            if not raiz:
                raise  # fora do .git: comportamento de antes (o chamador trata)
            self.mudaram.append(posix)
            return None
        if raiz:
            self.levados.add(raiz)
            self.arquivos_git.append(posix)
        if manutencao.com_cara_de_segredo(rel):
            self.segredos += 1
        return copiado

    def _fora(self, pasta: str) -> None:
        """Conta o arquivo que fica fora por estar em hooks/ (hooks_fora) ou no rebase em andamento (operacoes_fora)."""
        if SEM_CONTEUDO[pasta] == "hooks":
            self.hooks += 1
        else:
            self.operacoes += 1

    def descartar(self, caminho) -> bool:
        """True para o .git deixado inteiro fora da cópia; anota o motivo em `excluidos` e não o percorre (BAIXO #5). As
        pastas de um .git que entra ficam anotadas: a vazia volta na restauração (KIT-F4), menos as de hooks/ e de
        rebase de um gitdir, tiradas no relatório (os gitdirs só se sabem com a listagem inteira)."""
        rel = Path(caminho).relative_to(self.root)
        raiz, motivo, _ = self.git(rel)
        if motivo:
            self.excluidos[raiz] = motivo
        elif raiz:
            self.pastas.add(rel.as_posix())
        return bool(motivo)

    def relatorio_git(self) -> dict:
        """Para o manifesto: os .git levados, os que ficaram fora (com o motivo) e o que ficou fora dentro deles."""
        self._reconhecer()
        pastas = {p for p in self.pastas if not self._sob(list(PurePath(p).parts), self.git(p)[2], SEM_CONTEUDO)}
        return {"regra": "levado só em projects/<projeto>/, fora de data/ e de pastas reconstruíveis; sem os hooks e o "
                         "rebase em andamento (rebase-merge/, rebase-apply/) de cada gitdir, *.lock, config com "
                         "credencial ou programa e .git arquivo, commondir ou gitdir de worktree com caminho absoluto "
                         "ou que leve o git para fora de um gitdir",
                "levados": sorted(self.levados),
                "excluidos": [{"caminho": c, "motivo": m} for c, m in sorted(self.excluidos.items())],
                "config_fora": [{"caminho": c, "motivo": m} for c, m in sorted(self.config_fora.items())],
                "hooks_fora": self.hooks, "operacoes_fora": self.operacoes, "travas_fora": self.travas,
                "mudaram_durante_a_copia": sorted(self.mudaram),
                "pastas_vazias": regras_da_copia.pastas_vazias(pastas, self.arquivos_git, self.levados)}

    def texto_credenciais(self, cifrada: bool = False) -> str:
        """Texto de `credentials` do manifesto; `cifrada` (1.7.11): a cópia vai para as partes .gpg do titular."""
        fim = ("A cópia é CIFRADA para a chave pública do titular (partes .gpg): estes arquivos só abrem com a chave "
               "privada e a senha dele" if cifrada else
               "A cópia não é cifrada: guarde-a como guarda a fundação")
        return (f"o .env fica fora; {self.segredos} arquivo(s) com cara de segredo (pastas e nomes de segredo) "
                f"entraram {'dentro da cifra' if cifrada else 'em claro'}, sem leitura (segredos_incluidos); config do git "
                f"com credencial fica fora (git.config_fora). {fim}")
