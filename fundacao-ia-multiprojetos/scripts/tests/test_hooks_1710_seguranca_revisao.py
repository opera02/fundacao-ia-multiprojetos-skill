"""Revisão de segurança da 1.7.10, rodada 4, grupo HOOKS, correções da revisão 1: cada caso falha no código de antes
(03d8eaa ou 715863c, a primeira correção do grupo) e o uso normal continua.

- HOOK-F3, curinga (média): o curinga no lugar de `projects` com um componente a mais (`../../*/*`, `<raiz>/*/*`,
  `<raiz>/*/<outro>`, `*/*/` na raiz) nega; no resíduo do HOOK-F4, também `proj[e]cts`, `{projects,x}`,
  `$'\\x70rojects'`, `$'\\x2e\\x2e'`, `{..,x}`, `$".."` e o `^` do `cmd /c`.
- HOOK-F3, redirecionamento (média): `cd 2>/dev/null X`, `cd >/dev/null X`, `cd X &>/dev/null`, `{fd}>`: a pasta vai
  para X.
- HOOK-F3, destino que não se sabe (média; regressão da primeira correção): `cd "$(pwd)"`, `cd ~+`, `cd "$OLDPWD"`,
  `cd ""` e `cd "$NADA"` seguidos de `&&` não perdem a pasta real; numa lista com `&&` e `||`, o elo roda nas pastas
  do sucesso ou da falha do anterior (`cd X || cd Y && z`, `cd /nada && true || z`, `!`).
- HOOK-F3, poda dos modelos (média; regressão): o `find` com `-prune` de projects e state pelo nome, o
  `grep -r --exclude-dir` das duas e o Get-ChildItem com o Where-Object dos modelos seguem com o alvo na raiz; sem a
  poda, acima da raiz ou recebendo do cano o que o guarda não acompanha, negam.
- HOOK-F3, baixos: a substituição de comando entre aspas duplas é reanalisada; Push-Location, Pop-Location e a pasta da
  sessão do PowerShell (`|`, parêntese e chave não a devolvem); `diff -r`, `git diff --no-index`, `find --` e o `cd` do
  `eval`; os falsos positivos de `tar -C`, `-maxdepth 1`, `-Depth`, `popd` e `time echo` saem.
- HOOK-F5: a regex da identidade com `-a =` repetido decide logo (antes, 26 pares passavam de 30 s); `find -exec`
  aninhado nega como aninhamento; a conta é linear (o tempo com 2N fica perto do dobro do tempo com N).
- HOOK-F2: o escape das aspas da raiz no comando do lembrete (o aperto da primeira correção tirou a conferência); o
  destino gravado com `.` ou `..`, ou com a próxima cópia dentro da raiz, vira o marcador.

Raiz fictícia Q: (`/mnt/q`) nos comandos; fundação fictícia em pasta temporária no lembrete.
"""

from __future__ import annotations

import os
import subprocess
import time
import unittest

from test_hooks_1710 import ferramenta, motivo, rodar
from test_hooks_1710_aviso_copia import _Base as _BaseAviso
from test_hooks_1710_aviso_copia import iso
from test_hooks_1710_identidade import HOOK, RAIZ_L, RAIZ_W
from test_hooks_1710_identidade import _Base as _BaseIdentidade

B = chr(92)  # barra invertida
PROJ = RAIZ_L + "/projects/juridico-lab"  # a pasta da sessão no Ubuntu (o lançador abre nela)
IDENTIDADE = "FUNDACAO_" + "PRINCIPAL"


def _melhor_tempo(funcao, vezes: int = 3) -> float:
    melhor = float("inf")
    for _ in range(vezes):
        inicio = time.perf_counter()
        funcao()
        melhor = min(melhor, time.perf_counter() - inicio)
    return melhor


class _Casos(_BaseIdentidade):
    def conferir(self, casos, esperado: str, tool: str = "Bash"):
        for comando, cwd in casos:
            with self.subTest(comando=comando, cwd=cwd):
                self.assertEqual(self.decide(comando, tool=tool, cwd=cwd), esperado)


