"""Canário do WSL (1.7.10, pacote CANARIO; reconferência REV2, defeito 11a): controles SEM sandbox, no Linux. Os
comandos reais das sondas rodam por `bash -c`, um por vez, e a saída vai ao juiz no formato stream-json (o par
tool_use/tool_result de cada comando, como o Claude Code entrega): sem sandbox, cada sonda tem de dar `falhou` (prova
que o canário detecta o vazamento) e o seccomp, False. O barramento só é pulado sem um /run/user/*/bus que aceite
conexão no host; a rede, atrás de FUNDACAO_ENSAIO_CONTROLE_REDE=1 (não toca a rede por padrão). Nada abre o Claude
Code."""

from __future__ import annotations

import os
import shutil
import subprocess
import unittest

from test_ensaio_isolamento import LINUX, Base, _ctx, carregar, par_de_ferramenta

BASH = LINUX and bool(shutil.which("bash")) and os.path.exists("/usr/bin/python3")
BARRAMENTOS = carregar().barramentos_conectaveis() if BASH else []
REDE = BASH and os.environ.get("FUNDACAO_ENSAIO_CONTROLE_REDE") == "1" and os.path.exists("/usr/bin/curl")


def executor_bash(cwd):
    """Executor de controle: cada comando da sessão roda por `bash -c` (sem sandbox) e vira um par stream-json."""
    def exe(base, proj, sessao):
        linhas = []
        for i, cmd in enumerate(sessao["comandos"]):
            r = subprocess.run(["bash", "-c", cmd], capture_output=True, text=True, cwd=str(cwd), timeout=60)
            linhas += par_de_ferramenta(f"t{i}", cmd, (r.stdout or "") + (r.stderr or ""))
        return {"transcricao": "\n".join(linhas), "codigo": 0}
    return exe


class Controle(Base):
    def julgar(self, sid, ctx):
        plano = self.mod.preparar(self.base)
        sonda = next(s for s in self.mod.SONDAS if s["id"] == sid)
        exe = executor_bash(self.base / "projects" / "ensaio-a")
        sr = [(ses, exe(self.base, "ensaio-a", ses)) for ses in sonda["sessoes"](self.base, plano, plano["nonce"], ctx)]
        return plano, sr, sonda["julgar"](self.base, plano, ctx, sr)


@unittest.skipUnless(BASH, "controle sem sandbox só no Linux com bash e /usr/bin/python3")
class TestControleDeArquivos(Controle):
    def test_sondas_de_arquivos_em_stream_json_detectam_vazamento(self):
        for sid in ("leitura_outro_projeto", "leitura_state", "escrita_fora_do_projeto", "temp_outro_projeto",
                    "fila_porteiro"):
            with self.subTest(sid):
                plano, sr, (veredito, motivo) = self.julgar(sid, _ctx(barramentos=[]))
                self.assertEqual(veredito, "falhou", f"{sid}: {motivo}")
                medida = self.mod._medir(sr[0][0], sr[0][1], plano["nonce"])
                self.assertEqual(medida["problemas"], [], sid)  # o FIM de cada comando chegou pelo tool_result
                self.mod.limpar(self.base)


@unittest.skipUnless(BASH and BARRAMENTOS, "sem /run/user/*/bus que aceite conexão no host (nada a medir)")
class TestControleDoBarramento(Controle):
    def test_sonda_barramento_detecta_sem_sandbox(self):
        _, _, (veredito, motivo) = self.julgar("socket_barramento", _ctx(barramentos=BARRAMENTOS))
        self.assertEqual(veredito, "falhou", motivo)

    def test_seccomp_sem_sandbox_e_false(self):
        plano = self.mod.preparar(self.base)
        presente, motivo = self.mod.medir_seccomp(executor_bash(self.base), self.base, plano["nonce"])
        self.assertIs(presente, False, motivo)


@unittest.skipUnless(REDE, "controle de rede só com FUNDACAO_ENSAIO_CONTROLE_REDE=1 (toca example.com) no Linux")
class TestControleDaRede(Controle):
    def test_sonda_rede_detecta_sem_sandbox(self):
        _, _, (veredito, motivo) = self.julgar("rede_fora_da_lista", _ctx(barramentos=[]))
        self.assertEqual(veredito, "falhou", motivo)


if __name__ == "__main__":
    unittest.main()
