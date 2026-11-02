"""Conferência de segredo sem mostrar valores (1.7.10; DESENHO-1.7.10 §5.2; MELHORIAS-1.7.10, itens 0.7 e 0.8).

Antes, "há segredo verdadeiro?" só se respondia lendo o arquivo (os logs com SECRET no nome do Automaton nunca foram
lidos). `segredos.py conferir` dá um veredito por arquivo, com detector, linha e nome da chave, e nunca o valor.
Todos os valores destes testes são fictícios e montados em tempo de execução (o fonte não casa a varredura de
segredos da liberação); pastas descartáveis.
"""

from __future__ import annotations

import json
import os
import random
import shutil
import string
import tempfile
import unittest
from pathlib import Path

from apoio import criar_ligacao_dir, rodar_script


def aleatorio(n: int, alfabeto: str = string.ascii_letters + string.digits, semente: int = 0) -> str:
    """Valor fictício e reproduzível, com letras e dígitos."""
    rng = random.Random(n * 7919 + semente)
    while True:
        valor = "".join(rng.choice(alfabeto) for _ in range(n))
        if any(c.isdigit() for c in valor) and any(c.isalpha() for c in valor):
            return valor


MAIUSCULAS = string.ascii_uppercase + string.digits
PEM = "-----BEGIN " + "RSA PRIVATE" + " KEY-----"
VALORES = {
    "chave.pem": PEM + "\n" + aleatorio(64, semente=1) + "\n",
    "aws.txt": "acesso: " + "AK" + "IA" + aleatorio(16, MAIUSCULAS, 2) + "\n",
    "gh.txt": "token do github " + "gh" + "p_" + aleatorio(36, semente=3) + "\n",
    "pat.txt": "github" + "_pat_" + aleatorio(60, semente=4) + "\n",
    "slack.txt": "xo" + "xb-" + aleatorio(12, semente=5) + "-" + aleatorio(12, semente=6) + "\n",
    "openai.txt": "sk" + "-proj-" + aleatorio(40, semente=7) + "\n",
    "anthropic.txt": "sk" + "-ant-" + "api03-" + aleatorio(40, semente=8) + "\n",
    "jwt.txt": "eyJ" + aleatorio(12, semente=9) + ".eyJ" + aleatorio(12, semente=10) + "." + aleatorio(16, semente=11),
    "url.txt": "BANCO_URL=postgres://usuario:" + aleatorio(12, semente=12) + "@" + "servidor.local/db\n",
}
DETECTOR = {"chave.pem": "chave-privada", "aws.txt": "aws-chave-de-acesso", "gh.txt": "github-token",
            "pat.txt": "github-token", "slack.txt": "slack-token", "openai.txt": "openai-chave",
            "anthropic.txt": "anthropic-chave", "jwt.txt": "jwt", "url.txt": "url-com-senha"}


class _Pasta(unittest.TestCase):
    def setUp(self):
        self.base = Path(os.path.realpath(tempfile.mkdtemp(prefix="segredos-")))
        self.addCleanup(shutil.rmtree, self.base, ignore_errors=True)
        self.alvo = self.base / "alvo"
        self.alvo.mkdir()

    def escrever(self, rel: str, conteudo) -> Path:
        p = self.alvo / rel
        p.parent.mkdir(parents=True, exist_ok=True)
        p.write_bytes(conteudo if isinstance(conteudo, bytes) else conteudo.encode("utf-8"))
        return p

    def conferir(self, *extra, alvo: Path | None = None) -> tuple[int, dict, str]:
        p = rodar_script("segredos.py", "conferir", alvo or self.alvo, *extra)
        return p.returncode, (json.loads(p.stdout) if p.stdout.strip().startswith("{") else {}), p.stdout + p.stderr

    @staticmethod
    def por_caminho(rel: dict) -> dict:
        return {a["caminho"]: a for a in rel["arquivos"]}


