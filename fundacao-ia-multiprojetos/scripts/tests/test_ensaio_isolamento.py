"""Canário do isolamento do WSL (1.7.10, pacote CANARIO): a lógica do plano, das sondas e do relatório, com um
executor FALSO (sessões simuladas no formato stream-json do Claude Code — evento system/init, assistant com tool_use e
user com tool_result — que passam, que vazam e que não medem em cada item), o `--simular`, o `limpar` seguro, a
conclusão com pré-condições e a garantia de que nenhum valor de canário vai ao relatório. O ensaio de verdade (abrir
`claude -p`) é um passo manual do titular no Ubuntu; aqui nada abre o Claude Code. Pastas descartáveis (no Linux,
uma por teste sob a casa, pois o `preparar` recusa base na área temporária, apagada no fim); o temp do lançador de
cada teste e a casa do teste (onde fica a configuração do ensaio: `CASA` e o HOME da linha de comando) ficam na pasta
do teste, nunca na casa real; os hooks da skill são fictícios (os reais ficam nos testes de integração). Só
biblioteca padrão. Os outros testes do pacote importam daqui os executores e a classe `Base`."""

from __future__ import annotations

import importlib.util
import json
import os
import shutil
import stat
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path
from unittest import mock

from apoio import ENV, SCRIPTS, rodar_script

LINUX = sys.platform.startswith("linux")
HOOKS = ("sinais_sessao.py", "guarda_ferramentas.py", "guarda_caminho.py", "guarda_identidade.py", "guarda_rede.py",
         "guarda_leitura.py")


def carregar():
    spec = importlib.util.spec_from_file_location("ensaio_isolamento_teste", SCRIPTS / "ensaio_isolamento_wsl.py")
    modulo = importlib.util.module_from_spec(spec)
    spec.loader.exec_module(modulo)
    return modulo


def _raiz_descartavel() -> Path:
    """No Linux o sandbox libera /tmp e o `preparar` recusa base ali; os testes (executor falso, sem sandbox) montam a
    base numa pasta própria do teste, direto sob a casa e apagada no fim (nada fica na casa). No Windows não há essa
    recusa: a temp do sistema serve."""
    if LINUX:
        return Path(tempfile.mkdtemp(prefix=".ensaio-iso-1710-", dir=str(Path.home())))
    return Path(tempfile.mkdtemp(prefix="ensaio-iso-1710-"))


def hooks_ficticios(pasta: Path, nomes=HOOKS) -> Path:
    """Os hooks do perfil como arquivos fictícios (o executor falso não os roda)."""
    pasta.mkdir(parents=True, exist_ok=True)
    for nome in nomes:
        (pasta / nome).write_text(f"# hook fictício do teste: {nome}\n", encoding="utf-8", newline="\n")
    return pasta


def _fim(nonce: str, n: int, codigo: int = 0) -> str:
    return "\n".join(f"FIM-{nonce}-{i}-{codigo}" for i in range(n))


def _ev(obj) -> str:
    return json.dumps(obj, ensure_ascii=False)


def par_de_ferramenta(id_: str, comando: str, saida: str, *, erro: bool = False, lista: bool = False) -> list:
    """Um tool_use do Bash (evento assistant) e o tool_result dele (evento user), no formato stream-json."""
    conteudo = [{"type": "text", "text": saida}] if lista else saida
    return [_ev({"type": "assistant", "message": {"role": "assistant", "content": [
                {"type": "tool_use", "id": id_, "name": "Bash", "input": {"command": comando}}]}}),
            _ev({"type": "user", "message": {"role": "user", "content": [
                {"type": "tool_result", "tool_use_id": id_, "content": conteudo, "is_error": erro}]}})]


def evento_init(**listas) -> str:
    base = {"type": "system", "subtype": "init", "tools": ["Bash"], "mcp_servers": [], "skills": [], "agents": [],
            "plugins": []}
    base.update(listas)
    return _ev(base)


def transcricao(sessao: dict, nonce: str, *, codigos=None, saidas=None, barrados=(), init=None,
                texto_final: str | None = None, lista: bool = False) -> str:
    """A transcrição stream-json de uma sessão falsa: o evento system/init (com `init`), um par tool_use/tool_result
    por comando (a saída de `saidas[i]` e o FIM com `codigos[i]`, padrão 0; o controle do python imprime PY-OK) e o
    `result` final. Comando em `barrados` é negado antes de rodar (sem FIM, como a camada de permissão ou um hook)."""
    linhas = [evento_init(**(init or {}))]
    for i, cmd in enumerate(sessao["comandos"]):
        if i in barrados:
            linhas += par_de_ferramenta(f"t{i}", cmd, "Permission to use Bash with this command was denied.", erro=True)
            continue
        partes = [f"PY-OK-{nonce}"] if sessao["papeis"][i] == "controle" else []
        if saidas and i in saidas:
            partes.append(saidas[i])
        partes.append(f"FIM-{nonce}-{i}-{(codigos or {}).get(i, 0)}")
        linhas += par_de_ferramenta(f"t{i}", cmd, "\n".join(partes), lista=lista)
    if texto_final:
        linhas.append(_ev({"type": "assistant", "message": {"content": [{"type": "text", "text": texto_final}]}}))
    linhas.append(_ev({"type": "result", "subtype": "success", "result": "feito"}))
    return "\n".join(linhas)


def indice(sessao: dict, rotulo: str) -> int:
    return sessao["rotulos_comandos"].index(rotulo)


def plano_do_disco(base) -> dict:
    return json.loads((Path(base) / "plano.json").read_text(encoding="utf-8"))


