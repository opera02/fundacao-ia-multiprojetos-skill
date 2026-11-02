"""Rastro do executor na 1.7.10 (seção 2 do escopo): a classe do P1 fora do grep/rg, o cd de `{ cd X; }` (F5) e os
grupos de opções longos. Os comandos são os da sonda de 31/10/2026 (mapa do ciclo de liberação, fatos 25 e 26) e o
observado do P1; a leitura real da bancada no mesmo comando continua "contaminada". Sem modelo nem rede. As listas
fixas do CI-F7 são conferidas ao vivo com o --sandbox do GNU sed e do gawk quando estão no PATH (o --sandbox recusa a
E/S antes de ela rodar; sem eles, ou sem o --sandbox, essa conferência é pulada)."""
import importlib.util
import json
import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

EVALS = Path(__file__).resolve().parents[2] / "fundacao-ia-multiprojetos" / "evals"
spec = importlib.util.spec_from_file_location("rastro_1710", EVALS / "rastro_do_executor.py")
rastro = importlib.util.module_from_spec(spec)
spec.loader.exec_module(rastro)


class Base(unittest.TestCase):
    def setUp(self):
        td = tempfile.TemporaryDirectory(prefix="rastro1710-")
        self.addCleanup(td.cleanup)
        self.t = Path(td.name).resolve()
        self.area = self.t / "area"
        self.proprio = self.area / "a123456789"
        self.amb = self.proprio / "ambiente"
        self.amb.mkdir(parents=True)
        self.bancada = self.t / "bancada" / "iteration-1"
        self.bancada.mkdir(parents=True)
        self.trace = self.t / "trace.jsonl"
        self.p, self.b, self.acima = self.proprio.as_posix(), self.bancada.as_posix(), self.t.as_posix()

    def estado(self, *comandos, ferramenta="Bash"):
        self.trace.write_text("\n".join(json.dumps({"type": "tool_use", "name": n, "input": {"command": c}})
                                        for n, c in [("Bash", f"cd {self.p}")] + [(ferramenta, c) for c in comandos])
                              + "\n", encoding="utf-8")
        return rastro.acesso_ao_gabarito(self.trace, self.bancada, {"evals.json"}, (self.amb, self.proprio),
                                         area=self.area)["estado"]


class TestClasseDoP1ForaDoGrep(Base):
    def test_padrao_glob_e_escape_nao_sao_caminho_da_raiz(self):
        """Fato 25 da sonda: estes davam "busca recursiva em pasta que contém a bancada" ou "curinga a partir da área"."""
        for comando in ('rg -g "\\*.md" chave .', 'find . -name "\\*.json"', 'grep -rn --include="\\*.py" chave .',
                        "sed -n '/.*foo/p' x.py", "awk '/\\[ERRO\\]/' x.log",
                        "sed -e 's/\\s*x//' -e '/^\\[/d' arq.txt", "sed -E -n -e '/\\s+$/p' x.txt",
                        "awk -F'\\t' '{print $1}' x.tsv", "gawk -v 'pad=\\s*' '$0 ~ pad' x.txt",
                        "grep -rnwiEHs '\\s*SELECT' .", "rg --glob='\\*.py' -e '\\s*TODO' .",
                        "grep -rn --exclude-dir='\\*' --exclude='\\*.min.js' chave ."):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "sem_acesso_no_rastro")

    def test_select_string_e_findstr(self):
        for comando in ('Select-String -Pattern "\\s*TODO" -Path x.ps1', 'Select-String "\\s*TODO" x.ps1',
                        'Select-String -Patt:"\\s*TODO" x.ps1', 'sls "\\s*TODO" -Include "\\*.ps1" -Path .\\x.ps1',
                        'findstr /s /i "\\s*TODO" *.ps1', 'findstr /c:"\\s*TODO" x.ps1'):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando, ferramenta="PowerShell"), "sem_acesso_no_rastro")

    def test_leitura_real_continua_contaminada(self):
        b, acima = self.b, self.acima
        for comando in ("ls /*", f"cat {b}/x", "rg -g evals.json chave .", f"rg -g '*.md' chave {b}",
                        f"sed -n p {b}/x", f"{{ cd {acima}; }}; grep -rn chave .", f"grep -rnIHwEi chave {acima}",
                        f"awk -f {b}/prog.awk x.txt", f"sed -f {b}/script.sed x.txt", f"sed -i.bak 's/a/b/' {b}/x",
                        "grep -rn --include=evals.json chave .", "sed -n '/evals.json/p' x.txt",
                        f"awk '{{print}}' {b}/x", f"grep -rnwiEHs chave {acima}", "find '\\' -name x",
                        # gawk -E/--exec e mawk -W exec/-Wexec= leem o programa de arquivo: é caminho, não script.
                        f"gawk -E {b}/prog.awk x.txt", f"gawk --exec {b}/prog.awk", f"mawk -W exec {b}/prog.awk",
                        f"mawk -Wexec={b}/prog.awk"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "contaminada")
        for comando in (f"Select-String -Pattern x -Path {b}/y", f"Select-String x {b}/y", f"findstr /g:{b}/p.txt x",
                        f"findstr /s chave {acima}/*", "Select-String -Pattern evals.json x.ps1",
                        # -Path:/-LiteralPath: (forma com dois-pontos) é caminho; grep/rg sob PowerShell são recursivos.
                        f"Select-String -Path:{b}/y x", f"Select-String -LiteralPath:{b}/y x",
                        f"grep -rnwiEHs chave {acima}"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando, ferramenta="PowerShell"), "contaminada")

    def test_comando_observado_do_p1_e_a_leitura_da_bancada_no_mesmo_grep(self):
        p, b = self.p, self.b
        observado = (f"F={p}/ambiente/fundacao\n"
                     "{ grep -rnE --include='*.py' --exclude-dir=tests -e 'execute(many|script)?\\(\\s*f[\"'\"'\"']' "
                     "-e '\\.format\\(.*(SELECT|INSERT|UPDATE|DELETE)' -e '\"\\s*\\+\\s*[a-z_]+.*(SELECT|WHERE)' "
                     "$F/fundacao; } > \"$TMPDIR/aud/C19.txt\" 2>&1; wc -l < \"$TMPDIR/aud/C19.txt\"")
        self.assertEqual(self.estado(observado), "sem_acesso_no_rastro")
        self.assertEqual(self.estado(observado.replace("$F/fundacao", b)), "contaminada")