class CuringaNoLugarDeProjects(_Casos):
    """HOOK-F3 (média) e o resíduo do HOOK-F4."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("grep -r FICTICIO ../../*/*", PROJ), (f"grep -r FICTICIO {RAIZ_L}/*/*", PROJ),
                       (f"grep -r FICTICIO {RAIZ_L}/*/reversa-lab", PROJ), ("grep -r FICTICIO */*/", RAIZ_W),
                       ("cat */reversa-lab/segredo.txt", RAIZ_W), (f"ls {RAIZ_L}/p*/r*", PROJ),
                       ("rg FICTICIO ../../*/*", PROJ), (f"tar cf - {RAIZ_L}/*/*", PROJ),
                       ("cat /mnt/*/IA/fundacao/*/reversa-lab/a", PROJ)), "deny")
        self.conferir(((f"Get-Content {RAIZ_W}{B}*{B}reversa-lab{B}a", PROJ),
                       (f"Get-ChildItem -Recurse {RAIZ_W}{B}*{B}reversa-lab", PROJ)), "deny", tool="PowerShell")
        texto = motivo(HOOK, {**ferramenta("Bash", command="grep -r FICTICIO ../../*/*"), "cwd": PROJ}, **self.env)
        for trecho in ("guarda-corpo", "curinga"):
            self.assertIn(trecho, texto)

    def test_residuo_do_f4_nega(self):
        self.conferir((("cat proj[e]cts/reversa-lab/a", RAIZ_W), ("cat {projects,zz}/reversa-lab/a", RAIZ_W),
                       ("cat $'" + B + "x70rojects'/reversa-lab/a", RAIZ_W),
                       ("cat $'" + B + "160rojects'/reversa-lab/a", RAIZ_W),
                       ("cat $'" + B + "x2e" + B + "x2e'/reversa-lab/a", PROJ), ("cat {..,x}/reversa-lab/a", PROJ),
                       ('cat $".."/reversa-lab/a', PROJ), ("cat proj[!x]cts/reversa-lab/a", RAIZ_W)), "deny")
        self.conferir((('cmd /c "type proj^ects' + B + "reversa-lab" + B + 'a"', RAIZ_W),), "deny", tool="PowerShell")

    def test_uso_normal_segue(self):
        self.conferir((("ls */", RAIZ_W), ("cat docs/*.md", RAIZ_W), ("grep -r x ../../*/juridico-lab", PROJ),
                       ("echo {1..3}", RAIZ_W), ("mkdir -p src/{a,b}", PROJ), ("cat minutas/*.md", PROJ),
                       ("printf $'a" + B + "tb" + B + "n'", PROJ), ("rg x minutas/**/*.md", PROJ),
                       ("""curl -d '{"a":{"b":1,"c":2},"d":{"e":3,"f":4},"g":{"h":5,"i":6},"j":{"k":7,"l":8}}' """
                        "https://exemplo.invalid/api", PROJ), (f"ls {RAIZ_L}/*/juridico-lab", PROJ)), "sem_decisao")


class CdComRedirecionamento(_Casos):
    """HOOK-F3 (média): o alvo do redirecionamento não é o destino do cd."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("cd 2>/dev/null projects && cat reversa-lab/segredo.txt", RAIZ_W),
                       (f"cd >/dev/null {RAIZ_L} && grep -r FICTICIO .", PROJ), ("pushd 1>/dev/null projects", RAIZ_W),
                       (f"cd {RAIZ_L} &>/dev/null && grep -r x .", PROJ),
                       (f"cd {{fd}}>/dev/null {RAIZ_L} && rg x", PROJ), (f"cd 2>&1 {RAIZ_L} && rg x", PROJ),
                       ("cd </dev/null projects; ls", RAIZ_W)), "deny")
        self.conferir(((f"Set-Location {RAIZ_W} 2>$null; Get-ChildItem -Recurse", PROJ),), "deny", tool="PowerShell")

    def test_uso_normal_segue(self):
        self.conferir((("cd minutas 2>/dev/null && grep -r x .", PROJ), ("grep -r x . 2>/dev/null", PROJ),
                       ("ls 2>&1 | head", PROJ), ("cat < minutas/a.md", PROJ), ("rg x minutas > /tmp/saida.txt", PROJ),
                       ("cat <<FIM\nlinha\nFIM", PROJ)), "sem_decisao")
        self.assertEqual(self.decide("echo x > projects/reversa-lab/a"), "deny")  # o alvo continua conferido