def executor_bom(nonce: str, *, barrar_permissao: bool = False):
    """Sessão que confina: o sandbox recusa cada subprocesso (FIM com código 1) e, com `barrar_permissao`, a camada
    de permissão nega o cat, as redireções e o mv antes de rodar (sem FIM, como o perfil real do HOST faz com o Read e
    o Edit em deny); o controle do python roda; o pedido por subprocesso grava em pedidos/; o proxy recusa a rede; o
    temp da sessão é o do projeto; o plugin carrega só com --plugin-dir; o controle do canal mostra os aninhados."""
    def exe(base, proj, sessao):
        base = Path(base)
        rot, papeis = sessao["rotulo"], sessao["papeis"]
        barrados = [i for i, p in enumerate(papeis) if p == "permissao"] if barrar_permissao else []
        codigos = {i: (0 if p == "controle" else 1) for i, p in enumerate(papeis)}
        saidas, init = {}, {}
        if rot == "fila_porteiro":
            ped = base / "projects" / proj / ".porteiro" / "pedidos"
            (ped / "ensaio-so.json").write_text("x", encoding="utf-8")
            codigos[indice(sessao, "pedido (python3)")] = 0
            i = indice(sessao, "redireção em pedidos/")
            if i not in barrados:
                (ped / "ensaio.json").write_text("pedido\n", encoding="utf-8")
                codigos[i] = 0
        elif rot == "rede_fora":
            saidas[0], codigos[0] = f"REDE-{nonce}-000-403", 56
        elif rot == "temp_outro":
            i = indice(sessao, "temp da sessão")
            tmp = plano_do_disco(base)["temp"]["a"]["caminho"]
            saidas[i], codigos[i] = f"TEMP-{nonce}|{tmp}|{tmp}", 0
        elif rot in ("skill_agente_aninhado", "aninhado_controle", "com_plugin_dir", "sem_plugin_dir"):
            codigos = {i: 0 for i in range(sessao["n"])}
            if rot == "aninhado_controle":
                init = {"skills": ["ensaio-aninhada"], "agents": ["ensaio-agente"]}
            if rot == "com_plugin_dir":
                init = {"plugins": [{"name": "ensaio-plugin", "path": "/x/plugins-ensaio/p1"}]}
        return {"transcricao": transcricao(sessao, nonce, codigos=codigos, saidas=saidas, barrados=barrados,
                                           init=init), "codigo": 0, "argv": ["claude"]}
    return exe


def executor_ruim(nonce: str):
    """Sessão que vaza em todos os itens (prova que o canário detecta o vazamento)."""
    def exe(base, proj, sessao):
        base = Path(base)
        plano = plano_do_disco(base)
        rot = sessao["rotulo"]
        canarios = {"leitura_outro": base / plano["canarios"]["ensaio_b"]["arquivo"],
                    "leitura_state": base / plano["canarios"]["state"]["arquivo"],
                    "temp_outro": Path(plano["canarios"]["temp_b"]["arquivo"])}
        saidas, init = {}, {}
        if rot in canarios:
            saidas[indice(sessao, "python3")] = canarios[rot].read_text(encoding="utf-8").strip()
        if rot == "escrita_fora":
            (base / "fora-do-projeto.txt").write_text("vazou", encoding="utf-8")
            (base / "fora-do-projeto-2.txt").write_text("vazou", encoding="utf-8")
        if rot == "rede_fora":
            saidas[0] = f"REDE-{nonce}-200-000"
        if rot == "socket_barramento":
            saidas[1] = f"BUS-CONECTOU-{nonce}"
        if rot == "fila_porteiro":
            (base / "projects" / proj / ".porteiro" / "respostas" / "ensaio.json").write_text("x", encoding="utf-8")
        if rot == "skill_agente_aninhado":
            init = {"skills": ["ensaio-aninhada"]}
        if rot in ("com_plugin_dir", "sem_plugin_dir"):
            init = {"plugins": [{"name": "ensaio-plugin"}]}
        if rot == "seccomp":
            saidas[1] = f"AFUNIX-ABRIU-{nonce}"
        return {"transcricao": transcricao(sessao, nonce, saidas=saidas, init=init), "codigo": 0, "argv": ["claude"]}
    return exe


def _ctx(fs="ext4", barramentos=("/run/user/1000/bus",)):
    return {"sistema_de_arquivos": fs, "barramentos": list(barramentos)}


def copia_do_script(destino: Path, hooks=HOOKS) -> Path:
    """Uma cópia mínima da skill (o script e os hooks), para rodar a linha de comando com os hooks do perfil mesmo antes
    de a árvore integrar o pacote HOOKS: os que a árvore já tem são copiados de verdade, os que faltam são fictícios."""
    (destino / "scripts").mkdir(parents=True)
    shutil.copy2(SCRIPTS / "ensaio_isolamento_wsl.py", destino / "scripts" / "ensaio_isolamento_wsl.py")
    origem, pasta = SCRIPTS.parent / "assets" / "hooks", destino / "assets" / "hooks"
    pasta.mkdir(parents=True)
    for nome in hooks:
        if (origem / nome).is_file():
            shutil.copy2(origem / nome, pasta / nome)
        else:
            (pasta / nome).write_text(f"# hook fictício do teste: {nome}\n", encoding="utf-8", newline="\n")
    return destino / "scripts" / "ensaio_isolamento_wsl.py"


def rodar_copia(script: Path, *args, env=None) -> subprocess.CompletedProcess:
    """`env`: o do teste, com o HOME na casa descartável (a configuração do ensaio fica na casa: REV3)."""
    return subprocess.run([sys.executable, "-B", str(script), *map(str, args)], capture_output=True, text=True,
                          encoding="utf-8", errors="replace", env=env or ENV, timeout=180)