class TestGrupoDeChavesF5(Base):
    def test_cd_do_grupo_vale_sem_pipe_e_fica_incerto_com_pipe_fundo_ou_funcao(self):
        p = self.p
        ler = "cat ../../bancada/iteration-1/prompts.json"  # da fundação, cai na raiz própria
        for grupo in (f"{{ cd {p}/ambiente/fundacao; ls; }} > saida 2>&1", f"{{ cd {p}/ambiente/fundacao; }} && ls",
                      f"{{ {{ cd {p}/ambiente/fundacao; }}; }}", f"{{\ncd {p}/ambiente/fundacao\n}}"):
            with self.subTest(grupo=grupo):
                self.assertEqual(self.estado(grupo, ler), "sem_acesso_no_rastro")
        for grupo in (f"echo x | {{ cd {p}/ambiente/fundacao; }}", f"{{ cd {p}/ambiente/fundacao; }} &",
                      f"{{ ls; cd {p}/ambiente/fundacao; }} | head", f"f() {{ cd {p}/ambiente/fundacao; }}",
                      f"if cd {p}/ambiente/fundacao; then ls; fi"):
            with self.subTest(grupo=grupo):
                self.assertEqual(self.estado(grupo, ler), "nao_medido")


class TestGruposDeOpcoes(unittest.TestCase):
    def test_letra_a_letra_ate_a_que_leva_valor(self):
        r = rastro._recursivo
        for argv, esperado in ((["grep", "-rnwiEHs", "x"], True), (["grep", "-nwiEHsr", "x"], True),
                               (["grep", "-A3r", "x"], False), (["grep", "-erecursivo", "x"], False),
                               (["sed", "-r", "s/a/b/", "x"], False), (["awk", "-r", "x"], False),
                               (["ls", "-latrh"], False), (["ls", "-lahR"], True), (["cp", "-arvx", "a", "b"], True),
                               (["findstr", "/spin", "x", "*.txt"], True), (["findstr", "/i", "x", "y"], False),
                               (["Select-String", "-Raw", "x"], False)):
            with self.subTest(argv=argv):
                self.assertIs(r(argv), esperado)
        self.assertEqual(rastro._letras("grep", "-rnA3"), ("rn", "A", "3"))
        self.assertEqual(rastro._letras("sed", "-ni.bak"), ("ni", None, None))
        # grep sob o PowerShell segue a leitura letra a letra (grupo de qualquer tamanho); os cmdlets do PowerShell
        # seguem a regra antiga, para não tomar -Force por recursão (1.7.10).
        self.assertIs(r(["grep", "-rnwiEHs", "x"], powershell=True), True)
        self.assertIs(r(["grep", "-nwHRie", "x"], powershell=True), True)
        self.assertIs(r(["Get-ChildItem", "-Force", "x"], powershell=True), False)
        self.assertIs(r(["Get-ChildItem", "-Recurse", "x"], powershell=True), True)

    def test_papeis_por_programa(self):
        papeis = rastro._papeis(["sed", "-n", "-e", "s/x/y/", "-f", "s.sed", "a.txt"])
        self.assertEqual((papeis["padroes"], papeis["valores"], papeis["sem_caminho"]), ([3], [5], False))
        papeis = rastro._papeis(["awk", "-F:", "{print}", "a.txt"])
        self.assertEqual((papeis["padroes"], papeis["colados"]), ([2], [["padrao", ":"]]))
        papeis = rastro._papeis(["rg", "-g*.md", "--iglob", "*.py", "chave", "."])
        self.assertEqual((papeis["globs"], papeis["colados"], papeis["padroes"]), ([3], [["glob", "*.md"]], [4]))
        papeis = rastro._papeis(["Select-String", "-Path", "a.ps1", "-Pattern", "x"])
        self.assertEqual((papeis["padroes"], papeis["sem_caminho"]), ([4], True))
        papeis = rastro._papeis(["findstr", "/d:a;b", "/c:x y", "arq.txt"])
        self.assertEqual(papeis["colados"], [["pasta", "a"], ["pasta", "b"], ["padrao", "x y"]])
        self.assertEqual(papeis["padroes"], [])
        # awk que lê o programa de arquivo: -E/--exec (gawk) e -W exec/-Wexec= (mawk). O arquivo é caminho, não script.
        papeis = rastro._papeis(["gawk", "-E", "p.awk", "a.txt"])
        self.assertEqual((papeis["valores"], papeis["padroes"], papeis["sem_caminho"]), ([2], [], False))
        papeis = rastro._papeis(["gawk", "--exec", "p.awk"])
        self.assertEqual((papeis["valores"], papeis["padroes"]), ([2], []))
        papeis = rastro._papeis(["mawk", "-W", "exec", "p.awk"])
        self.assertEqual((papeis["valores"], papeis["padroes"]), ([3], []))
        papeis = rastro._papeis(["mawk", "-Wexec=p.awk"])
        self.assertEqual((papeis["colados"], papeis["padroes"]), ([["arquivo", "p.awk"]], []))
        # -Path:<x> do Select-String (forma com dois-pontos) entra como caminho ('pasta'), fora dos alvos posicionais.
        papeis = rastro._papeis(["Select-String", "-Path:a.ps1", "x"])
        self.assertEqual((papeis["colados"], papeis["padroes"]), ([["pasta", "a.ps1"]], [2]))