class TestDetectores(_Pasta):
    def test_detectores_fortes_sem_mostrar_valores(self):
        for rel, texto in VALORES.items():
            self.escrever(rel, texto)
        codigo, rel, saida = self.conferir()
        self.assertEqual(codigo, 1)
        arquivos = self.por_caminho(rel)
        for nome, detector in DETECTOR.items():
            with self.subTest(nome):
                self.assertEqual(arquivos[nome]["veredito"], "indicio-forte")
                self.assertIn(detector, [a["detector"] for a in arquivos[nome]["achados"]])
        for texto in VALORES.values():
            for linha in texto.splitlines():
                for pedaco in (linha[-12:], linha[len(linha) // 2:len(linha) // 2 + 10]):
                    self.assertNotIn(pedaco, saida, "o relatório mostrou um trecho do valor")
        self.assertIn("não é prova", rel["aviso"])

    def test_atribuicao_com_nome_de_segredo_da_linha_e_o_nome_da_chave(self):
        nome, valor = "DB_" + "SENHA", aleatorio(16, semente=20)
        self.escrever(".env", f"DEBUG=1\n{nome}={valor}\nPORTA=5432\n")
        chave_api, valor_api = "chave_" + "api", aleatorio(24, semente=21)
        self.escrever("codigo.py", f'import os\n\n{chave_api} = "{valor_api}"\n')
        nome_json, valor_json = "api" + "_key", aleatorio(20, semente=22)
        self.escrever("config.json", json.dumps({"servico": "x", nome_json: valor_json}, indent=1))
        codigo, rel, saida = self.conferir()
        self.assertEqual(codigo, 1)
        arquivos = self.por_caminho(rel)
        self.assertEqual(arquivos[".env"]["achados"], [{"detector": "atribuicao-de-segredo", "linha": 2,
                                                         "chave": nome, "forca": "forte"}])
        self.assertEqual(arquivos["codigo.py"]["achados"][0]["linha"], 3)
        self.assertEqual(arquivos["codigo.py"]["achados"][0]["chave"], chave_api)
        self.assertEqual(arquivos["config.json"]["achados"][0]["chave"], nome_json)
        for v in (valor, valor_api, valor_json):
            self.assertNotIn(v, saida)

    def test_valores_de_exemplo_nao_sao_indicio(self):
        linhas = ["API_" + "TOKEN=changeme", "DB_" + "SENHA=<sua_senha_aqui>", "CHAVE_" + "API=${CHAVE_API}",
                  "URL=postgres://usuario:${SENHA_DO_BANCO}" + "@" + "servidor.local/db"]
        self.escrever(".env.example", "\n".join(linhas) + "\n")
        codigo, rel, _ = self.conferir()
        item = self.por_caminho(rel)[".env.example"]
        self.assertEqual((codigo, item["veredito"], item["achados"]), (0, "sem-indicio", []))
        self.assertGreaterEqual(item["exemplos"], 4)

    def test_codigo_comum_sem_indicio(self):
        self.escrever("README.md", "# Projeto\n\nUse a variável de ambiente para a senha.\n")
        self.escrever("tokenizer.py", "def tokenizar(texto):\n    tokens = texto.split()\n    return tokens\n"
                                      "senha = input('Senha: ')\nTIPO = 'Bearer'\n")
        codigo, rel, _ = self.conferir()
        self.assertEqual(codigo, 0, rel)
        self.assertTrue(rel["completo"])
        self.assertEqual({a["veredito"] for a in rel["arquivos"]}, {"sem-indicio"})

    def test_indicios_fracos(self):
        self.escrever("entropia.py", f'valor_interno = "{aleatorio(32, semente=30)}"\n')
        self.escrever("solto/setup_token", aleatorio(40, semente=31) + "\n")
        codigo, rel, _ = self.conferir()
        arquivos = self.por_caminho(rel)
        self.assertEqual(codigo, 1)
        self.assertEqual(arquivos["entropia.py"]["veredito"], "indicio-fraco")
        self.assertEqual(arquivos["entropia.py"]["achados"][0]["detector"], "alta-entropia")
        self.assertEqual(arquivos["solto/setup_token"]["achados"][0]["detector"], "valor-solto")

    def test_nome_de_chave_com_cara_de_token_nao_sai(self):
        nome = "k" + aleatorio(30, semente=40)
        self.escrever("estranho.py", f'{nome} = "{aleatorio(30, semente=41)}"\n')
        _, rel, saida = self.conferir()
        achado = self.por_caminho(rel)["estranho.py"]["achados"][0]
        self.assertIsNone(achado["chave"])
        self.assertNotIn(nome, saida)

    def test_detectores_fortes_novos(self):
        casos = {"stripe.txt": "STRIPE=" + "sk" + "_live_" + aleatorio(24, semente=70),
                 "google.txt": "GOOGLE=" + "AI" + "za" + aleatorio(35, semente=71),
                 "npm.txt": "// " + "npm" + "_" + aleatorio(36, semente=72),
                 "gitlab.txt": "TOKEN " + "glpat" + "-" + aleatorio(20, semente=73)}
        for rel, texto in casos.items():
            self.escrever(rel, texto + "\n")
        codigo, rel, saida = self.conferir()
        self.assertEqual(codigo, 1)
        arquivos = self.por_caminho(rel)
        esperado = {"stripe.txt": "stripe-chave", "google.txt": "google-api-chave", "npm.txt": "npm-token",
                    "gitlab.txt": "gitlab-token"}
        for nome, detector in esperado.items():
            with self.subTest(nome):
                self.assertEqual(arquivos[nome]["veredito"], "indicio-forte")
                self.assertIn(detector, [a["detector"] for a in arquivos[nome]["achados"]])

    def test_atribuicao_de_segredo_com_valor_entre_aspas_com_espaco_e_valor_curto(self):
        com_espaco = "frase " + "secreta de teste"   # valor entre aspas com espaço
        curto = "ab" + "12"                           # valor de 4 caracteres (MIN_VALOR)
        self.escrever("config.json", json.dumps({"db_" + "senha": com_espaco, "token": curto}, indent=1))
        codigo, rel, saida = self.conferir()
        self.assertEqual(codigo, 1)
        achados = self.por_caminho(rel)["config.json"]["achados"]
        chaves = {a["chave"] for a in achados if a["detector"] == "atribuicao-de-segredo"}
        self.assertEqual(chaves, {"db_senha", "token"})
        self.assertNotIn(com_espaco, saida)


class TestCobertura(_Pasta):
    def test_pulados_e_contados(self):
        self.escrever("imagem.bin", b"\x89PNG\x00\x00" + os.urandom(64))
        self.escrever("grande.txt", "x" * 3000)
        self.escrever("normal.txt", "nada aqui\n")
        self.escrever("node_modules/pacote/index.js", VALORES["gh.txt"])
        fora = self.base / "fora"
        fora.mkdir()
        (fora / "segredo.txt").write_text(VALORES["openai.txt"], encoding="utf-8")
        criar_ligacao_dir(self.alvo / "atalho", fora)
        self.escrever("h1.txt", "vínculo\n")
        try:
            os.link(self.alvo / "h1.txt", self.alvo / "h2.txt")
        except OSError as exc:
            self.skipTest(f"vínculo físico indisponível neste ambiente: {exc}")
        codigo, rel, saida = self.conferir("--teto-bytes", "2000")
        arquivos = self.por_caminho(rel)
        self.assertEqual(codigo, 1)
        self.assertFalse(rel["completo"])
        self.assertEqual((arquivos["imagem.bin"]["veredito"], arquivos["grande.txt"]["veredito"],
                          arquivos["atalho"]["veredito"], arquivos["h1.txt"]["veredito"]),
                         ("binario", "acima-do-teto", "ligacao", "vinculo-fisico"))
        self.assertEqual(arquivos["normal.txt"]["veredito"], "sem-indicio")
        self.assertEqual([p["caminho"] for p in rel["pastas_puladas"]], ["node_modules"])
        self.assertNotIn("node_modules/pacote/index.js", arquivos)
        self.assertNotIn("segredo.txt", saida)
        self.assertEqual(rel["resumo"]["binario"], 1)
        self.assertEqual(rel["resumo"]["pastas_puladas"], 1)

    def test_do_git_so_o_config(self):
        self.escrever(".git/config", "[remote \"origin\"]\n\turl = https://usuario:" + aleatorio(20, semente=50)
                      + "@" + "servidor.local/repo.git\n")
        self.escrever(".git/objects/ab/cdef", b"x\x00y")
        codigo, rel, _ = self.conferir()
        arquivos = self.por_caminho(rel)
        self.assertEqual(sorted(arquivos), [".git/config"])
        self.assertEqual(arquivos[".git/config"]["achados"][0]["detector"], "url-com-senha")
        self.assertEqual([p["caminho"] for p in rel["pastas_puladas"]], [".git"])
        self.assertEqual(codigo, 1)

    def test_arquivo_unico_e_alvo_inexistente(self):
        p = self.escrever("so.txt", VALORES["aws.txt"])
        codigo, rel, _ = self.conferir(alvo=p)
        self.assertEqual((codigo, rel["arquivos"][0]["caminho"], rel["arquivos"][0]["veredito"]),
                         (1, "so.txt", "indicio-forte"))
        codigo, _, saida = self.conferir(alvo=self.alvo / "nao-existe")
        self.assertEqual(codigo, 2, saida)

    def test_saida_em_arquivo(self):
        self.escrever("normal.txt", "nada\n")
        destino = self.base / "relatorios" / "r.json"
        codigo, rel, _ = self.conferir("--saida", destino)
        self.assertEqual(codigo, 0)
        self.assertEqual(json.loads(destino.read_text(encoding="utf-8"))["resumo"], rel["resumo"])

    def test_segredo_so_em_pasta_pulada_deixa_incompleto_e_sai_um(self):
        self.escrever("node_modules/pacote/.env", "DB_" + "SENHA=" + aleatorio(16, semente=60) + "\n")
        self.escrever("legivel.txt", "nada aqui\n")
        codigo, rel, _ = self.conferir()
        self.assertEqual(codigo, 1)             # pasta pulada pode esconder segredo: incompleto, sai 1
        self.assertFalse(rel["completo"])
        self.assertEqual(self.por_caminho(rel)["legivel.txt"]["veredito"], "sem-indicio")
        self.assertEqual([p["caminho"] for p in rel["pastas_puladas"]], ["node_modules"])

    def test_do_git_confere_fetch_head_e_logs_head(self):
        self.escrever(".git/config", "[core]\n")
        self.escrever(".git/FETCH_HEAD", "https://usuario:" + aleatorio(20, semente=52) + "@" + "servidor.local/r\n")
        self.escrever(".git/logs/HEAD", "0" * 40 + " commit\n")
        codigo, rel, _ = self.conferir()
        arquivos = self.por_caminho(rel)
        self.assertEqual(sorted(arquivos), [".git/FETCH_HEAD", ".git/config", ".git/logs/HEAD"])
        self.assertEqual(arquivos[".git/FETCH_HEAD"]["achados"][0]["detector"], "url-com-senha")
        self.assertEqual(codigo, 1)


if __name__ == "__main__":
    unittest.main()