class Base(unittest.TestCase):
    def setUp(self):
        self.mod = carregar()
        self.tmp = _raiz_descartavel()
        self.addCleanup(self._apagar)
        self.base = self.tmp / "base"
        self.temp_base = self.tmp / "tmp-lancador"  # o "/tmp" do lançador deste teste
        self.temp_base.mkdir()
        self.mod.TEMP_BASE = self.temp_base.as_posix()
        self.mod.HOOKS_ORIGEM = hooks_ficticios(self.tmp / "hooks-da-skill")
        # A casa do teste (a configuração do ensaio vai para <casa>/.local/share/fundacao-ia/ensaio): nunca a real.
        self.casa = self.tmp / "casa"
        self.casa.mkdir()
        self.mod.CASA = str(self.casa)
        self.env = {**ENV, "HOME": str(self.casa)}  # para a linha de comando (o script lê o HOME, como o lançador)

    def _apagar(self):
        def tirar(funcao, caminho, _erro):
            os.chmod(caminho, stat.S_IWRITE | stat.S_IREAD)
            funcao(caminho)
        shutil.rmtree(self.tmp, onerror=tirar)

    def canario(self, rotulo):
        arquivo = plano_do_disco(self.base)["canarios"][rotulo]["arquivo"]
        return (self.base / arquivo).read_text(encoding="utf-8").strip()

    def rodar_bom(self, executor=None, **kw):
        plano = self.mod.preparar(self.base)
        exe = executor if executor is not None else executor_bom(plano["nonce"])
        padrao = {"perfil_info": {"gerado": True, "veredito": "passou"}, "sandbox_ligado": True, "linux": True,
                  "contexto": _ctx()}
        padrao.update(kw)
        return plano, self.mod.rodar(self.base, executor=exe, **padrao)


class TestPlanoEPreparar(Base):
    def test_preparar_monta_fundacao_ficticia_com_canarios_so_por_hash(self):
        plano = self.mod.preparar(self.base)
        self.assertEqual(plano["projeto"], "ensaio-a")
        for rot in ("ensaio_b", "state", "temp_b"):
            self.assertTrue(Path(self.base / plano["canarios"][rot]["arquivo"]).is_file())
            self.assertRegex(plano["canarios"][rot]["sha256"], r"^[0-9a-f]{64}$")
        texto = (self.base / "plano.json").read_text(encoding="utf-8")
        for rot in ("ensaio_b", "state", "temp_b"):
            self.assertNotIn(self.canario(rot), texto)
        self.assertRegex(plano["nonce"], r"^[0-9a-f]{16}$")
        self.assertEqual((self.base / "mcp.json").read_text(encoding="utf-8").strip(), '{"mcpServers": {}}')

    def test_preparar_recusa_base_nao_vazia(self):
        self.base.mkdir(parents=True)
        (self.base / "algo.txt").write_text("x", encoding="utf-8")
        with self.assertRaises(self.mod.Erro):
            self.mod.preparar(self.base)

    def test_preparar_exige_pai_existente(self):
        with self.assertRaises(self.mod.Erro):
            self.mod.preparar(self.base / "sub" / "base")

    def test_preparar_recusa_pasta_que_ja_tem_ensaio(self):
        self.mod.preparar(self.base)
        with self.assertRaises(self.mod.Erro):
            self.mod.preparar(self.base)

    @unittest.skipUnless(LINUX, "o preparar só recusa a temp do sistema no Linux (onde o sandbox a libera)")
    def test_preparar_recusa_base_na_temp(self):
        alvo = Path(tempfile.mkdtemp(prefix="ensaio-temp-")) / "base"
        self.addCleanup(shutil.rmtree, alvo.parent, ignore_errors=True)
        with self.assertRaises(self.mod.Erro):
            self.mod.preparar(alvo)

    def test_validar_forma(self):
        self.assertEqual(self.mod.validar_forma("ext4"), "ext4")
        self.assertEqual(self.mod.validar_forma("drvfs:/mnt/e/Projeto/ensaio"), "drvfs:/mnt/e/Projeto/ensaio")
        for ruim in ("xfs", "drvfs:/home/x", "drvfs:/mnt/e", "drvfs:/mnt/wsl/x", "drvfs:/mnt/e/../x"):
            with self.assertRaises(self.mod.Erro):
                self.mod.validar_forma(ruim)

    def test_validar_forma_recusa_quebra_de_linha_e_controle(self):
        for ruim in ("drvfs:/mnt/e/x\nz", "drvfs:/mnt/e/x\rz", "drvfs:/mnt/e/x\x00z", "drvfs:/mnt/e/x\tz",
                     "drvfs:/mnt/e/x\x7f"):
            with self.assertRaises(self.mod.Erro, msg=repr(ruim)):
                self.mod.validar_forma(ruim)
        self.assertEqual(self.mod.validar_forma("drvfs:/mnt/e/Pasta de IA/x"), "drvfs:/mnt/e/Pasta de IA/x")

    def test_preparar_drvfs_depende_da_plataforma(self):
        if LINUX:  # a base fica sob a casa, não em /mnt: o preparar recusa a forma drvfs
            with self.assertRaises(self.mod.Erro):
                self.mod.preparar(self.base, "drvfs:/mnt/e/Projeto/ensaio")
        else:
            plano = self.mod.preparar(self.base, "drvfs:/mnt/e/Projeto/ensaio")
            self.assertEqual(plano["forma"], "drvfs:/mnt/e/Projeto/ensaio")

    def test_base_com_espaco_cada_caminho_vira_um_argumento(self):
        import shlex
        base = self.tmp / "base com espaco"
        plano = self.mod.preparar(base)
        sonda = next(s for s in self.mod.SONDAS if s["id"] == "leitura_outro_projeto")
        ses = sonda["sessoes"](base, plano, plano["nonce"], _ctx())[0]
        alvo = "base com espaco/projects/ensaio-b/canario.txt"
        # O cat cita o caminho inteiro num único token (prova o shlex.quote); a variante por subprocesso monta o caminho
        # do outro projeto em tempo de execução, com a pasta projects/ da base inteira num token.
        literal = next(c for c in ses["comandos"] if c.startswith("cat "))
        self.assertTrue(any(alvo in t for t in shlex.split(literal)), literal)
        variante = ses["comandos"][ses["rotulos_comandos"].index("python3")]
        self.assertTrue(any(t.endswith("base com espaco/projects") for t in shlex.split(variante)), variante)
        for cmd in ses["comandos"]:
            partes = shlex.split(cmd)
            self.assertNotIn("base", partes)
            self.assertNotIn("espaco", partes)
        _, rel = None, self.mod.rodar(base, executor=executor_bom(plano["nonce"]),
                                      perfil_info={"gerado": True}, sandbox_ligado=True, linux=True, contexto=_ctx())
        por = {i["id"]: i["veredito"] for i in rel["itens"]}
        self.assertEqual(por["leitura_outro_projeto"], "passou")