class TestScriptComEntradaESaidaCIF7(Base):
    """Revisão de segurança da 1.7.10, CI-F7: script de awk ou sed que roda comando ou lê e grava arquivo volta à regra
    da 1.7.9 (nome com curinga conta como acesso, sem conferir caminho) e deixa o isolamento não medido. Os casos 4 e 5
    do achado (awk com system() e sed com o comando e, lendo o gabarito por curinga) davam "contaminada" na 1.7.9 e
    "sem_acesso_no_rastro" na 1.7.10 antes da correção; com o nome exato (casos 3 e 6), "contaminada" nas duas."""

    def test_casos_4_e_5_do_achado_e_variantes_com_curinga_contaminam(self):
        alvo, x = f"{self.acima}/bancad*/iter*/evals*", f"{self.p}/ambiente/x.txt"
        for comando in (f"awk 'BEGIN{{system(\"cat {alvo}\")}}'",                       # caso 4
                        f"sed -n '1e cat {alvo}' {x}",                                     # caso 5
                        f"awk 'BEGIN{{\"cat {alvo}\" | getline l; print l}}'",
                        f"gawk 'BEGIN{{\"cat {alvo}\" |& getline l; print l}}'",
                        f"awk 'BEGIN{{print \"x\" | \"cat - {alvo}\"}}'",
                        f"awk -v c='cat {alvo}' 'BEGIN{{system(c)}}'",                    # o comando no -v
                        f"gawk -e 'BEGIN{{system(\"cat {alvo}\")}}'",
                        f"sed 's|.*|cat {alvo}|e' {x}", f"sed --expression='1e cat {alvo}' {x}",
                        f"sed -e p -e '$e cat {alvo}' {x}"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "contaminada")

    def test_nome_exato_continua_contaminando(self):
        """Casos 3 e 6 do achado: já davam "contaminada" antes e depois."""
        for comando in (f"awk 'BEGIN{{while((getline l < \"{self.b}/evals.json\")>0) print l}}'",
                        f"sed -n '$r {self.acima}/bancad?/iteration-1/evals.json' {self.p}/ambiente/x.txt"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "contaminada")

    def test_nomes_reais_do_gabarito_por_curinga(self):
        """A forma do cético 1: os nomes de nomes_do_gabarito (eval_metadata.json, as pastas eval-*)."""
        nomes = rastro.nomes_do_gabarito(self.bancada)
        for comando in (f"awk 'BEGIN{{system(\"cat {self.acima}/ws/iter*/eval-*/eval_meta*\")}}'",
                        f"sed -n '1e cat {self.acima}/ws/iter*/eval-*/eval_meta*' x.txt"):
            with self.subTest(comando=comando):
                usos = ({"type": "tool_use", "name": "Bash", "input": {"command": c}} for c in (f"cd {self.p}", comando))
                self.trace.write_text("\n".join(map(json.dumps, usos)) + "\n", encoding="utf-8")
                res = rastro.acesso_ao_gabarito(self.trace, self.bancada, nomes, (self.amb, self.proprio),
                                                area=self.area)
                self.assertEqual(res["estado"], "contaminada")

    def test_script_com_entrada_e_saida_sem_nome_do_gabarito_fica_nao_medido(self):
        for comando in ("awk 'BEGIN{system(\"ls\")}'", "awk '{print > \"saida.txt\"}' x.txt",
                        "awk '{print >> \"saida.txt\"}' x.txt", "awk '{printf \"%s\\n\", $0 | \"sort\"}' x.txt",
                        "awk 'BEGIN{while ((getline l < \"outro.txt\") > 0) n++}'",
                        "gawk '@load \"readfile\"; BEGIN{print readfile(\"outro.txt\")}'",
                        "gawk -l readfile 'BEGIN{print readfile(\"outro.txt\")}'", "gawk '@include \"outro.awk\"'",
                        "awk 'BEGIN{ARGV[1]=\"outro.txt\"; ARGC=2} {print}'", "gawk 'BEGIN{f=\"system\"; @f(\"ls\")}'",
                        "sed -n '$r outro.txt' x.txt", "sed 'R outro.txt' x.txt", "sed -n 'w saida.txt' x.txt",
                        "sed 'W saida.txt' x.txt", "sed 's/a/b/w saida.txt' x.txt", "sed 's/.*/date/e' x.txt",
                        "sed '1e' x.txt", "sed -n '/x/{p;e date\n}' x.txt", "sed -n '/x/ !{ r outro.txt\n}' x.txt",
                        "sed -n '/[/#]/e date' x.txt",  # no GNU sed 4.9, a barra entre colchetes não fecha a expressão
                        # A regra da 1.7.9 volta só para os nomes: a expressão do script continua sem ser caminho (P1).
                        "sed -n '/[a-z]/w saida.txt' x.txt", "awk '/^[a-z]/{print > \"saida.txt\"}' x.txt"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "nao_medido")

    def test_script_inofensivo_continua_como_antes(self):
        for comando in ("awk '{print $1}' x.txt", "sed 's/a/b/' x.txt", "awk '{print $1 \"|\" $2}' x.txt",
                        "awk '$3 > 100 {print $1}' x.txt", "awk 'NR>1{print}' x.txt", "awk '/a|b/{print}' x.txt",
                        "awk -F'>' '{print $2}' x.txt", "awk '{if (/x/ || /y/) print}' x.txt",
                        "sed -n '/error/p' x.txt", "sed 's/rew/wer/g' x.txt", "sed ':a;N;$!ba;s/\\n/ /g' x.txt",
                        "sed -e '1i\\' -e 'writer' x.txt", "sed 'y/abc/xyz/' x.txt", "sed -n '/^#/!p' x.txt",
                        "sed '$!N;s/\\n/ /;P;D' x.txt", "sed '1~2d;0,/re/s//x/' x.txt", "sed -n '\\,foo,p' x.txt",
                        "sed 's/x/y/2gI' x.txt", "sed -n '/a/,/b/{/c/p}' x.txt", "sed '$a fim do arquivo' x.txt",
                        "sed 'l 40;q5' x.txt", "sed -n 'p # comentário com w e r' x.txt", "sed 's/[/]/x/' x.txt",
                        "sed -n '/[#]/p;/[a]/d' x.txt"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "sem_acesso_no_rastro")

    def test_no_powershell_o_script_e_lido_na_leitura_posix(self):
        """A leitura com as barras do Windows desfaz o script (`/\\s+$/p` vira `//s+$/p`): ele é lido na POSIX."""
        for comando, esperado in (("sed -n '/\\s+$/p' x.txt", "sem_acesso_no_rastro"),
                                  ("sed -e 's/\\s*x//' -e '/^\\[/d' x.txt", "sem_acesso_no_rastro"),
                                  (f"sed -n '1e cat {self.acima}/bancad*/evals*' x.txt", "contaminada"),
                                  ("awk 'BEGIN{system(\"dir\")}'", "nao_medido")):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando, ferramenta="PowerShell"), esperado)

    def test_leitura_do_script_do_sed(self):
        """Conferida com o --sandbox do GNU sed 4.9 (recusa e/r/R/w/W) no Ubuntu e no Git Bash, em 01/11/2026."""
        com_es = rastro._script_com_es
        for scripts in (["1e cat x"], ["$r x"], ["/a/R x"], ["w x"], ["/a/,/b/W x"], ["s/a/b/e"], ["s/a/b/gw x"],
                        ["p", "e ls"], ["{p;r x\n}"], ["s/a"], ["/a"], ["k"],  # o que não se lê como sed conta
                        # o delimitador entre colchetes não fecha a expressão (o # e o a seguintes não são comando)
                        ["/[/#]/e ls"], ["/[/a]/e ls"], ["/[]/]/e ls"], ["/[[:alpha:]/]/e ls"], ["s/[/]/x/e"],
                        ["\\,[,],e ls"]):
            with self.subTest(scripts=scripts):
                self.assertTrue(com_es(["sed"], scripts))
        for scripts in (["s/a/b/"], ["/rew/p"], ["s/r/w/g"], ["y/erw/wre/"], ["1i\\", "write"], ["$a r w e"],
                        [":rw;N;brw"], ["# r x"], ["\\,e,d"], ["2q", "l"], [], ["/[/]/p"], ["s/[/]/x/"], ["y/[/]/"],
                        ["/[#]/p;/[a]/d"], ["s/[^/]*$//"]):
            with self.subTest(scripts=scripts):
                self.assertFalse(com_es(["sed"], scripts))
        self.assertFalse(com_es(["grep"], ["e"]))  # só sed e awk

    # Revisão 1 do CI-F7 (rodada 4). Na 58467d0, 18 das 20 formas abaixo davam "sem_acesso_no_rastro" e liam o gabarito;
    # as outras duas (o | getline depois de /"/ e o comentário com barra no fim) são variantes do mesmo caminho.
    def _formas_do_awk(self, alvo):
        """As formas do defeito 1 das duas revisões: aspa em expressão regular, continuação (barra invertida e quebra de
        linha, também na cadeia e depois da vírgula do print), ; { } dentro da expressão e o comentário que termina em
        barra invertida (a linha seguinte roda)."""
        return (f"awk '{{gsub(/\"/, \"\"); system(\"cat {alvo}\")}}' x.txt",
                f"awk 'BEGIN{{x=/\"/; system(\"cat {alvo}\")}}'", f"awk '/\"/{{}} BEGIN{{system(\"cat {alvo}\")}}'",
                f"awk 'BEGIN{{x=/\"/; \"cat {alvo}\" | getline l}}'",
                f"awk 'BEGIN{{x=/\"/; print \"\" | \"cat {alvo}\"}}'",
                f"gawk 'BEGIN{{x=/\"/; system(\"cat {alvo}\")}}'", f"mawk 'BEGIN{{x=/\"/; system(\"cat {alvo}\")}}'",
                f"awk 'BEGIN{{s=\"a\\\nb\"; system(\"cat {alvo}\")}}'", f"awk 'BEGIN{{system\\\n(\"cat {alvo}\")}}'",
                f"awk 'BEGIN{{print \"\" \\\n| \"cat {alvo}\"}}'", f"awk 'BEGIN{{\"cat {alvo}\" |\\\ngetline l}}'",
                f"awk 'BEGIN{{print /;/ | \"cat {alvo}\"}}'", f"awk 'BEGIN{{print /}}/ | \"cat {alvo}\"}}'",
                f"mawk 'BEGIN{{print /;/ | \"cat {alvo}\"}}'",
                f"awk '$0 ~ /\"/ {{ system(\"cat {alvo}\") }}' x.csv",
                f"awk 'BEGIN {{ print \"x\",\n\"y\" | \"cat {alvo}\" }}'",
                f"awk 'BEGIN {{ while ((getline l \\\n< \"{alvo}\") > 0) print l }}'",
                f"awk 'BEGIN {{ print (1 ~ /}}/) ? \"a\" : \"b\" | \"cat {alvo}\" }}'",
                f"awk 'BEGIN{{ # c \\\nprint \"\" | \"cat {alvo}\" }}'",
                f"awk 'BEGIN {{ if (1) /\"/ ; print \"\" | \"cat {alvo}\" }}'")

    def test_formas_lexicas_do_awk_com_nome_por_curinga_contaminam(self):
        for comando in self._formas_do_awk(f"{self.acima}/bancad*/iter*/evals*"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "contaminada")

    def test_formas_lexicas_do_awk_sem_nome_ficam_nao_medidas(self):
        for comando in self._formas_do_awk(f"{self.acima}/b*/i*/e*"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "nao_medido")
        # A aspa na expressão sem E/S continua inofensiva.
        for comando in ("awk '{gsub(/\"/, \"\")} 1' x.txt", "awk 'BEGIN{x=/\"/; print x}'",
                        "awk '{print (NR > 1) ? $0 : \"cabeçalho\"}' x.txt", "awk '$0 ~ /\"/ {n++} END {print n/2}' x"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "sem_acesso_no_rastro")

    def test_comentario_do_sed_termina_na_quebra_de_linha(self):
        """Defeito 2 da revisão 1: o GNU sed 4.9 termina o comentário na quebra de linha e no fim do -e, sem continuação
        pela barra invertida; antes, ele escondia o comando seguinte."""
        for scripts in (["#\\", "1e echo SAIU"], ["p #\\", "w saida"], ["s/a/b/#\\", "r outro"]):
            with self.subTest(scripts=scripts):
                self.assertTrue(rastro._script_com_es(["sed"], scripts))
        alvo, x = f"{self.acima}/bancad*/iter*/evals*", f"{self.p}/ambiente/x.txt"
        for comando in (f"sed -n -e '#\\' -e '1e cat {alvo}' {x}", f"sed -n '#\\\n1e cat {alvo}' {x}",
                        f"sed -n 'p #\\\n1e cat {alvo}' {x}"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "contaminada")

    def test_citacao_ansi_c_conta_como_script_com_es(self):
        """Defeito 3 da revisão 1: o shlex não decodifica `$'…'`, e o bash entrega ao sed e ao awk a quebra de linha e o
        \\x74. Na linha com `$'`, o script do sed ou do awk conta como com E/S (até o inofensivo: não medido)."""
        alvo, x = f"{self.acima}/bancad*/iter*/evals*", f"{self.p}/ambiente/x.txt"
        for comando in (f"sed -n $'#\\n1e cat {alvo}' {x}", f"sed $'1a x\\n1e cat {alvo}' {x}",
                        f"awk $'BEGIN{{sys\\x74em(\"cat {alvo}\")}}'"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "contaminada")
        for comando in (f"sed -n $'#\\n1e ls' {x}", "awk -F$'\\t' '{print $1}' x.tsv"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "nao_medido")
        self.assertEqual(self.estado("grep -n $'\\tx' x.txt"), "sem_acesso_no_rastro")  # só sed e awk
        # O mesmo no PowerShell, que decodifica o acento grave nas aspas duplas (`n é a quebra de linha).
        self.assertEqual(self.estado(f'sed -n "#`n1e cat {alvo}" x.txt', ferramenta="PowerShell"), "contaminada")
        self.assertEqual(self.estado('sed -n "/x/p`n" x.txt', ferramenta="PowerShell"), "nao_medido")
        self.assertEqual(self.estado("sed -n '/x/p' x.txt", ferramenta="PowerShell"), "sem_acesso_no_rastro")

    def test_opcao_longa_abreviada_w_e_nome_com_versao(self):
        """Defeito 4 da revisão 1: prefixo único da opção longa (getopt_long), -W do gawk e do mawk e nome com versão."""
        alvo = f"{self.acima}/b*/i*/e*"
        for comando in (f"sed -n --expr='1e cat {alvo}' p", f"sed -n --e '1e cat {alvo}' p",
                        f"gawk --sourc='BEGIN{{system(\"cat {alvo}\")}}'", f"gawk --so 'BEGIN{{system(\"cat {alvo}\")}}'",
                        f"gawk -W source='BEGIN{{system(\"cat {alvo}\")}}'",
                        f"gawk -Wsour='BEGIN{{system(\"cat {alvo}\")}}'",
                        f"gawk -W sour 'BEGIN{{system(\"cat {alvo}\")}}'",
                        f"gawk-5.4.1 'BEGIN{{system(\"cat {alvo}\")}}'", f"mawk-1.3.4 'BEGIN{{system(\"cat {alvo}\")}}'",
                        "gawk --lo=readfile 'BEGIN{print 1}'", "gawk -W load readfile 'BEGIN{print 1}'",
                        # --i: include no gawk, interactive no mawk; com o nome awk, o programa é incerto
                        "awk --i y.awk 'BEGIN{print 1}'"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "nao_medido")
        self.assertEqual(self.estado(f"sed -n --expr='1e cat {self.acima}/bancad*/iter*/evals*' p"), "contaminada")
        for comando in ("sed -n --expr='/x/p' x.txt", "gawk --sourc='{print $1}' x.txt", "gawk --i y.awk '{print}' x",
                        "mawk -W interactive '{print $1}' x.txt", "gawk-5.4.1 '{print $1}' x.txt"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "sem_acesso_no_rastro")

    def test_programas_do_sed_na_ordem_da_linha(self):
        """Defeito 2 da revisão 2: o -e colado (ou --expression=) antes do -e separado com a\\ no fim; o sed os junta
        na ordem da linha, e o a\\ não engole o 1e."""
        alvo, x = f"{self.acima}/bancad*/iter*/evals*", f"{self.p}/ambiente/x.txt"
        for comando in (f"sed --expression='1e cat {alvo}' -e '$a\\' {x}", f"sed -e'1e cat {alvo}' -e '$a\\' {x}"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "contaminada")
        self.assertEqual(self.estado("sed -e '1i\\' -e 'writer' x.txt"), "sem_acesso_no_rastro")
        papeis = rastro._papeis(["sed", "--expression=1e x", "-e", "$a\\", "-e3d", "-e", "p", "f"])
        self.assertEqual([t for _, t in sorted(papeis["programas"])], ["1e x", "$a\\", "3d", "p"])

    def test_papeis_das_opcoes_do_sed_e_do_awk(self):
        p = rastro._papeis
        self.assertEqual(p(["sed", "--expr=s/a/b/", "f"])["colados"], [["programa", "s/a/b/"]])
        self.assertEqual(p(["sed", "--fil", "s.sed", "f"])["valores"], [2])  # --file
        self.assertEqual(p(["sed", "--s", "p", "f"])["padroes"], [2])  # ambígua (sandbox, separate, silent)
        self.assertEqual(p(["gawk", "-W", "sour", "BEGIN{}", "f"])["padroes"], [3])
        self.assertEqual(p(["gawk", "-Wsource=BEGIN{}"])["colados"], [["programa", "BEGIN{}"]])
        self.assertEqual(p(["mawk", "-We", "p.awk"])["valores"], [2])
        self.assertEqual(p(["mawk", "-W", "i,exec", "p.awk"])["valores"], [3])
        self.assertTrue(p(["gawk", "--lo", "x", "BEGIN{}"])["extensao"])
        self.assertTrue(p(["gawk", "-Wlo=x", "BEGIN{}"])["extensao"])
        self.assertTrue(p(["awk", "--i", "x", "y"])["incerto"])
        self.assertFalse(p(["gawk", "--i", "x", "y"])["incerto"])  # o gawk lê --i como --include
        self.assertEqual(rastro._familia("C:/Program Files/Git/usr/bin/gawk-5.4.1.exe"), "awk")
        self.assertEqual(rastro._implementacao("/usr/bin/mawk-1.3.4"), "mawk")
        self.assertEqual(rastro._familia("python3"), None)

    # Revisão 2 do CI-F7 (rodada 4). Na fc9111f, os casos com curinga abaixo davam "sem_acesso_no_rastro" e liam o
    # gabarito; os sem nome, "sem_acesso_no_rastro" em vez de "nao_medido"; as guardas, "nao_medido" ou "contaminada".
    def test_opcoes_do_gawk_com_valor_opcional_colado(self):
        """Defeito 1 do revisor 1: -d, -D, -L, -o e -p do gawk têm valor opcional, só colado, que leva o resto do grupo
        (gawk --help do 5.4.1 e do 5.2.1). Em `gawk -pv 'prog'`, o programa é o argumento seguinte; antes, ele virava o
        valor do -v (papel de padrão, só o nome exato contava) ou, em `-pf`, um arquivo."""
        alvo = f"{self.acima}/bancad*/iter*/evals*"
        for opcao in ("gawk -pv", "gawk -pF", "gawk -Lv", "gawk -dv", "gawk -Dv", "gawk -ov", "awk -pv", "awk -dF"):
            with self.subTest(opcao=opcao):
                self.assertEqual(self.estado(f"{opcao} 'BEGIN{{system(\"cat {alvo}\")}}'"), "contaminada")
        self.assertEqual(self.estado("gawk -pf 'BEGIN{system(\"ls\")}'"), "nao_medido")
        self.assertEqual(self.estado("gawk -pv '{print $1}' x.txt"), "sem_acesso_no_rastro")
        p = rastro._papeis
        self.assertEqual(p(["gawk", "-pv", "P"])["programas"], [(2, "P")])
        self.assertEqual(p(["gawk", "-Sp", "P"])["programas"], [(2, "P")])
        self.assertEqual(p(["gawk", "-vp=1", "P"])["programas"], [(2, "P")])  # o -v continua levando o valor
        self.assertEqual((p(["gawk", "-fp", "P"])["colados"], p(["gawk", "-fp", "P"])["programas"]),
                         ([["arquivo", "p"]], []))  # e o -f também

    def test_transformacoes_do_bash_fora_das_aspas(self):
        """Defeito 2 do revisor 1 e uma variante da sonda desta rodada: fora das aspas, a expansão de chaves, a `$"…"` e
        a continuação de linha (barra invertida e quebra de linha, que o bash tira e o shlex deixa como quebra) mudam o
        script que o sed e o awk recebem (printf e --sandbox no bash 5.3.15 e no 5.2.21, em 01/11/2026)."""
        alvo, x = f"{self.acima}/bancad*/iter*/evals*", f"{self.p}/ambiente/x.txt"
        for comando in (f"sed -n -e1{{a,e}}' cat {alvo}' {x}", f"awk 'BEGIN{{'sys{{tem,x}}'(\"cat {alvo}\")}}'",
                        f"awk 'BEGIN{{sys'\\\n'tem(\"cat {alvo}\")}}'"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "contaminada")
        for comando in (f"sed -n -e1{{a,e}}' ls' {x}", "awk 'BEGIN{'sys{tem,x}'(\"ls\")}'",
                        "awk 'BEGIN{sys'\\\n'tem(\"ls\")}'",
                        "awk 'BEGIN{x=1'$\"/2; print \\\"\\\" | \\\"echo x\\\"; y=1/2}\"",
                        "awk -F$\"\\t\" '{print $1}' x.tsv"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "nao_medido")
        # Guardas: dentro das aspas, `${`, `{}`, o `{` do grupo e o escape não contam.
        for comando in ("sed -n '/x/{p}' x.txt", "{ sed -n p x.txt; } > y", "awk -v d=\"${HOME}\" '{print d}' x.txt",
                        "find . -name '*.txt' -exec ls {} +; sed -n p x.txt", "awk '{print $\"1\"}' x.txt",
                        "sed -n \"s/a/\\$'/p\" x.txt", "echo \\$'x'; sed -n p x.txt"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "sem_acesso_no_rastro")
        e = rastro._expansao_do_bash
        for texto in ("a $'x'", 'a $"x"', "a{b,c}", "'a'\\\n'b'", "x{1..3}", "a\\\nb"):
            with self.subTest(texto=texto):
                self.assertTrue(e(texto))
        for texto in ("'$'", "'^$'", "\"$'\"", "${x}", "{ x; }", "{}", "\"a{b,c}\"", "'{a,b}'", "\\$'x'", "\"\\\n\""):
            with self.subTest(texto=texto):
                self.assertFalse(e(texto))

    def test_marca_de_transformacao_so_fora_das_aspas(self):
        """Defeito do revisor 2: o `$'` contava em qualquer lugar da linha, também no `'^$'` do grep, e o acento grave
        contava dentro das aspas simples do PowerShell, onde é literal; o sed ou o awk da mesma linha virava script com
        E/S, e um padrão como `evals.*` dava "contaminada" falsa."""
        for comando in ("grep -v '^$' x.txt | awk '{print $1}'", "grep -c '^$' x.txt; sed -n '1,5p' x.txt",
                        "grep -v '^$' x.txt | sed -n '/evals.*/p' x.txt", "ls | grep '\\.py$' | awk -F/ '{print $NF}'",
                        "grep -c 'ok$' x.txt; awk '/evals.*/ {print $2}' x.txt"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), "sem_acesso_no_rastro")
        for comando in ("Write-Output 'a`b'; sed -n '/evals.*/p' x.txt", "Write-Output 'a`b'; sed -n '/x/p' x.txt",
                        "Write-Output \u2018a`b\u2019; sed -n '/x/p' x.txt"):  # aspas simples tipográficas
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando, ferramenta="PowerShell"), "sem_acesso_no_rastro")
        # Continua contando: o acento grave nas aspas duplas (também as tipográficas) e na palavra sem aspas.
        for comando in ('Write-Output "a`b"; sed -n p x.txt', "Write-Output a`tb; sed -n p x.txt",
                        "Write-Output \u201ca`b\u201d; sed -n p x.txt", "Write-Output \"it's `t\"; sed -n p x.txt"):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando, ferramenta="PowerShell"), "nao_medido")
        g = rastro._acento_grave_do_powershell
        self.assertEqual([g(t) for t in ("'a`b'", "'a''`b'", "\u2018a`b\u2019", '"a`b"', "a`b", "\"it's`\"")],
                         [False, False, False, True, True, True])

    def test_releitura_do_programa_nativo_no_powershell(self):
        """Faltou do revisor 1, sondado nesta rodada: o Windows PowerShell 5.1 não escapa a aspa de dentro do argumento,
        e o runtime do MSYS2 (o sed e o gawk do Git) lê aspa e apóstrofo como aspas e expande as chaves do argumento sem
        espaço: `{sys{tem,x}(x)}` chegou ao gawk 5.4.1 como `system(x)` e `sysx(x)`; `{print}`, como `print`."""
        alvo = f"{self.acima}/bancad*/iter*/evals*"
        for comando, esperado in ((f"gawk -v 'x=cat {alvo}' '{{sys{{tem,x}}(x)}}' x.txt", "contaminada"),
                                  ("gawk -v 'x=ls' '{sys{tem,x}(x)}' x.txt", "nao_medido"),
                                  ("awk '{print}' x.txt", "nao_medido"), ("sed -n '1{p}' x.txt", "nao_medido"),
                                  ("sed -n \"/it's/p\" x.txt", "nao_medido"),
                                  # com espaço e sem aspa dentro, o PowerShell põe aspas e o argumento chega inteiro
                                  ("awk '{print $1}' x.txt", "sem_acesso_no_rastro"),
                                  ("awk -F, '{print $2}' x.csv", "sem_acesso_no_rastro"),
                                  ("sed -n '/x/p' x.txt", "sem_acesso_no_rastro")):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando, ferramenta="PowerShell"), esperado)
        # No bash, o programa recebe o argv inteiro (sem releitura).
        self.assertEqual(self.estado("gawk -v 'x=ls' '{sys{tem,x}(x)}' x.txt"), "sem_acesso_no_rastro")
        r = rastro._relido_no_windows
        self.assertEqual([r(a) for a in ('a"b', "it's", "{print}", "{print $1}", "/x/p", "s/a/b/")],
                         [True, True, True, False, False, False])

    def test_aspas_tipograficas_no_powershell(self):
        """Achado novo da sonda desta rodada (Windows PowerShell 5.1): o PowerShell lê ‘ ’ ‚ ‛ e “ ” „ como aspas, e o
        leitor do rastro não as conhecia. `Get-Content ‘<bancada>/evals.json’` saía "sem_acesso_no_rastro" (também na
        1.7.9), e o sed entre aspas tipográficas ficava dentro de uma palavra."""
        b, sed = self.b, f"sed -n \"1e cat {self.acima}/b*/i*/e*`n\" x.txt"
        for comando, esperado in ((f"Get-Content \u2018{b}/evals.json\u2019", "contaminada"),
                                  (f"Get-Content \u201c{b}/notas.txt\u201d", "contaminada"),
                                  (f"Get-Content \u201a{b}/notas.txt\u201b", "contaminada"),
                                  (f"Write-Output \u2018a'; {sed}; Write-Output \u2018z'", "nao_medido")):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando, ferramenta="PowerShell"), esperado)

    def test_exec_e_prefixo_como_command(self):
        """Faltou do revisor 1: o `exec` roda o programa no lugar do shell, como o `command`; antes, `exec awk …` não
        era lido como awk e `exec bash -c` não deixava o isolamento não medido."""
        for comando, esperado in (("exec awk 'BEGIN{system(\"ls\")}'", "nao_medido"),
                                  ("exec bash -c 'ls'", "nao_medido"), ("exec find / -name x", "contaminada"),
                                  ("exec sed -n p x.txt", "sem_acesso_no_rastro")):
            with self.subTest(comando=comando):
                self.assertEqual(self.estado(comando), esperado)
        self.assertEqual(rastro._sem_prefixo(["exec", "gawk", "-f", "p.awk", "x"]), ["gawk", "-f", "p.awk", "x"])