class CdParaDestinoQueNaoSeSabe(_Casos):
    """HOOK-F3 (média): a pasta real não se perde depois de `cd` para destino que não se sabe (regressão da primeira
    correção); numa lista com `&&` e `||`, cada elo roda nas pastas do sucesso ou da falha do anterior."""

    def test_formas_da_revisao_negam(self):
        for cd in ('cd "$(pwd)"', "cd ~+", 'cd "$OLDPWD"', 'cd ""', 'cd "$NADA"', "cd -", "pushd +1", "cd ~-"):
            with self.subTest(cd=cd):
                self.assertEqual(self.decide(cd + " && cat ../reversa-lab/segredo.txt", cwd=PROJ), "deny")
        self.conferir((("cd '' && grep -r FICTICIO ..", PROJ), ('cd "$X" && rg FICTICIO', RAIZ_W),
                       ('cd "$(pwd)" && rg x', RAIZ_W)), "deny")
        self.conferir((('Set-Location "$X"; Get-ChildItem -Recurse', RAIZ_W),), "deny", tool="PowerShell")

    def test_lista_com_e_e_ou(self):
        self.conferir(((f"cd {RAIZ_L} || cd /tmp && grep -r x .", PROJ),
                       ("cd /tmp/nada && true || grep -r x .", RAIZ_W), ("! cd /tmp/nada && grep -r x .", RAIZ_W),
                       # `cd X || exit; ...`: falso positivo declarado (revisão 2 da rodada 4) — o grep só roda em X,
                       # mas o guarda fica com a pasta de antes e a de X; use `cd X && ...`
                       ("cd /tmp || exit; grep -r x .", RAIZ_W), ("cd /tmp & grep -r x .", RAIZ_W),
                       ("(cd /tmp) && grep -r x .", RAIZ_W)), "deny")
        self.conferir((("cd /tmp && grep -r x .", RAIZ_W),
                       ("cd projects/juridico-lab && grep -r x . || echo x", RAIZ_W),
                       ("cd minutas && grep -r x . && cd .. && ls", PROJ), ("(cd /tmp && grep -r x .)", RAIZ_W),
                       ('cd "$(pwd)" && cat minutas/a.md', PROJ), ("cd ~+ && ls", PROJ)), "sem_decisao")


class PodaDosModelos(_Casos):
    """HOOK-F3 (média): a busca na raiz com a poda dos modelos de auditoria e revisão (SKILL.md, passo 2) segue
    (regressão da primeira correção); sem a poda, acima da raiz ou recebendo do cano o que o guarda não acompanha,
    nega."""

    FIND = f"find {RAIZ_L} -type d " + B + "( -name projects -o -name state " + B + ") -prune -o -type f -print"
    GCI = (f"Get-ChildItem -Force -LiteralPath {RAIZ_W} | Where-Object Name -notin 'projects','state' | "
           "Get-ChildItem -Force -Recurse -File")

    def test_formas_dos_modelos_seguem(self):
        self.conferir(((self.FIND, PROJ), (self.FIND, RAIZ_W),
                       (f"grep -r --exclude-dir=projects --exclude-dir=state senha {RAIZ_L}", PROJ),
                       ("grep -r --exclude-dir=projects --exclude-dir=state senha .", RAIZ_W),
                       ("grep -rn --exclude-dir={projects,state} senha .", RAIZ_W),
                       (self.FIND.replace("-name state", "-iname STATE"), PROJ)), "sem_decisao")
        self.conferir(((self.GCI, RAIZ_W), (self.GCI, PROJ),
                       (f"Get-ChildItem -LiteralPath {RAIZ_W}{B}projects{B}juridico-lab | Get-ChildItem -Recurse",
                        RAIZ_W)), "sem_decisao", tool="PowerShell")

    def test_sem_a_poda_nega(self):
        self.conferir(((f"find {RAIZ_L} -type f", PROJ),
                       (f"find {RAIZ_L} -type d -name projects -prune -o -type f -print", PROJ),
                       (self.FIND.replace("-type d", "-depth -type d"), PROJ),
                       (self.FIND.replace(RAIZ_L, "/mnt/q/IA"), PROJ),
                       ("grep -r --exclude-dir=projects senha .", RAIZ_W),
                       (f"grep -r --exclude-dir=state senha {RAIZ_L}", PROJ)), "deny")
        cano = f"Get-ChildItem {RAIZ_W} | ForEach-Object FullName | Get-ChildItem -Recurse"
        item = f"Get-Item {RAIZ_W} | Where-Object Name -notin 'projects','state' | Get-ChildItem -Recurse"
        self.conferir(((f"Get-ChildItem -LiteralPath {RAIZ_W} | Get-ChildItem -Recurse -File", RAIZ_W),
                       (f"Get-ChildItem -LiteralPath {RAIZ_W} | Get-ChildItem -Recurse -File", PROJ), (cano, PROJ),
                       (item, PROJ), (f"(Get-ChildItem {RAIZ_W}) | Get-ChildItem -Recurse", PROJ)), "deny",
                      tool="PowerShell")
        self.assertIn("cano", motivo(HOOK, {**ferramenta("PowerShell", command=cano), "cwd": PROJ}, **self.env))