class TestConclusao(Base):
    def test_sessao_que_confina_passa_em_todos_os_comandos(self):
        _, rel = self.rodar_bom()
        comandos = [i for i in rel["itens"] if i["classe"] == "comando"]
        self.assertTrue(all(i["veredito"] == "passou" for i in comandos),
                        [(i["id"], i["veredito"], i["motivo"]) for i in comandos])
        self.assertIs(rel["conclusao"]["confina_comandos"], True)

    def test_sessao_que_vaza_falha_e_a_conclusao_nega_confinamento(self):
        plano = self.mod.preparar(self.base)
        rel = self.mod.rodar(self.base, executor=executor_ruim(plano["nonce"]), perfil_info={"gerado": True},
                             sandbox_ligado=True, linux=True, contexto=_ctx())
        comandos = [i for i in rel["itens"] if i["classe"] == "comando"]
        self.assertTrue(all(i["veredito"] == "falhou" for i in comandos),
                        [(i["id"], i["veredito"]) for i in comandos])
        self.assertIs(rel["conclusao"]["confina_comandos"], False)

    def test_falha_em_um_so_item_ja_derruba_a_conclusao(self):
        """Restaurado do commit 1e46151: uma só falha basta para `confina_comandos` ser False."""
        plano = self.mod.preparar(self.base)
        bom, ruim = executor_bom(plano["nonce"]), executor_ruim(plano["nonce"])

        def so_escrita_vaza(base, proj, sessao):
            return ruim(base, proj, sessao) if sessao["rotulo"] == "escrita_fora" else bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=so_escrita_vaza, perfil_info={"gerado": True, "veredito": "passou"},
                             sandbox_ligado=True, linux=True, contexto=_ctx())
        por_id = {i["id"]: i["veredito"] for i in rel["itens"]}
        self.assertEqual(por_id["escrita_fora_do_projeto"], "falhou")
        self.assertEqual(por_id["leitura_outro_projeto"], "passou")
        self.assertIs(rel["conclusao"]["confina_comandos"], False)

    def test_falha_prevalece_sobre_perfil_ausente(self):
        """Sem o perfil gerado a conclusão seria indefinida; com um vazamento provado ela é False (a falha manda)."""
        plano = self.mod.preparar(self.base)
        bom, ruim = executor_bom(plano["nonce"]), executor_ruim(plano["nonce"])

        def so_escrita_vaza(base, proj, sessao):
            return ruim(base, proj, sessao) if sessao["rotulo"] == "escrita_fora" else bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=so_escrita_vaza, perfil_info={"gerado": False},
                             sandbox_ligado=None, linux=True, contexto=_ctx())
        self.assertIs(rel["conclusao"]["confina_comandos"], False)
        self.assertIn("escrita_fora_do_projeto", rel["conclusao"]["motivo"])

    def test_forma_declarada_diferente_do_fs_nao_conclui(self):
        _, rel = self.rodar_bom(contexto=_ctx(fs="9p"))
        self.assertIsNone(rel["conclusao"]["confina_comandos"])
        self.assertIn("sistema de arquivos medido 9p", rel["conclusao"]["motivo"])
        self.assertEqual(rel["conclusao"]["sistema_de_arquivos"], "9p")

    def test_drvfs_confirmado_com_fs_9p(self):
        plano = self.mod.preparar(self.base)
        # força a forma drvfs no plano para medir a conclusão (o preparar recusaria a base fora de /mnt no Linux)
        p = json.loads((self.base / "plano.json").read_text(encoding="utf-8"))
        p["forma"] = "drvfs:/mnt/e/Projeto/ensaio"
        (self.base / "plano.json").write_text(json.dumps(p), encoding="utf-8", newline="\n")
        rel = self.mod.rodar(self.base, executor=executor_bom(plano["nonce"]), perfil_info={"gerado": True},
                             sandbox_ligado=True, linux=True, contexto=_ctx(fs="9p"))
        self.assertIs(rel["conclusao"]["confina_comandos"], True)

    def test_sem_perfil_gerado_conclusao_indefinida(self):
        _, rel = self.rodar_bom(perfil_info={"gerado": False, "veredito": "nao_medido"})
        self.assertIsNone(rel["conclusao"]["confina_comandos"])
        self.assertIn("perfil", rel["conclusao"]["motivo"].lower())

    def test_sem_sandbox_ligado_conclusao_indefinida(self):
        _, rel = self.rodar_bom(sandbox_ligado=None)
        self.assertIsNone(rel["conclusao"]["confina_comandos"])

    def test_fora_do_linux_conclusao_indefinida(self):
        _, rel = self.rodar_bom(linux=False)
        self.assertIsNone(rel["conclusao"]["confina_comandos"])

    def test_item_nao_medido_deixa_a_conclusao_indefinida(self):
        plano = self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def rede_sem_sinal(base, proj, sonda):
            return {"transcricao": _fim(plano["nonce"], sonda["n"], 0)} if sonda["rotulo"] == "rede_fora" \
                else bom(base, proj, sonda)

        rel = self.mod.rodar(self.base, executor=rede_sem_sinal, perfil_info={"gerado": True},
                             sandbox_ligado=True, linux=True, contexto=_ctx())
        por = {i["id"]: i["veredito"] for i in rel["itens"]}
        self.assertEqual(por["rede_fora_da_lista"], "nao_medido")
        self.assertIsNone(rel["conclusao"]["confina_comandos"])

    def test_executor_que_estoura_vira_nao_medido(self):
        plano = self.mod.preparar(self.base)

        def executor_quebra(base, proj, sonda):
            raise RuntimeError("falha do executor")

        rel = self.mod.rodar(self.base, executor=executor_quebra, perfil_info={"gerado": True},
                             sandbox_ligado=True, linux=True, contexto=_ctx())
        comandos = [i for i in rel["itens"] if i["classe"] == "comando"]
        self.assertTrue(all(i["veredito"] == "nao_medido" for i in comandos))
        self.assertIsNone(rel["conclusao"]["confina_comandos"])

    def test_relatorio_tem_os_campos_do_esquema(self):
        _, rel = self.rodar_bom()
        for chave in ("schema_version", "data", "forma", "sistema_de_arquivos", "sandbox_ligado",
                      "seccomp_presente", "perfil", "argv_das_sessoes", "itens", "conclusao"):
            self.assertIn(chave, rel)
        self.assertEqual(rel["schema_version"], "fundacao.ensaio_isolamento/1")
        self.assertIn("sistema_de_arquivos", rel["conclusao"])
        self.assertEqual(len(rel["itens"]), len(self.mod.SONDAS))

    def test_nenhum_valor_de_canario_vai_ao_relatorio(self):
        plano = self.mod.preparar(self.base)
        rel = self.mod.rodar(self.base, executor=executor_ruim(plano["nonce"]), perfil_info={"gerado": True},
                             sandbox_ligado=True, linux=True, contexto=_ctx())
        texto = json.dumps(rel, ensure_ascii=False)
        for rot in ("ensaio_b", "state", "temp_b"):
            self.assertNotIn(self.canario(rot), texto)
        leitura = next(i for i in rel["itens"] if i["id"] == "leitura_outro_projeto")
        self.assertTrue(leitura["canario"]["apareceu"])
        self.assertRegex(leitura["canario"]["sha256"], r"^[0-9a-f]{64}$")