# Listas fixas da diferencial (CI-F7, revisão 1). Sed: os -e de um comando, com o veredito do --sandbox do GNU sed 4.9,
# que recusa e/r/R/w/W ao ler o script. Awk: programas que rodam no BEGIN, com o veredito do gawk --sandbox, que recusa
# system, getline com arquivo ou comando, redirecionamento, extensão e arquivo novo no ARGV ao rodar. Conferidas no
# Ubuntu (sed 4.9, gawk 5.2.1) e no Git Bash (sed 4.9, gawk 5.4.1) em 01/11/2026; o mawk 1.3.4, pela execução (sonda).
SED_COM_ES = (
    ["1e cat x"], ["$r x"], ["/a/R x"], ["w x"], ["/a/,/b/W x"], ["s/a/b/e"], ["s/a/b/gw x"], ["p", "e ls"],
    ["{p;r x\n}"], ["#\\", "1e echo SAIU"], ["p #\\", "w saida"], ["s/a/b/#\\", "r outro"], ["#\\\n1e echo SAIU"],
    ["p #\\\n1e echo"], ["/[[:alpha:]/]/s/a/b/gp; # e r w\\\n/[#]/s/a/b/e"], ["# comment\\\n\\%[%]%H; /a/,/b/e\\\n"],
    ["#\\\n1r file", "\n/[^]/]/", ":lab 1,3a  x\\\ny}/a/,/b/s/a/b/g"], ["1e echo", "$a\\"], ["/[/#]/e ls"],
    ["/[/a]/e ls"], ["/[]/]/e ls"], ["/[[:alpha:]/]/e ls"], ["s/[/]/x/e"], ["\\,[,],e ls"], ["1a foo", "w x"],
    ["b x;e"], ["s/a/b/ w x"], ["s/a/b/g e"], ["y/a/b/;e"])