class SubstituicaoEntreAspasEPastaDoPowerShell(_Casos):
    """HOOK-F3 (baixa): a substituição de comando entre aspas duplas é reanalisada; Push-Location e Pop-Location; no
    PowerShell a pasta é da sessão, e `|`, parêntese e chave não a devolvem."""

    def test_formas_da_revisao_negam(self):
        self.conferir(((f'x="$(grep -r FICTICIO {RAIZ_L}/projects)"', PROJ), ('x="$(grep -r FICTICIO ..)"', PROJ),
                       (f'echo "$(find {RAIZ_L}/projects -name segredo.txt -exec cat {{}} +)"', PROJ),
                       ('echo "$(cd /; rg FICTICIO)"', PROJ), ('echo "`grep -r FICTICIO ..`"', PROJ),
                       ('echo "$(echo "$(grep -r x ..)")"', PROJ)), "deny")
        self.conferir((('Write-Output "$(Get-ChildItem -Recurse ..)"', PROJ),
                       ("Push-Location Q:" + B + "IA; Get-ChildItem -Recurse", PROJ)), "deny", tool="PowerShell")

    def test_pasta_da_sessao_do_powershell(self):
        self.conferir(((f"Set-Location {RAIZ_W} | Out-Null; Get-ChildItem -Recurse", PROJ),
                       (f"if ($true) {{ Set-Location {RAIZ_W} }}; Get-ChildItem -Recurse", PROJ),
                       (f"(Set-Location {RAIZ_W}); gci -r", PROJ),
                       (f"Push-Location {RAIZ_W}{B}projects{B}juridico-lab; Pop-Location; gci -r", RAIZ_W)), "deny",
                      tool="PowerShell")

    def test_uso_normal_segue(self):
        self.conferir((('x="$(git status)"', PROJ), ('echo "$(date)"', PROJ), ('echo "`pwd`"', PROJ),
                       ('x="$(grep -r x minutas)"', PROJ), ('x="$(echo "a b")"', PROJ)), "sem_decisao")
        self.conferir((('Write-Output "$(Get-Date)"', PROJ), ("if ($x) { Set-Location minutas }; gci -r", PROJ)),
                      "sem_decisao", tool="PowerShell")


