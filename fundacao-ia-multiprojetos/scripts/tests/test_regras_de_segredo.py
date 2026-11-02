"""Regra única de segredo (1.7.10; DESENHO-1.7.10 §5.1 e §7.1; MELHORIAS-1.7.10, seção 1, item 10).

Casos certos, errados e quase certos de `regras_de_segredo.classificar`, as listas exportadas (que o kit e os perfis
do host repetem) e a mesma regra gravada na política do manifesto do formato 3. Só nomes: nada é lido do disco.
"""

from __future__ import annotations

import importlib.util
import json
import unittest

from apoio import SCRIPTS, rodar_script


def carregar(nome: str):
    spec = importlib.util.spec_from_file_location(f"_teste_regras_{nome}", SCRIPTS / f"{nome}.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


R = carregar("regras_de_segredo")


class TestListas(unittest.TestCase):
    def test_listas_trazem_o_pedido_da_1_7_10(self):
        fortes_antigos = [".env", ".env.*", "*.pem", "*.key", "*.pfx", "*.p12", "id_rsa*", "*credentials*",
                          "*secret*", "auth.json", "*.kdbx"]
        fortes_novos = ["id_ed25519*", "id_ecdsa*", "id_dsa*", "*.ppk", "*.jks", "*.keystore", "*.p8", "*.ovpn",
                        ".netrc", "_netrc", ".npmrc", ".pypirc", ".pgpass", ".htpasswd", "*.tfvars", "*.tfstate*",
                        "kubeconfig*", "service-account*.json", ".git-credentials"]
        self.assertEqual(list(R.NOMES_FORTES), fortes_antigos + fortes_novos)
        self.assertEqual(set(R.NOMES_FRACOS), {"*token*", "*senha*", "*password*", "*passwd*", "*api_key*",
                                               "*apikey*", ".env.example", "*.example", "*.sample", ".mcp.json",
                                               "settings.local.json", ".git/config"})
        self.assertLessEqual(set(R.EXEMPLOS_DE_SEGREDO), set(R.NOMES_FRACOS))
        self.assertEqual(set(R.PASTAS_DE_SEGREDO), {".segredos", "segredos", ".secrets", "secrets", ".envs", ".ssh",
                                                    ".gnupg", ".aws", ".azure", ".kube", ".docker", "credentials",
                                                    "_browser_profile", ".omniroute"})

    def test_os_fortes_do_manifesto_ate_a_1_7_9_continuam_fortes(self):
        # A regra nova não afrouxa a antiga: todo padrão do formato 2 do manifesto continua forte.
        manifesto = carregar("manifesto")
        self.assertLessEqual(set(manifesto.SECRET_GLOBS), set(R.NOMES_FORTES))

    def test_listas_pela_linha_de_comando_iguais_as_do_modulo(self):
        p = rodar_script("regras_de_segredo.py", "listas")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), R.listas())
        self.assertEqual(json.loads(p.stdout)["schema_version"], "fundacao.regras_de_segredo/1")