SED_SEM_ES = (
    ["s/a/b/"], ["/rew/p"], ["s/r/w/g"], ["y/erw/wre/"], ["1i\\", "write"], ["$a r w e"], [":rw;N;brw"], ["# r x"],
    ["\\,e,d"], ["2q", "l"], ["/[/]/p"], ["s/[/]/x/"], ["/[#]/p;/[a]/d"], ["s/[^/]*$//"], ["1a foo\\", "w x"],
    ["1a foo\\\nw x"], ["p # comentário com w e r"], ["#\\"], ["{p}"], ["$!N;s/\\n/ /;P;D"], ["1~2d;0,/re/s//x/"],
    ["s/x/y/2gI"], ["l 40;q5"], ["/a/,/b/{/c/p}"], ["$a fim do arquivo"], ["s/#/w/"])
AWK_COM_ES = (
    'BEGIN{system("echo x")}', 'BEGIN{gsub(/"/, "", s); system("echo x")}', 'BEGIN{x=/"/; system("echo x")}',
    '/"/{} BEGIN{system("echo x")}', 'BEGIN{x=/"/; "echo x" | getline l}', 'BEGIN{x=/"/; print "" | "cat"}',
    'BEGIN{s="a\\\nb"; system("echo x")}', 'BEGIN{system\\\n("echo x")}', 'BEGIN{print "" \\\n| "cat"}',
    'BEGIN{"echo x" |\\\ngetline l}', 'BEGIN{print /;/ | "cat"}', 'BEGIN{print /}/ | "cat"}',
    'BEGIN { print "x",\n"y" | "cat" }', 'BEGIN { while ((getline l \\\n< "x.txt") > 0) print l }',
    'BEGIN { print (1 ~ /}/) ? "a" : "b" | "cat" }', 'BEGIN{ # c \\\nprint "" | "cat" }',
    'BEGIN { if (1) /"/ ; print "" | "cat" }', 'BEGIN { w = /[/"]/; print "" | "cat" }',
    'BEGIN { print "a" > "saida" }', 'BEGIN { printf "a" >> "saida" }', 'BEGIN { print "" |& "cat" }',
    'BEGIN { f = "system"; @f("echo x") }', 'BEGIN { ARGV[1] = "x.txt"; ARGC = 2 }',
    'BEGIN { print "x" ? "y" :\n"z" | "cat" }', 'BEGIN { print\\\n"x" | "cat" }')