class LeitoresForaDaLista(_Casos):
    """HOOK-F3 (baixa): `diff -r`, `git diff --no-index`, `find --` e o `cd` dentro do `eval` e do `iex`."""

    def test_formas_da_revisao_negam(self):
        self.conferir(((f"diff -rN /tmp/vazio {RAIZ_L}/projects", PROJ), ("diff -rN /tmp/vazio ..", PROJ),
                       ("diff --recursive /tmp/a ..", PROJ),
                       (f"git diff --no-index /tmp/vazio {RAIZ_L}/projects", PROJ),
                       (f"find -- {RAIZ_L} -name segredo.txt -exec cat {{}} +", PROJ),
                       (f"eval cd {RAIZ_L} && grep -r FICTICIO .", PROJ), (f"eval 'cd {RAIZ_L};' grep -r x .", PROJ)),
                      "deny")
        self.conferir(((f"iex 'Set-Location {RAIZ_W}'; gci -r", PROJ),), "deny", tool="PowerShell")

    def test_uso_normal_segue(self):
        self.conferir((("diff -r minutas /tmp/x", PROJ), ("diff a.md b.md", PROJ),
                       ("eval cd minutas && grep -r x .", PROJ), ("git diff --no-index a.md b.md", PROJ),
                       ("sdiff a.md b.md", PROJ)), "sem_decisao")


class FalsosPositivosDaPrimeiraCorrecao(_Casos):
    """HOOK-F3 (baixa): o que a primeira correção negava sem precisar e o que continua negado."""

    def test_seguem(self):
        self.conferir((("tar czf /tmp/x.tgz -C .. juridico-lab", PROJ),
                       ("tar -C .. -czf /tmp/x.tgz juridico-lab", PROJ),
                       ("tar --directory=.. -czf /tmp/x.tgz juridico-lab", PROJ), ("find .. -maxdepth 1 -type d", PROJ),
                       ("tree -L 1 ..", PROJ), ("pushd / && popd && rg x", PROJ), ("time echo ls -R /", PROJ),
                       ("then echo grep -r x /", PROJ)), "sem_decisao")
        self.conferir((("Get-ChildItem -Depth 1", RAIZ_W), ("gci -Depth 0 ..", PROJ)), "sem_decisao", tool="PowerShell")

    def test_continuam_negados(self):
        self.conferir((("tar czf /tmp/x.tgz -C .. reversa-lab", PROJ), ("tar czf /tmp/x.tgz -C .. .", PROJ),
                       ("tar xf /tmp/x.tgz -C ..", PROJ), ("find .. -maxdepth 2 -type f", PROJ),
                       ("find .. -maxdepth 1 -exec ls {} " + B + ";", PROJ), ("pushd / && rg x", PROJ),
                       ("time grep -r x /", PROJ), ("sudo -u root grep -r x /", PROJ), ("nice -n 5 grep -r x /", PROJ),
                       ("time --format x grep -r x /", PROJ), ("cd -P /mnt/q/IA/fundacao && grep -r x .", PROJ),
                       ("cd -- /mnt/q/IA/fundacao && rg x", PROJ)), "deny")
        self.conferir((("Get-ChildItem -Depth 1 ..", PROJ), ("gci -Depth 2", RAIZ_W),
                       (f"Set-Location -Path:{RAIZ_W}; gci -r", PROJ),
                       (f"Set-Location -LiteralPath {RAIZ_W}; gci -r", PROJ)), "deny", tool="PowerShell")