class TestClassificar(unittest.TestCase):
    def conferir(self, esperado, casos, extras=()):
        for caminho in casos:
            with self.subTest(caminho=caminho):
                self.assertEqual(R.classificar(caminho, extras), esperado)

    def test_nomes_fortes(self):
        self.conferir("forte", [
            ".env", "config/.env.local", "a/b/server.pem", "tls/site.key", "cert.pfx", "cert.p12", "chaves/id_rsa",
            "chaves/id_ed25519", "id_ecdsa", "id_dsa", "deploy/acesso.ppk", "android/app.jks", "release.keystore",
            "AuthKey_ABC.p8", "vpn/escritorio.ovpn", ".netrc", "_netrc", ".npmrc", ".pypirc", ".pgpass", ".htpasswd",
            "infra/prod.tfvars", "terraform.tfstate", "terraform.tfstate.backup", "kubeconfig", "kubeconfig-prod",
            "service-account-123.json", ".git-credentials", "aws_credentials", "app_secret.txt", "auth.json",
            "cofre.kdbx"])

    def test_nomes_fracos(self):
        self.conferir("fraco", [
            "setup_token", "tokens/acesso_token.txt", "minhas_senhas.txt", "password_reset.py", "etc/passwd",
            "api_key.txt", "openai_apikey", "settings.local.json", ".claude/settings.local.json", ".mcp.json",
            "squad/.mcp.json", ".git/config", "repo/sub/.git/config", "config.sample", "modelo.example"])

    def test_exemplo_de_segredo_e_fraco_mesmo_casando_um_forte(self):
        # `.env.example` casa `.env.*` (forte) e `*secret*` (forte): o exemplo vence, para a conferência liberar.
        self.conferir("fraco", [".env.example", "secrets.env.example", "id_rsa.sample", "credentials.example"])

    def test_pastas_de_segredo_em_qualquer_nivel_e_inclusive_o_ultimo(self):
        self.conferir("pasta-de-segredo", [
            ".segredos/setup_token", ".segredos", "x/.envs/dev.env", "secrets/config.yaml", "app/.secrets/a",
            "segredos/notas.txt", "home/.ssh/known_hosts", ".gnupg/pubring.kbx", ".aws/config", ".azure/x",
            ".kube/config", ".docker/config.json", "projeto/credentials/x.txt",
            # Globais desde os contratos do lote 2 (antes, extras só da cópia do kit):
            "x/_browser_profile/Default/Cookies", ".omniroute/roteador.sqlite", "ferramentas/.OmniRoute/x"])

    def test_pasta_de_segredo_vence_a_classe_do_nome(self):
        self.assertEqual(R.classificar(".segredos/.env.example"), "pasta-de-segredo")
        self.assertEqual(R.classificar("secrets/id_rsa"), "pasta-de-segredo")

    def test_pasta_extra_do_projeto(self):
        # O exemplo do mecanismo de pasta extra é fictício: `.omniroute` passou a ser global (contratos do lote 2, §3).
        self.assertIsNone(R.classificar(".cofre-ficticio/roteador.sqlite"))
        self.assertEqual(R.classificar(".cofre-ficticio/roteador.sqlite", [".cofre-ficticio"]), "pasta-de-segredo")
        self.assertEqual(R.classificar("ferramentas/.Cofre-Ficticio/x", [".cofre-ficticio"]), "pasta-de-segredo")

    def test_falsos_positivos_documentados(self):
        # Ficam fora por cautela e aparecem como não lidos; os fracos a conferência de conteúdo libera.
        self.assertEqual(R.classificar("src/tokenizer.py"), "fraco")
        self.assertEqual(R.classificar("estilos/tokens.css"), "fraco")
        self.assertEqual(R.classificar("chaves/id_ed25519.pub"), "forte")
        self.assertEqual(R.classificar("jogos/secret_santa.py"), "forte")

    def test_quase_certos_nao_casam(self):
        self.conferir(None, [
            "segredos.py", "scripts/regras_de_segredo.py", "env.txt", ".environment", "envs/x.txt", "keyboard.txt",
            "monkey.py", "pem.py", "tokens/x.css", "credential/x.txt", "ssh/config", "sshd_config", "my.aws/x",
            ".gitconfig", "git/config", "README.md", "src/app.py", "docker/Dockerfile", "kube/deploy.yaml"])

    def test_sem_caixa_e_com_barra_invertida(self):
        self.assertEqual(R.classificar("PROD.PEM"), "forte")
        self.assertEqual(R.classificar(".ENV"), "forte")
        self.assertEqual(R.classificar("SETUP_TOKEN"), "fraco")
        self.assertEqual(R.classificar("A/.SSH/x"), "pasta-de-segredo")
        self.assertEqual(R.classificar("a\\.ssh\\x"), "pasta-de-segredo")
        self.assertEqual(R.classificar("pasta\\.env"), "forte")

    def test_forma_de_compatibilidade_do_unicode(self):
        largo = "".join(chr(ord(c) + 0xFEE0) for c in "secret") + ".txt"  # "secret" em letras de largura cheia
        self.assertNotEqual(largo, "secret.txt")
        self.assertEqual(R.classificar(largo), "forte")

    def test_caminho_vazio(self):
        for caminho in ("", ".", "./", "//"):
            self.assertIsNone(R.classificar(caminho))

    def test_listas_explicitas_da_politica_gravada(self):
        # O manifesto do formato 3 confere com as listas do dia em que foi criado, não com as de hoje.
        self.assertIsNone(R.classificar("setup_token", fortes=[], fracos=[], exemplos=[], pastas=[]))
        self.assertEqual(R.classificar("x.cofre", fortes=["*.cofre"], fracos=[], exemplos=[], pastas=[]), "forte")

    def test_motivos(self):
        for classe in R.CLASSES:
            self.assertTrue(R.motivo(classe))
        self.assertIsNone(R.motivo(None))


class TestPastaExtra(unittest.TestCase):
    def test_valida(self):
        self.assertEqual(R.validar_pasta_extra(".omniroute"), ".omniroute")

    def test_invalidas(self):
        for nome in ("", " ", ".", "..", "a/b", "a\\b", "x\ny"):
            with self.subTest(nome=nome), self.assertRaises(ValueError):
                R.validar_pasta_extra(nome)

    def test_linha_de_comando(self):
        p = rodar_script("regras_de_segredo.py", "classificar", ".cofre-ficticio/a.db", "tokenizer.py",
                         "--pasta-segredo", ".cofre-ficticio")
        self.assertEqual(p.returncode, 0, p.stderr)
        self.assertEqual(json.loads(p.stdout), {".cofre-ficticio/a.db": "pasta-de-segredo", "tokenizer.py": "fraco"})
        p = rodar_script("regras_de_segredo.py", "classificar", "x", "--pasta-segredo", "a/b")
        self.assertEqual(p.returncode, 2)


class TestMesmaRegraNoManifesto(unittest.TestCase):
    def test_politica_do_formato_3_grava_as_listas_da_regra_unica(self):
        manifesto = carregar("manifesto")
        politica = manifesto.politica_formato3(pastas_extras=[".cofre-ficticio"])
        self.assertEqual(politica["padroes_fracos"], list(R.NOMES_FRACOS))
        self.assertEqual(set(politica["pastas_de_segredo"]), set(R.PASTAS_DE_SEGREDO) | {".cofre-ficticio"})
        # Para quem lê só o formato 2: fortes e fracos de nome em padroes_de_segredo; pastas de segredo e .git nas
        # pastas ignoradas (tudo o que o formato 3 não lê aparece como não preso).
        self.assertLessEqual(set(R.NOMES_FORTES), set(politica["padroes_de_segredo"]))
        self.assertLessEqual({g for g in R.NOMES_FRACOS if "/" not in g}, set(politica["padroes_de_segredo"]))
        self.assertLessEqual(set(R.PASTAS_DE_SEGREDO) | {".git", ".cofre-ficticio"}, set(politica["pastas_ignoradas"]))


if __name__ == "__main__":
    unittest.main()