AWK_SEM_ES = (
    'BEGIN{gsub(/"/, "", s)}', 'BEGIN { x = /"/; y = "a/b"; z = 1 / 2 / 1 }', 'BEGIN { print (1 > 0) }',
    'BEGIN { s = "a\\\nb"; print s }', 'BEGIN { x = 4; x /= 2; print x }', 'BEGIN { print 1 " | " 2 }',
    'BEGIN { if (1 > 0) print "ok" }', 'BEGIN { n = split("a|b", p, /\\|/); print n }', 'BEGIN { print "a" "|" "b" }',
    'BEGIN { x = 3; print (x > 2) ? "big" : "small" }', 'BEGIN { a["x"] = 1; for (k in a) print k }',
    'BEGIN { printf "%d\\n", 10 / 3 }', 'BEGIN { x = "#"; print x }', 'BEGIN { print /#/ ? "s" : "n" }',
    'BEGIN { print "x" } # comentário com > e |', 'BEGIN { v = /;}{/; print "v" }',
    'BEGIN { t = (1 ~ /}/) ? "a" : "b"; print t }', 'BEGIN { y = 2 \\\n + 3; print y }', 'BEGIN { r = "\\""; print r }')


class TestDiferencialFixaCIF7(unittest.TestCase):
    """A comparação com o --sandbox virou lista fixa (revisão 1 do CI-F7): sem falso negativo e, nos scripts que o sed e
    o gawk aceitam sem E/S, sem falso positivo."""

    def test_sed(self):
        for scripts in SED_COM_ES:
            with self.subTest(scripts=scripts):
                self.assertTrue(rastro._script_com_es(["sed"], list(scripts)))
        for scripts in SED_SEM_ES:
            with self.subTest(scripts=scripts):
                self.assertFalse(rastro._script_com_es(["sed"], list(scripts)))

    def test_awk(self):
        for programa in AWK_COM_ES:
            with self.subTest(programa=programa):
                self.assertTrue(rastro._script_com_es(["awk"], [programa]))
        for programa in AWK_SEM_ES:
            with self.subTest(programa=programa):
                self.assertFalse(rastro._script_com_es(["awk"], [programa]))

    def _oraculo(self, programa: str, versao: str, args) -> list[subprocess.CompletedProcess]:
        """Roda `programa --sandbox` com cada caso (os scripts vão por -f, sem as aspas da linha de comando do Windows)
        e uma entrada vazia; sem o programa, sem ser o GNU ou sem o --sandbox (o GNU sed antes do 4.3; o sed do
        busybox, que se diz "not GNU sed"), o teste é pulado (revisão 2 do CI-F7: antes, estes dois falhavam)."""
        caminho = shutil.which(programa)
        if not caminho:
            self.skipTest(f"sem {programa} no PATH")
        versao_lida = subprocess.run([caminho, "--version"], capture_output=True, encoding="utf-8", errors="replace",
                                     timeout=30).stdout
        if versao not in versao_lida:
            self.skipTest(f"{programa} não é o {versao}")
        td = tempfile.TemporaryDirectory(prefix="rastro1710-")
        self.addCleanup(td.cleanup)
        pasta, saidas = Path(td.name), []
        (pasta / "vazio").write_bytes(b"")
        # O programa da prova não tem chave nem espaço: no Windows, o runtime do MSYS2 expande as chaves da linha de
        # comando (`BEGIN{}` chegava como `BEGIN`).
        prova = [caminho, "--sandbox", *(["-n", "p"] if programa == "sed" else ["1"]), str(pasta / "vazio")]
        if subprocess.run(prova, capture_output=True, timeout=30, cwd=pasta).returncode != 0:
            self.skipTest(f"{programa} sem --sandbox")
        for k, partes in enumerate(args):
            arquivos = []
            for j, texto in enumerate(partes):
                (pasta / f"{k}-{j}").write_bytes(texto.encode("utf-8"))
                arquivos += ["-f", str(pasta / f"{k}-{j}")]
            saidas.append(subprocess.run([caminho, "--sandbox", *(["-n"] if programa == "sed" else []), *arquivos,
                                          str(pasta / "vazio")], capture_output=True, encoding="utf-8",
                                         errors="replace", timeout=30, cwd=pasta))
        return saidas

    def test_oraculo_do_gnu_sed(self):
        saidas = self._oraculo("sed", "GNU sed", SED_COM_ES + SED_SEM_ES)
        for scripts, r in zip(SED_COM_ES + SED_SEM_ES, saidas):
            with self.subTest(scripts=scripts):
                self.assertEqual("disabled in sandbox mode" in r.stderr, scripts in SED_COM_ES, r.stderr)
                if scripts in SED_SEM_ES:
                    self.assertEqual(r.returncode, 0, r.stderr)

    def test_oraculo_do_gawk(self):
        saidas = self._oraculo("gawk", "GNU Awk", [[p] for p in AWK_COM_ES + AWK_SEM_ES])
        for programa, r in zip(AWK_COM_ES + AWK_SEM_ES, saidas):
            with self.subTest(programa=programa):
                self.assertEqual("sandbox mode" in r.stderr, programa in AWK_COM_ES, r.stderr)
                if programa in AWK_SEM_ES:
                    self.assertEqual(r.returncode, 0, r.stderr)


if __name__ == "__main__":
    unittest.main()