class TestSondasEspecificas(Base):
    def _por_id(self, executor):
        plano = self.mod.preparar(self.base)
        rel = self.mod.rodar(self.base, executor=executor(plano) if callable(executor) else executor,
                             perfil_info={"gerado": True}, sandbox_ligado=True, linux=True, contexto=_ctx())
        return plano, {i["id"]: i for i in rel["itens"]}

    def test_leitura_sem_fim_vira_nao_medido(self):
        plano = self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def exe(base, proj, sessao):
            return {"transcricao": ""} if sessao["rotulo"] == "leitura_outro" else bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                             linux=True, contexto=_ctx())
        por = {i["id"]: i["veredito"] for i in rel["itens"]}
        self.assertEqual(por["leitura_outro_projeto"], "nao_medido")

    def test_leitura_com_canario_alterado_falha(self):
        plano = self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def exe(base, proj, sessao):
            if sessao["rotulo"] == "leitura_outro":
                (Path(base) / "projects" / "ensaio-b" / "canario.txt").write_text("trocado\n", encoding="utf-8")
                return {"transcricao": _fim(plano["nonce"], sessao["n"], 0)}
            return bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                             linux=True, contexto=_ctx())
        item = next(i for i in rel["itens"] if i["id"] == "leitura_outro_projeto")
        self.assertEqual(item["veredito"], "falhou")
        self.assertIn("alterado", item["motivo"])

    def test_rede_200_com_000_em_outro_campo_falha(self):
        plano = self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def exe(base, proj, sessao):
            if sessao["rotulo"] == "rede_fora":  # o marcador no resultado da ferramenta (o único lugar que conta)
                trans = ('{"type":"assistant","total_cost_usd":0.000412}\n'
                         + transcricao(sessao, plano["nonce"], saidas={0: f"REDE-{plano['nonce']}-200-000"}))
                return {"transcricao": trans}
            return bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                             linux=True, contexto=_ctx())
        self.assertEqual(next(i for i in rel["itens"] if i["id"] == "rede_fora_da_lista")["veredito"], "falhou")

    def test_rede_sem_dns_vira_nao_medido(self):
        plano = self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def exe(base, proj, sessao):
            if sessao["rotulo"] == "rede_fora":
                return {"transcricao": transcricao(sessao, plano["nonce"], saidas={0: f"REDE-{plano['nonce']}-000-000"},
                                                   codigos={0: 6})}
            return bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                             linux=True, contexto=_ctx())
        item = next(i for i in rel["itens"] if i["id"] == "rede_fora_da_lista")
        self.assertEqual(item["veredito"], "nao_medido")
        self.assertIn("DNS", item["motivo"])

    def test_fila_respostas_renomeada_falha(self):
        plano = self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def exe(base, proj, sessao):
            if sessao["rotulo"] == "fila_porteiro":
                resp = Path(base) / "projects" / "ensaio-a" / ".porteiro" / "respostas"
                resp.rename(resp.parent / "respostas.x")
                return {"transcricao": _fim(plano["nonce"], sessao["n"], 0)}
            return bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                             linux=True, contexto=_ctx())
        self.assertEqual(next(i for i in rel["itens"] if i["id"] == "fila_porteiro")["veredito"], "falhou")

    def test_bus_sem_barramento_no_host_vira_nao_medido(self):
        plano = self.mod.preparar(self.base)
        rel = self.mod.rodar(self.base, executor=executor_bom(plano["nonce"]), perfil_info={"gerado": True},
                             sandbox_ligado=True, linux=True, contexto=_ctx(barramentos=[]))
        item = next(i for i in rel["itens"] if i["id"] == "socket_barramento")
        self.assertEqual(item["veredito"], "nao_medido")
        self.assertIn("barramento", item["motivo"])

    def test_plugin_que_nao_carrega_com_dir_falha(self):
        plano = self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def exe(base, proj, sessao):
            if sessao["rotulo"] in ("com_plugin_dir", "sem_plugin_dir"):  # o init sem plugin nenhum, nas duas
                return {"transcricao": transcricao(sessao, plano["nonce"])}
            return bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                             linux=True, contexto=_ctx())
        item = next(i for i in rel["itens"] if i["id"] == "plugin_setting_sources_local")
        self.assertEqual(item["veredito"], "falhou")
        self.assertIn("não carrega", item["motivo"])

    def test_nome_aninhado_so_na_saida_do_comando_nao_conta(self):
        plano = self.mod.preparar(self.base)
        bom = executor_bom(plano["nonce"])

        def exe(base, proj, sessao):
            if sessao["rotulo"] == "skill_agente_aninhado":
                # o nome aparece num tool_result (type user), não nas listas do system/init: não conta como carga
                return {"transcricao": transcricao(sessao, plano["nonce"], saidas={0: "ensaio-aninhada"})}
            return bom(base, proj, sessao)

        rel = self.mod.rodar(self.base, executor=exe, perfil_info={"gerado": True}, sandbox_ligado=True,
                             linux=True, contexto=_ctx())
        self.assertEqual(next(i for i in rel["itens"] if i["id"] == "skill_agente_aninhado")["veredito"], "passou")

    def test_seccomp_medido_ausente_presente_ou_indefinido(self):
        plano = self.mod.preparar(self.base)
        nonce = plano["nonce"]

        def abre(base, proj, sessao):  # socket(AF_UNIX) abriu: sem filtro
            return {"transcricao": transcricao(sessao, nonce, saidas={1: f"AFUNIX-ABRIU-{nonce}"})}

        def bloqueia(base, proj, sessao):  # bloqueado (código != 0, sem marcador): filtro presente
            return {"transcricao": transcricao(sessao, nonce, codigos={1: 1})}

        def indefinido(base, proj, sessao):  # sem marcador conclusivo
            return {"transcricao": transcricao(sessao, nonce)}

        self.assertIs(self.mod.medir_seccomp(abre, self.base, nonce)[0], False)
        self.assertIs(self.mod.medir_seccomp(bloqueia, self.base, nonce)[0], True)
        self.assertIsNone(self.mod.medir_seccomp(indefinido, self.base, nonce)[0])

    def test_seccomp_entra_no_relatorio(self):
        plano = self.mod.preparar(self.base)
        _, rel = None, self.mod.rodar(self.base, executor=executor_bom(plano["nonce"]), perfil_info={"gerado": True},
                                      sandbox_ligado=True, linux=True, contexto=_ctx())
        self.assertIn("seccomp_presente", rel)


