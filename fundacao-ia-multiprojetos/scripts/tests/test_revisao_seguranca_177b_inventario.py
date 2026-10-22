"""Revisão de segurança da 1.7.7, segunda passada — inventário dos plugins do host (R177B-A-01 e R177B-A-02).

- A-01: o matcher de hook de plugin era saneado antes de tudo — caractere de controle e surrogate viravam espaço — e o
  texto saneado era o avaliado pelos alertas e o do SHA-256. `Edit|\\u0001|` saía como `Edit| |`, lista exata, sem
  alerta e com o hash de `Edit| |`; trocar um pelo outro não aparecia no `verificar`. Pela regra do matcher, o
  caractere de controle faz uma expressão sem âncora, e a alternativa vazia casa todas as ferramentas. Agora o
  inteiro cru é o avaliado e o do hash (UTF-8 com `surrogatepass`); só a cópia de exibição é saneada; e matcher com
  caractere de controle ou surrogate sai com alerta — `matcher_casa_tudo` quando a regra diz, senão
  `matcher_indeterminado` (a cópia mostra espaço onde o host vê outro caractere).
- A-02: NUL num caminho declarado por plugin (script do hook, `skills`, `hooks`, `mcpServers` ou `installPath`) chegava
  ao `os.lstat`, que lança `ValueError`: o `gravar` saía com 1 sem gravar e o `verificar` caía com o mesmo código das
  diferenças. Agora o caminho com NUL é recusado como o com `..` ou `:`, sem reproduzir o texto dele, e o acesso ao
  disco pega `ValueError` junto com `OSError`.

Perfil fictício numa pasta descartável (o apoio de test_revisao_seguranca_177_inventario.py). Cada teste falha no HEAD
revisado (4c11fed) e passa depois da correção; os controles mostram o uso legítimo.
"""

from __future__ import annotations

import hashlib
import json
import unittest
from unittest import mock

from test_revisao_seguranca_177_inventario import _Host, carregar, escrever

RAIZ_P = "${CLAUDE_PLUGIN_ROOT}"
NULO = "caminho com caractere nulo"


def sha(texto: str) -> str:
    return hashlib.sha256(texto.encode("utf-8", "surrogatepass")).hexdigest()


def grupo(matcher: str) -> dict:
    return {"matcher": matcher, "hooks": [{"type": "command", "command": "node"}]}


class TestMatcherCru(_Host):
    """R177B-A-01: avaliação e hash pelo matcher cru; a cópia de exibição é a única saneada."""

    def test_controle_no_matcher_e_avaliado_e_guardado_pelo_texto_cru(self):
        crus = ("Edit|\u0001|", "Edit|\t|", "Edit|Write\u0001", "Edit\ud800", "Edit|\x7f|Write")
        self.hooks_do_plugin({"PreToolUse": [grupo(m) for m in crus]})
        escrever(self.raiz / ".claude" / "settings.json", {"hooks": {"PreToolUse": [grupo("Write|\u0002|")]}})
        inv = self.gravar()
        do_plugin = [h for h in inv["hooks"] if h["origem"] == self.ORIGEM]
        self.assertEqual([h["matcher"] for h in do_plugin], ["Edit| |", "Edit| |", "Edit|Write ", "Edit ",
                                                             "Edit| |Write"])  # a cópia de exibição, saneada
        self.assertEqual([h["matcher_sha256"] for h in do_plugin], [sha(m) for m in crus])
        self.assertNotEqual(do_plugin[0]["matcher_sha256"], sha("Edit| |"), "o hash é o do texto saneado")
        self.assertEqual({h["matcher_tipo"] for h in do_plugin}, {"expressao"}, "controle não forma lista exata")
        alertas = {(a["matcher"], a["alerta"]) for a in inv["alertas"] if a["alerta"] != "evento_fora_do_guarda"}
        for exibido, alerta in (("Edit| |", "matcher_casa_tudo"), ("Edit|Write ", "matcher_indeterminado"),
                                ("Edit ", "matcher_indeterminado"), ("Edit| |Write", "matcher_indeterminado")):
            with self.subTest(matcher=exibido):
                self.assertIn((exibido, alerta), alertas)
        raiz = next(a for a in inv["alertas"] if a["origem"] == "raiz:settings.json")  # controle: o da raiz, cru
        self.assertEqual(raiz["alerta"], "matcher_casa_tudo")

    def test_verificar_acusa_a_troca_do_espaco_pelo_controle(self):
        self.hooks_do_plugin({"PreToolUse": [grupo("Edit| |")]})
        self.gravar()
        code, saida = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 0, saida[-1500:])
        self.hooks_do_plugin({"PreToolUse": [grupo("Edit|\u0001|")]})  # a mesma cópia de exibição
        code, saida = self.rodar("verificar", "--inventario", self.saida)
        self.assertEqual(code, 1, "a troca do espaço pelo caractere de controle passou sem diferença: " + saida[-800:])
        res = json.loads(saida)
        dif = res["diferencas"]["hooks"]
        self.assertTrue(dif["alterados"] or (dif["adicionados"] and dif["removidos"]), dif)
        self.assertIn("matcher_casa_tudo", res["alertas"])

    def test_regra_e_controles(self):
        ah, ip = carregar("alertas_hooks"), carregar("inventario_plugins")
        self.assertEqual(ah.CONTROLE.pattern, ip.CONTROLE.pattern, "o que a cópia troca é o que o alerta acusa")
        self.assertEqual(ah.avaliar_matcher("PreToolUse", "Edit|\u0001|")[:2], ("expressao", "matcher_casa_tudo"))
        self.assertEqual(ah.avaliar_matcher("PreToolUse", "Edit\u0001")[:2], ("expressao", "matcher_indeterminado"))
        self.assertEqual(ah.avaliar_matcher("Stop", "x\u0001")[:2], ("ignorado", "matcher_casa_tudo"))
        self.assertEqual(ah.avaliar_matcher("Evento\u0001", "Edit")[:2], ("evento desconhecido", "matcher_nunca_casa"))
        for evento, legitimo, forma in (("PreToolUse", "Edit|Write", "exato"), ("PreToolUse", "Edit| |Write", "exato"),
                                        ("PreToolUse", "mcp__srv__.*", "expressao"),
                                        ("SessionStart", "startup|resume", "exato")):
            with self.subTest(matcher=legitimo):
                self.assertEqual(ah.avaliar_matcher(evento, legitimo), (forma, None, None))
        campos = ip._matcher("Edit|\u0001|")
        self.assertEqual((campos["matcher"], campos["_matcher_inteiro"]), ("Edit| |", "Edit|\u0001|"))
        self.assertEqual(ip._matcher("Edit|Write"), {"matcher": "Edit|Write", "matcher_sha256": sha("Edit|Write"),
                                                     "_matcher_inteiro": "Edit|Write"})


