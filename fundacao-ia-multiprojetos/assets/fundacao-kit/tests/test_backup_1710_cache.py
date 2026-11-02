"""Caches de ferramenta do projeto fora da cópia (1.7.10). O perfil do Ubuntu aponta XDG_CACHE_HOME, npm, pip e uv
para `projects/<p>/.cache` (contratos do lote 2, §6), e a crítica do desenho os quer "fora do Git e da cópia de
segurança": a cópia os deixa fora como as outras pastas reconstruíveis (`.venv`, `node_modules`), e a verificação da
cópia continua passando. Raiz descartável com projetos de ensaio; conteúdo fictício."""

from __future__ import annotations

import shutil

from helpers import FoundationTestCase

from fundacao.core import backup


class TestCacheForaDaCopia(FoundationTestCase):
    def test_cache_do_projeto_fica_fora_e_a_copia_confere(self):
        projeto = self.root / "projects" / "juridico-lab"
        for rel in (".cache/npm/_cacache/pacote-ficticio", ".cache/pip/http/roda-ficticia", "trabalho/notas.md"):
            (projeto / rel).parent.mkdir(parents=True, exist_ok=True)
            (projeto / rel).write_text("conteúdo fictício\n", encoding="utf-8")
        snap = self.root.parent / f"{self.root.name}-snap-cache"
        self.addCleanup(shutil.rmtree, snap, True)
        m = backup.create_backup(self.root, snap, "cache-1710")
        caminhos = {f["path"] for f in m["files"]}
        self.assertIn("projects/juridico-lab/trabalho/notas.md", caminhos)
        self.assertEqual([c for c in caminhos if "/.cache/" in c], [])
        self.assertIn(".cache", m["excluded"])
        self.assertFalse((snap / "projects" / "juridico-lab" / ".cache").exists())
        self.assertTrue(backup.verify_backup(snap)["ok"])