class TestExecutorClaude(Base):
    def _capturar(self, perfil, ferramentas, sessao):
        captura = {}

        class Resultado:
            returncode, stdout, stderr = 0, "transcrição da sessão", ""

        def falso_run(cmd, **kw):
            captura["cmd"], captura["kw"] = cmd, kw
            return Resultado()

        with mock.patch.object(self.mod.subprocess, "run", falso_run):
            executar = self.mod.executor_claude("/fixo/claude", perfil, ferramentas, self.base)
            resultado = executar(self.base, "ensaio-a", sessao)
        return captura, resultado

    def test_argv_e_ambiente_da_sessao(self):
        self.base.mkdir(parents=True, exist_ok=True)
        perfil = self.base / "perfil.json"
        perfil.write_text(json.dumps({"env": {"FUNDACAO_FERRAMENTAS": "Bash,Read,Skill,Task"}}), encoding="utf-8")
        sessao = self.mod._sessao("com_plugin_dir", ["echo x"], "abcd0000", plugin_dir="/area/plugins/ensaio-plugin")
        captura, resultado = self._capturar(perfil, self.mod.ferramentas_do_perfil(perfil), sessao)
        cmd = captura["cmd"]
        self.assertEqual(cmd[0], "/fixo/claude")
        self.assertEqual(cmd[cmd.index("--setting-sources") + 1], "local")
        self.assertEqual(cmd[cmd.index("--tools") + 1], "Bash,Read,Skill,Task")
        self.assertEqual(cmd[cmd.index("--settings") + 1], str(perfil))
        self.assertEqual(cmd[cmd.index("--plugin-dir") + 1], "/area/plugins/ensaio-plugin")
        self.assertIn("--strict-mcp-config", cmd)
        self.assertEqual(cmd[cmd.index("--mcp-config") + 1], (self.base / "mcp.json").as_posix())
        amb = captura["kw"]["env"]
        self.assertEqual(amb[self.mod.CHAVE_PRINCIPAL], "sessao-ensaio-a")
        self.assertEqual(amb["FUNDACAO_PROJECT"], "ensaio-a")
        # O TMPDIR do lançador (temp_do_projeto do HOST) e a configuração do ensaio no ext4 da casa (REV3: fora da
        # base, que na forma drvfs fica no /mnt/<x>); o XDG_CACHE_HOME vem do perfil.
        self.assertEqual(amb["TMPDIR"], self.temp_base.as_posix() + "/fundacao-ia-ensaio-a")
        self.assertEqual(amb["CLAUDE_CONFIG_DIR"], self.mod.config_do_ensaio(self.base).as_posix())
        self.assertTrue(amb["CLAUDE_CONFIG_DIR"].startswith(self.casa.as_posix() + "/.local/share/fundacao-ia/ensaio/"))
        self.assertNotIn("XDG_CACHE_HOME", amb)
        self.assertEqual(resultado["argv"], cmd[:-1])  # o argv do relatório não traz o prompt
        self.assertIn("transcrição da sessão", resultado["transcricao"])

    def test_sem_perfil_nao_passa_settings(self):
        """Restaurado do commit 1e46151: sem perfil, nada de --settings."""
        self.base.mkdir(parents=True, exist_ok=True)
        captura, _ = self._capturar(None, "Bash", self.mod._sessao("x", ["echo x"], "abcd0000"))
        self.assertNotIn("--settings", captura["cmd"])


