"""Ensaio REAL do canário (1.7.10, pacote CANARIO): abre o Claude Code de verdade (`claude -p`) sobre a fundação
fictícia e confere o relatório. É o passo manual do titular no Ubuntu; NÃO roda na CI pública nem neste PC — fica
atrás do portão `skipUnless` abaixo. Para a CI contar este pulado como pulado (e não esconder que a prova real não
rodou), o runner dedicado do Linux liga `FUNDACAO_ENSAIO_REAL=1` com o `claude` fixado no PATH (ver `interface`:
sentinela, no espírito do `FUNDACAO_CI_EXIGE_BWRAP`). A base fica sob a casa (o `preparar` recusa a área temporária,
onde o sandbox libera a escrita; defeito 19); os temps são os do lançador (`/tmp/fundacao-ia-ensaio-*`) e o `limpar`
os apaga no fim. As sessões usam o ambiente do lançador (`env -i`, CLAUDE_CONFIG_DIR do ensaio no ext4 da casa,
`~/.local/share/fundacao-ia/ensaio/config-<id da base>`, que o `limpar` também apaga): sem o login único nessa
configuração (o passo do titular), elas não abrem e os itens ficam `nao_medido` — o teste confere o formato do
relatório e que nenhum canário vaza, não a conclusão. Só biblioteca padrão; nenhum dado real."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import sys
import tempfile
import unittest
from pathlib import Path

from apoio import SCRIPTS

# O portão exato pedido pelo contrato: só no Linux, só com FUNDACAO_ENSAIO_REAL=1 e com o `claude` disponível.
ENSAIO_REAL = (sys.platform.startswith("linux") and os.environ.get("FUNDACAO_ENSAIO_REAL") == "1"
               and bool(shutil.which("claude")))
MOTIVO = ("ensaio real do WSL: só com Linux + FUNDACAO_ENSAIO_REAL=1 + claude no PATH (passo manual do titular; "
          "não roda na CI pública nem neste PC)")


def carregar():
    spec = importlib.util.spec_from_file_location("ensaio_isolamento_real", SCRIPTS / "ensaio_isolamento_wsl.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


@unittest.skipUnless(ENSAIO_REAL, MOTIVO)
class TestEnsaioReal(unittest.TestCase):
    def test_abre_sessoes_e_gera_relatorio_bem_formado(self):
        mod = carregar()
        # A base sob a casa, nunca na temp (o sandbox libera a escrita na temp): apagada no fim.
        pai = Path(tempfile.mkdtemp(prefix="ensaio-real-1710-", dir=str(Path.home())))
        self.addCleanup(shutil.rmtree, pai, ignore_errors=True)
        base = pai / "ensaio"
        plano = mod.preparar(base)
        self.addCleanup(mod.limpar, base)  # os temps do lançador ficam fora da base: o limpar os apaga
        valores = {rot: Path(base / c["arquivo"]).read_text(encoding="utf-8").strip()
                   for rot, c in plano["canarios"].items()}
        claude = shutil.which("claude")
        versao, sha = mod.conferir_claude(claude, None)
        preparo = SCRIPTS.parent / "assets" / "host" / "preparo_host.py"
        destino = base / "perfil-ensaio-a.settings.json"
        perfil_info = mod.gerar_perfil_pelo_host(preparo, base, destino)
        perfil = destino if perfil_info.get("gerado") else None
        executor = mod.executor_claude(claude, perfil, mod.ferramentas_do_perfil(perfil), base)
        rel = mod.rodar(base, executor=executor, claude=claude, claude_versao=versao, claude_sha256=sha,
                        preparo_host=preparo, perfil_info=perfil_info,
                        sandbox_ligado=mod.sandbox_ligado_do_perfil(perfil))
        self.assertEqual(rel["schema_version"], "fundacao.ensaio_isolamento/1")
        self.assertIn("conclusao", rel)
        self.assertIn("sistema_de_arquivos", rel["conclusao"])
        self.assertEqual(len(rel["itens"]), len(mod.SONDAS))
        # Nenhum valor de canário no relatório, mesmo na prova real.
        texto = json.dumps(rel, ensure_ascii=False)
        for valor in valores.values():
            self.assertNotIn(valor, texto)


if __name__ == "__main__":
    unittest.main()
