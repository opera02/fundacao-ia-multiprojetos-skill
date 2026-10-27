"""Dados de executores encerrados: leitura limitada, sem elos, para cópia privada.

Não executa conteúdo. A captura exige uma árvore quieta; mudança observada recusa
a captura inteira. Não é isolamento de SO contra outro processo com a mesma conta.
"""
from contextlib import contextmanager
import os
from pathlib import Path
import stat
import tempfile

MAX_ARQUIVO = 64 * 1024 * 1024
MAX_TOTAL = 512 * 1024 * 1024
MAX_ENTRADAS = 50000
MAX_PROFUNDIDADE = 64

def seguro(raiz, caminho):
    root, p = Path(raiz), Path(caminho)
    if '..' in root.parts or '..' in p.parts:
        raise ValueError('subida de pasta recusada')
    root, p = Path(os.path.abspath(root)), Path(os.path.abspath(p))
    if not p.is_relative_to(root):
        raise ValueError('caminho fora da raiz declarada')
    for part in p.parts[1:]:
        if ':' in part: raise ValueError('nome de caminho recusado')
    for item in [*reversed(p.parents), p]:
        st = item.lstat()
        if stat.S_ISLNK(st.st_mode) or getattr(st,'st_file_attributes',0) & 0x400:
            raise ValueError('ligacao ou juncao recusada')
        if item != p and not stat.S_ISDIR(st.st_mode):
            raise ValueError('ancestral nao e pasta comum')
        if not (stat.S_ISREG(st.st_mode) or stat.S_ISDIR(st.st_mode)):
            raise ValueError('arquivo especial recusado')
        if stat.S_ISREG(st.st_mode) and st.st_nlink != 1:
            raise ValueError('hardlink recusado')
    return p

def marca(st):
    return (st.st_dev, st.st_ino, st.st_size, st.st_mtime_ns, st.st_ctime_ns)

def ler(raiz, caminho, *, limite=MAX_ARQUIVO):
    p = seguro(raiz, caminho); before = p.lstat()
    if not stat.S_ISREG(before.st_mode) or before.st_size > limite:
        raise ValueError('arquivo comum acima do limite ou tipo recusado')
    flags = os.O_RDONLY | getattr(os,'O_BINARY',0) | getattr(os,'O_NOFOLLOW',0) | getattr(os,'O_NONBLOCK',0)
    with os.fdopen(os.open(p,flags),'rb') as stream:
        opened = os.fstat(stream.fileno())
        # No Windows lstat.ctime (criação) e fstat.ctime (alteração) podem ter
        # semânticas diferentes; conferir ctime somente dentro da mesma API.
        if marca(before)[:4] != marca(opened)[:4] or not stat.S_ISREG(opened.st_mode) or opened.st_nlink != 1:
            raise ValueError('arquivo trocado antes da leitura')
        data = stream.read(limite+1); after = os.fstat(stream.fileno())
    if len(data)>limite or marca(opened)!=marca(after) or marca(seguro(raiz,p).lstat())!=marca(before):
        raise ValueError('arquivo mudou durante a leitura')
    return data

def capturar(raiz, *, recusados=None):
    root = seguro(raiz,raiz)
    if not root.is_dir(): raise ValueError('raiz nao e pasta')
    files, observed, total, count = {}, {}, 0, 0
    links = {}
    stack = [(root,0)]
    while stack:
        folder, depth = stack.pop()
        if depth > MAX_PROFUNDIDADE: raise ValueError('profundidade acima do limite')
        folder = seguro(root,folder); before = marca(folder.lstat())
        children = []
        for child in folder.iterdir():
            count += 1
            if count>MAX_ENTRADAS: raise ValueError('entradas acima do limite')
            children.append(child)
        if marca(seguro(root,folder).lstat())!=before: raise ValueError('pasta mudou durante captura')
        observed[folder] = before
        for child in children:
            st = child.lstat()
            if recusados is not None and (stat.S_ISLNK(st.st_mode) or getattr(st,'st_file_attributes',0) & 0x400):
                # Compatibilidade da coleta de saídas: só ligações são omitidas,
                # com lacuna explícita; nunca seguir nem ler o alvo.
                recusados.append(child.relative_to(root).as_posix())
                links[child] = marca(st)
                continue
            child = seguro(root,child); st = child.lstat()
            if child.is_dir(): stack.append((child,depth+1))
            else:
                if total+st.st_size>MAX_TOTAL: raise ValueError('bytes totais acima do limite')
                data = ler(root,child); total += len(data)
                if total>MAX_TOTAL: raise ValueError('bytes totais acima do limite')
                files[child.relative_to(root).as_posix()] = data
                observed[child] = marca(st)
    for p, before in observed.items():
        if marca(seguro(root,p).lstat())!=before: raise ValueError('arvore mudou durante captura')
    for p, before in links.items():
        seguro(root,p.parent)
        if marca(p.lstat())!=before: raise ValueError('ligacao mudou durante captura')
    return files, [p.relative_to(root).as_posix() for p in observed if p.is_dir()]

@contextmanager
def copia_arvore(raiz, *, recusados=None):
    files, dirs = capturar(raiz, recusados=recusados)
    with tempfile.TemporaryDirectory(prefix='avaliado-dados-') as td:
        target = Path(td)/'copia'; target.mkdir()
        for rel in dirs: (target/rel).mkdir(parents=True,exist_ok=True)
        for rel,data in files.items():
            path = target/rel; path.parent.mkdir(parents=True,exist_ok=True)
            with path.open('xb') as stream: stream.write(data)
        yield target

@contextmanager
def copia_banco(raiz, banco):
    p = seguro(raiz,banco); candidates = [p]
    for suffix in ('-wal','-shm','-journal'):
        side = Path(str(p)+suffix)
        try: seguro(raiz,side)
        except FileNotFoundError: continue
        candidates.append(side)
    before = {f:marca(f.lstat()) for f in candidates}
    files = {f.name:ler(raiz,f) for f in candidates}
    for f, expected in before.items():
        if marca(seguro(raiz,f).lstat())!=expected: raise ValueError('banco mudou durante captura')
    # Conferir também criação/remoção de auxiliares durante a captura.
    for suffix in ('-wal','-shm','-journal'):
        side = Path(str(p)+suffix)
        try: seguro(raiz,side)
        except FileNotFoundError:
            if side in before: raise ValueError('auxiliar removido durante captura')
        else:
            if side not in before: raise ValueError('auxiliar criado durante captura')
    with tempfile.TemporaryDirectory(prefix='avaliado-sqlite-') as td:
        for name,data in files.items():
            with (Path(td)/name).open('xb') as stream: stream.write(data)
        yield Path(td)/p.name