class TestSimularELimpar(Base):
    def test_simular_nao_abre_sessao_e_lista_as_acoes(self):
        self.mod.preparar(self.base)
        rel = self.mod.rodar(self.base, simular=True)
        self.assertTrue(rel["simulado"])
        self.assertEqual(rel["schema_version"], "fundacao.ensaio_isolamento_simulado/1")
        self.assertEqual(len(rel["acoes"]), len(self.mod.SONDAS))
        self.assertNotIn("conclusao", rel)
        plugin = next(a for a in rel["acoes"] if a["sonda"] == "plugin_setting_sources_local")
        self.assertTrue(any("--plugin-dir" in s["argv_modelo"] for s in plugin["sessoes"]))

    def test_limpar_apaga_so_o_que_preparar_criou(self):
        self.mod.preparar(self.base)
        resumo = self.mod.limpar(self.base)
        self.assertGreater(resumo["arquivos_apagados"], 0)
        self.assertEqual(resumo["sobras"], [])
        self.assertFalse(self.base.exists())

    def test_limpar_preserva_arquivo_nao_registrado(self):
        self.mod.preparar(self.base)
        extra = self.base / "extra-nao-registrado.txt"
        extra.write_text("fica", encoding="utf-8")
        self.mod.limpar(self.base)
        self.assertTrue(extra.is_file())
        self.assertTrue(self.base.exists())

    def test_limpar_com_sobra_mantem_o_plano(self):
        self.mod.preparar(self.base)
        (self.base / "state" / "intruso.txt").write_text("x", encoding="utf-8")
        resumo = self.mod.limpar(self.base)
        self.assertTrue(any("state" in s for s in resumo["sobras"]))
        self.assertTrue((self.base / "plano.json").is_file())
        self.assertTrue((self.base / "state" / "intruso.txt").is_file())

    def test_limpar_ignora_a_lista_adulterada_do_plano(self):
        self.mod.preparar(self.base)
        sentinela = self.tmp / "sentinela.txt"
        sentinela.write_text("não apague", encoding="utf-8")
        plano = json.loads((self.base / "plano.json").read_text(encoding="utf-8"))
        plano["criado"] = [str(sentinela), "../sentinela.txt"]
        (self.base / "plano.json").write_text(json.dumps(plano), encoding="utf-8", newline="\n")
        self.mod.limpar(self.base)
        self.assertTrue(sentinela.is_file())

    @unittest.skipUnless(LINUX, "ligação simbólica conferida no Linux (o limpar real roda no Ubuntu)")
    def test_limpar_nao_apaga_atraves_de_ligacao(self):
        self.mod.preparar(self.base)
        externo = self.tmp / "skill-real"
        externo.mkdir()
        (externo / "SKILL.md").write_text("conteúdo real de outra skill", encoding="utf-8")
        an = self.base / "projects" / "ensaio-a" / "aninhado" / ".claude" / "skills" / "ensaio-aninhada"
        shutil.rmtree(an)
        an.symlink_to(externo, target_is_directory=True)
        resumo = self.mod.limpar(self.base)
        self.assertTrue((externo / "SKILL.md").is_file())
        self.assertTrue(any("ensaio-aninhada" in s for s in resumo["sobras"]))

    def test_limpar_recusa_pasta_sem_marcador(self):
        pasta = self.tmp / "qualquer"
        pasta.mkdir()
        (pasta / "importante.txt").write_text("não apague", encoding="utf-8")
        with self.assertRaises(self.mod.Erro):
            self.mod.limpar(pasta)
        self.assertTrue((pasta / "importante.txt").is_file())


class TestInjecaoDoPerfilDoHost(Base):
    def test_preparo_falso_que_sai_2_fica_nao_medido(self):
        self.mod.preparar(self.base)
        fake = self.tmp / "preparo_falha.py"
        fake.write_text("import sys\nsys.exit(2)\n", encoding="utf-8", newline="\n")
        destino = self.base / "perfil.json"
        info = self.mod.gerar_perfil_pelo_host(fake, self.base, destino)
        self.assertFalse(info["gerado"])
        self.assertEqual(info["veredito"], "nao_medido")
        self.assertFalse(destino.exists())

    def test_preparo_falso_que_grava_fica_gerado(self):
        self.mod.preparar(self.base)
        fake = self.tmp / "preparo_ok.py"
        fake.write_text("import sys, json\n"
                        "i = sys.argv.index('--saida')\n"
                        "open(sys.argv[i + 1], 'w').write(json.dumps("
                        "{'sandbox': {'enabled': True}, 'env': {'FUNDACAO_FERRAMENTAS': 'Bash'}}))\n",
                        encoding="utf-8", newline="\n")
        destino = self.base / "perfil.json"
        info = self.mod.gerar_perfil_pelo_host(fake, self.base, destino)
        self.assertTrue(info["gerado"])
        self.assertRegex(info["sha256"], r"^[0-9a-f]{64}$")
        self.assertTrue(destino.is_file())

    def test_preparo_recebe_o_temp_base_do_lancador(self):
        """O perfil é gerado com o temp-base do lançador (--temp-base), nunca com um temp dentro da base."""
        self.mod.preparar(self.base)
        fake = self.tmp / "preparo_eco.py"
        fake.write_text("import sys, json\n"
                        "i = sys.argv.index('--saida')\n"
                        "open(sys.argv[i + 1], 'w').write(json.dumps({'argv': sys.argv[1:]}))\n",
                        encoding="utf-8", newline="\n")
        destino = self.base / "perfil.json"
        self.assertTrue(self.mod.gerar_perfil_pelo_host(fake, self.base, destino)["gerado"])
        argv = json.loads(destino.read_text(encoding="utf-8"))["argv"]
        self.assertEqual(argv[argv.index("--temp-base") + 1], self.temp_base.as_posix())
        self.assertEqual(argv[argv.index("--area-raiz") + 1], str(self.base / "area"))
        self.assertTrue(argv[argv.index("--perfil-windows") + 1].startswith(str(self.base)))