class PrazoDaRevisao(_Casos):
    """HOOK-F5 (baixa): a regex da identidade e o `find -exec` aninhado decidem logo; a conta é linear."""

    def test_regex_com_separador_ambiguo_decide_logo(self):
        # Um cmdlet com `-a =` repetido: cada par tinha duas leituras, e 20 pares levavam 1 s (o dobro a cada par).
        for tool in ("Bash", "PowerShell"):
            for comando, esperado in (("Set-Item " + "-a = " * 21 + f"; $env:{IDENTIDADE}='admin'", "deny"),
                                      ("Set-Item " + "-a = " * 21 + f"; echo {IDENTIDADE}", "sem_decisao"),
                                      ("Set-Item " + "-a = " * 21, "sem_decisao")):
                with self.subTest(tool=tool, esperado=esperado, comando=comando[-30:]):
                    inicio = time.perf_counter()
                    self.assertEqual(self.decide(comando, tool=tool), esperado)
                    self.assertLess(time.perf_counter() - inicio, 0.5)

    def test_regex_pelo_processo_longe_do_prazo(self):
        # A forma da revisão (26 pares: mais de 30 s) e a de 15 KB, pelo processo como o host o chama.
        for comando, nega in (("Set-Item " + "-a = " * 26 + f"; $env:{IDENTIDADE}='admin'; echo fim", True),
                              ("Set-Item " + "-a = " * 3000 + f"; echo {IDENTIDADE}", False)):
            with self.subTest(tamanho=len(comando)):
                inicio = time.monotonic()
                try:
                    p = rodar(HOOK, ferramenta("PowerShell", command=comando), timeout=10, **self.env)
                except subprocess.TimeoutExpired:
                    self.fail("sem decisão em 10 s, o prazo do perfil")
                self.assertEqual((p.returncode, b'"deny"' in p.stdout), (0, nega), p.stdout[-200:])
                self.assertLess(time.monotonic() - inicio, 5)

    def test_formas_da_identidade_continuam(self):
        for comando in (f'Set-Item -Path "env:{IDENTIDADE}" -Value "titular"', f"Set-Item 'env:{IDENTIDADE}' 'titular'",
                        f"Set-Item -Path:env:{IDENTIDADE} -Value titular", f"Set-Item -Path=env:{IDENTIDADE} -Value t",
                        f"Set-Item Env:{B}{IDENTIDADE} titular", f'Remove-Item "env:{IDENTIDADE}"',
                        f"New-Item -Path env: -Name {IDENTIDADE} -Value titular",
                        f"Set-Item -Value =x env:{IDENTIDADE}",
                        f"[Environment]::SetEnvironmentVariable('{IDENTIDADE}','x')",
                        f"[Environment]::SetEnvironmentVariable( 'X' + '{IDENTIDADE}' , 'x')"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, tool="PowerShell"), "deny")
        for comando in (f"Get-ChildItem env:{IDENTIDADE}", f"if ($env:{IDENTIDADE} -eq 'titular') {{ 'ok' }}",
                        f"[Environment]::SetEnvironmentVariable('X','y'); echo {IDENTIDADE}"):
            with self.subTest(comando=comando):
                self.assertEqual(self.decide(comando, tool="PowerShell"), "sem_decisao")

    def test_find_exec_aninhado_nega_como_aninhamento(self):
        comando = "find . " + "-exec find . " * 1240
        self.assertLessEqual(len(comando), 16 * 1024)
        inicio = time.perf_counter()
        self.assertEqual(self.decide(comando, cwd=PROJ), "deny")
        self.assertLess(time.perf_counter() - inicio, 1)
        self.assertIn("aninhado", motivo(HOOK, {**ferramenta("Bash", command=comando), "cwd": PROJ}, **self.env))
        self.conferir((("find . -exec find . -exec grep -r x / " + B + "; " + B + ";", PROJ),), "deny")
        self.conferir((("find . -exec grep x {} " + B + ";", PROJ),
                       ("find minutas -exec find {} -name x " + B + ";", PROJ)), "sem_decisao")

    def razao(self, prefixo: str, miolo: str, sufixo: str, tool: str = "Bash", **env) -> tuple[float, float]:
        """(o melhor tempo logo abaixo do teto, ele dividido pelo da metade do tamanho)."""
        def roda(tamanho):
            comando = prefixo + miolo * ((tamanho - len(prefixo) - len(sufixo)) // len(miolo)) + sufixo
            return lambda: self.decide(comando, tool=tool, cwd=PROJ, **env)
        grande, metade = _melhor_tempo(roda(16 * 1024 - 64)), _melhor_tempo(roda(8 * 1024 - 32))
        return grande, grande / max(metade, 1e-6)

    def test_a_conta_e_linear(self):
        # Linear dá perto de 2; o quadrado, perto de 4. Abaixo de 0,05 s a conta não pesa (o ruído domina a razão).
        raiz_em_projects = {"FUNDACAO_RAIZ": B.join(("Q:", "u", "projects", "fund"))}
        rabo = f" ; cat '{RAIZ_L}/projects/reversa-lab/segredo.txt'"
        casos = [("echo '", '/projects/juridico-lab"', "'" + rabo, "Bash", {}),
                 ("echo '", "projects/ ", "'" + rabo, "Bash", {}),
                 ("echo '", "a=projects/juridico-lab/x ", "'" + rabo, "Bash", {}),
                 ("echo '", "/x/../", "'" + rabo, "Bash", {}),
                 ("echo '", "Q:/u/projects/fund/projects/juridico-lab/ ", "'" + rabo, "Bash", raiz_em_projects),
                 ("", "Set-Item -a ", f"; echo {IDENTIDADE}", "PowerShell", {}),
                 ("", "SetEnvironmentVariable(", f") {IDENTIDADE}", "PowerShell", {}),
                 ("echo ", '"$(ls)" ', "", "Bash", {}), ("cd a; cd b; cd c; echo ", "*/* ", "", "Bash", {}),
                 ("", "pushd a; ", "ls", "Bash", {}), ("tar cf x ", "-C a b ", "", "Bash", {}),
                 ("", 'cd "$X" && ', "rg x", "Bash", {}), ("echo ", "{a,b}{c,d} ", "", "Bash", {})]
        for prefixo, miolo, sufixo, tool, env in casos:
            with self.subTest(miolo=miolo):
                grande, razao = self.razao(prefixo, miolo, sufixo, tool, **env)
                if grande >= 0.05 and razao >= 3:  # uma segunda medida: a carga da máquina pesa numa só
                    grande, razao = min((grande, razao), self.razao(prefixo, miolo, sufixo, tool, **env),
                                        key=lambda medida: medida[1])
                self.assertLess(grande, 3)  # longe do prazo do perfil (10 s) mesmo com a máquina carregada
                self.assertTrue(grande < 0.05 or razao < 3, f"{grande:.3f} s com 16 KiB; razão {razao:.2f}")


class EscapeEDestinoNoLembrete(_BaseAviso):
    """HOOK-F2: a raiz com aspas vai escapada ao comando do lembrete (o aperto da primeira correção tirou a única
    conferência do escape); o destino gravado com `.` ou `..`, ou com a próxima cópia dentro da raiz, vira o
    marcador."""

    def test_aspas_na_raiz_vao_escapadas(self):
        nomes = ["fund d'agua"] + (["fund d\u2019agua"] if os.name == "nt" else [])
        for nome in nomes:
            with self.subTest(nome=nome):
                raiz = self.base / nome
                (raiz / "registry").mkdir(parents=True)
                texto = self.contexto(self.rodar(raiz=False, FUNDACAO_RAIZ=str(raiz)))
                if os.name == "nt":  # o PowerShell lê também a aspa tipográfica como aspa simples: dobrada
                    esperado = str(raiz).replace("'", "''").replace("\u2019", "\u2019\u2019")
                else:
                    esperado = str(raiz).replace("'", "'" + B + "''")
                self.assertIn(f"--raiz '{esperado}' backup", texto)

    def test_ponto_ponto_ou_dentro_da_raiz_vira_o_marcador(self):
        if os.name == "nt":
            fora = [B.join(("C:", "Copias", "..", "..", "Users", "x", "OneDrive", "semanal")),
                    B.join(("C:", "Copias", ".", "semanal"))]
            dentro = [str(self.raiz).upper() + B + "state" + B + "semanal-x"]
        else:
            fora, dentro = ["/srv/copias/../../home/x/semanal", "/srv/copias/./semanal"], []
        dentro += [str(self.raiz / "state" / "semanal-x"), str(self.raiz / "semanal-x"),
                   str(self.raiz / "projects" / "juridico-lab" / "semanal-x")]
        for destino in fora + dentro:
            with self.subTest(destino=destino):
                self.registrar(criada_em=iso(30), destino=destino)
                texto = self.contexto(self.rodar())
                self.assertIn("<pasta das cópias", texto)
                self.assertNotIn(destino, texto)
                self.assertNotIn("que as sessões gravam", texto)
        self.registrar(criada_em=iso(30))  # a pasta fora da raiz continua no comando
        self.assertIn(str(self.copias), self.contexto(self.rodar()))


if __name__ == "__main__":
    unittest.main()