class TestNulNoCaminhoDoPlugin(_Host):
    """R177B-A-02: caminho com NUL vindo de plugin é recusado sem tocar o disco e sem derrubar o inventário."""

    VETORES = {
        "script do hook": lambda t: t.hooks_do_plugin({"PreToolUse": [{"matcher": "Bash", "hooks": [
            {"type": "command", "command": f"{RAIZ_P}/a\u0000.sh"}]}]}),
        "skills": lambda t: t.manifesto(skills=["a\u0000b"]),
        "hooks do manifesto": lambda t: t.manifesto(hooks="./h\u0000.json"),
        "mcpServers do manifesto": lambda t: t.manifesto(mcpServers="./m\u0000.json"),
        "installPath": lambda t: t.instalados(str(t.plugin) + "\u0000x"),
    }

    def manifesto(self, **campos) -> None:
        escrever(self.plugin / ".claude-plugin" / "plugin.json", {"name": "teste", "version": "1.0.0", **campos})

    def instalados(self, *outro: str) -> None:
        plugins = {"teste@mercado": [{"scope": "user", "version": "1.0.0", "installPath": str(self.plugin)}]}
        plugins.update({"nulo@mercado": [{"scope": "user", "version": "1.0.0", "installPath": p}] for p in outro})
        escrever(self.plugins / "installed_plugins.json", {"version": 2, "plugins": plugins})

    def reiniciar(self) -> None:
        """O perfil do setUp, sem o que o vetor anterior plantou."""
        self.instalados()
        self.manifesto()
        (self.plugin / "hooks" / "hooks.json").unlink(missing_ok=True)
        self.saida.unlink(missing_ok=True)

    def test_nul_nao_derruba_gravar_nem_verificar(self):
        for nome, plantar in self.VETORES.items():
            with self.subTest(vetor=nome):
                self.reiniciar()
                plantar(self)
                inv = self.gravar()  # no 4c11fed: código 1, "ValueError: embedded null character"
                self.assertNotIn("\\u0000", self.saida.read_text(encoding="utf-8"), "o caminho com NUL saiu")
                motivos = [n["motivo"] for n in inv["plugins_nao_lidos"]]
                motivos += [s.get("nao_lido", "") for h in inv["hooks"] for s in h["scripts"]]
                self.assertTrue(any(NULO in m for m in motivos), motivos)
                code, saida = self.rodar("verificar", "--inventario", self.saida)
                self.assertEqual(code, 0, saida[-1500:])

    def test_leitor_recusa_nul_sem_tocar_o_disco(self):
        ip = carregar("inventario_plugins")
        leitor = ip._Leitor()
        with mock.patch.object(ip.os, "lstat", side_effect=AssertionError("tocou o disco")):
            for rel in ("a\u0000.sh", "pasta/a\u0000b", "\u0000"):
                with self.subTest(rel=repr(rel)):
                    self.assertEqual(leitor.caminho(self.plugin, rel), NULO)
                    self.assertEqual(leitor.ler(self.plugin, rel), NULO)
                    self.assertIsNone(leitor.pasta(self.plugin, rel))
        self.assertIn(NULO, ip.SEM_O_CAMINHO)  # o texto do caminho não vai para o inventário
        self.assertEqual(ip._nao_lido("o", "a\u0000b", NULO), {"origem": "o", "motivo": NULO})
        escrever(self.plugin / "ok.json", {"x": 1})  # controle: o caminho legítimo continua lido
        self.assertEqual(leitor.ler_json(self.plugin, "ok.json", "o", []), {"x": 1})


if __name__ == "__main__":
    unittest.main()