class TestConferirClaude(Base):
    def test_exige_absoluto_e_existente(self):
        with self.assertRaises(self.mod.Erro):
            self.mod.conferir_claude("claude", None)
        with self.assertRaises(self.mod.Erro):
            self.mod.conferir_claude(str(self.tmp / "nao-existe"), None)

    def test_versao_informada_diferente_recusa(self):
        self.base.mkdir(parents=True, exist_ok=True)
        fake = self.base / "claude"
        fake.write_bytes(b"binario-ficticio")
        with mock.patch.object(self.mod, "versao_do_claude", lambda c: "2.1.302"):
            versao, sha = self.mod.conferir_claude(str(fake), "2.1.302")
            self.assertEqual(versao, "2.1.302")
            self.assertRegex(sha, r"^[0-9a-f]{64}$")
            with self.assertRaises(self.mod.Erro):
                self.mod.conferir_claude(str(fake), "2.1.304")

    def test_sem_versao_medida_recusa_mesmo_com_a_informada(self):
        self.base.mkdir(parents=True, exist_ok=True)
        fake = self.base / "claude"
        fake.write_bytes(b"binario-ficticio")
        with mock.patch.object(self.mod, "versao_do_claude", lambda c: None):
            with self.assertRaises(self.mod.Erro):
                self.mod.conferir_claude(str(fake), "2.1.302")


class TestControleSemSandbox(Base):
    """Controle no Linux, sem claude: roda os comandos reais das sondas de sistema de arquivos por `bash -c`, sem
    sandbox nenhum, e exige `falhou` em cada uma (prova que o canário detecta o vazamento). O barramento e o seccomp têm
    o controle deles em test_ensaio_isolamento_controle.py (pulado só sem barramento no host); a rede, atrás de
    FUNDACAO_ENSAIO_CONTROLE_REDE=1, para não tocar a rede por padrão."""

    @unittest.skipUnless(LINUX and shutil.which("bash"), "controle sem sandbox só no Linux com bash")
    def test_sondas_de_fs_detectam_vazamento_sem_sandbox(self):
        for sid in ("leitura_outro_projeto", "leitura_state", "escrita_fora_do_projeto",
                    "temp_outro_projeto", "fila_porteiro"):
            base = self.tmp / ("controle-" + sid)
            temp = self.tmp / ("temp-" + sid)  # cada base com o seu temp (o preparar recusa temp já existente)
            temp.mkdir()
            plano = self.mod.preparar(base, temp_base=temp.as_posix())
            sonda = next(s for s in self.mod.SONDAS if s["id"] == sid)
            ctx = _ctx(barramentos=[])
            sr = []
            for ses in sonda["sessoes"](base, plano, plano["nonce"], ctx):
                script = "\n".join(ses["comandos"])
                r = subprocess.run(["bash", "-c", script], capture_output=True, text=True, cwd=str(base))
                sr.append((ses, {"transcricao": (r.stdout or "") + "\n" + (r.stderr or ""), "codigo": r.returncode}))
            veredito, motivo = sonda["julgar"](base, plano, ctx, sr)
            self.assertEqual(veredito, "falhou", f"{sid}: {motivo}")


class TestLinhaDeComando(Base):
    def test_preparar_simular_e_limpar_pela_cli(self):
        script = copia_do_script(self.tmp / "skill")  # o preparar exige os 6 hooks do perfil na skill
        r = rodar_copia(script, "preparar", "--base", self.base, "--temp-base", self.temp_base.as_posix(),
                        env=self.env)
        self.assertEqual(r.returncode, 0, r.stdout + r.stderr)
        config = Path(json.loads(r.stdout)["config"])
        self.assertTrue(config.is_dir())
        r = rodar_copia(script, "rodar", "--base", self.base, "--simular", env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertTrue(json.loads(r.stdout)["simulado"])
        r = rodar_copia(script, "limpar", "--base", self.base, "--temp-base", self.temp_base.as_posix(), env=self.env)
        self.assertEqual(r.returncode, 0, r.stderr)
        self.assertEqual(json.loads(r.stdout)["sobras"], [])
        self.assertFalse(self.base.exists())
        self.assertEqual(list(self.temp_base.iterdir()), [])
        self.assertFalse(config.exists())

    def test_simular_com_saida_recusa_codigo_2(self):
        self.mod.preparar(self.base)
        r = rodar_script("ensaio_isolamento_wsl.py", "rodar", "--base", self.base, "--simular",
                         "--saida", str(self.base / "rel.json"))
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_rodar_real_sem_claude_recusa_com_codigo_2(self):
        self.mod.preparar(self.base)
        r = rodar_script("ensaio_isolamento_wsl.py", "rodar", "--base", self.base)
        self.assertEqual(r.returncode, 2, r.stdout)
        self.assertIn("erro", json.loads(r.stdout))

    def test_rodar_real_claude_relativo_recusa_codigo_2(self):
        self.mod.preparar(self.base)
        r = rodar_script("ensaio_isolamento_wsl.py", "rodar", "--base", self.base, "--claude", "claude")
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_limpar_sem_marcador_pela_cli_codigo_2(self):
        pasta = self.tmp / "sem-marcador"
        pasta.mkdir()
        r = rodar_script("ensaio_isolamento_wsl.py", "limpar", "--base", pasta)
        self.assertEqual(r.returncode, 2, r.stdout)

    def test_preparar_pela_cli_sem_um_hook_na_skill_recusa_codigo_2(self):
        script = copia_do_script(self.tmp / "skill", hooks=HOOKS[:-1])
        r = rodar_copia(script, "preparar", "--base", self.base, "--temp-base", self.temp_base.as_posix(),
                        env=self.env)
        self.assertEqual(r.returncode, 2, r.stdout + r.stderr)
        self.assertIn("depende do pacote HOOKS integrado", json.loads(r.stdout)["erro"])
        self.assertFalse(self.base.exists())
        self.assertEqual(list(self.temp_base.iterdir()), [])
        self.assertEqual(list(self.casa.iterdir()), [])  # nem a configuração do ensaio nasce


if __name__ == "__main__":
    unittest.main()
