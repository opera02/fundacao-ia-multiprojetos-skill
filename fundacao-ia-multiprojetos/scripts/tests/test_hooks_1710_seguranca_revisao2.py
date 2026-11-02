"""Revisão de segurança da 1.7.10, rodada 4, grupo HOOKS, correções da revisão 2: cada caso que nega falha no código
de antes (03d8eaa, 715863c ou 55a8ac8, a correção da revisão 1) e o uso normal continua.

- HOOK-F3, Get-ChildItem (média): `-s` (o apelido do `-Recurse`) e o parâmetro comum com valor separado
  (`-ErrorAction SilentlyContinue`, `-ea 0`, `-OutVariable x`...) negam na raiz e com `..`; todos os caminhos
  posicionais contam, e a lista com vírgula dá um alvo por item.
- HOOK-F3, curinga (média, da revisão 1): a chave sem vírgula no próprio nível não casa qualquer nome — JSON,
  dicionário do Python, `'{0}/{1}' -f` e `[0-9]{2}/` citados da raiz seguem; o `{}` do `xargs -I{}` e o extglob negam.
- HOOK-F3, baixos: mais de 8 pastas possíveis nega (a do meio se perdia); o `{}` do `find -exec` vira o ponto de
  partida, sem o desconto do `-maxdepth` nem a poda; o texto dado a um lançador pela entrada (`bash <<< '...'`,
  `echo '...' | sh`, `'...' | iex`) e o `. /dev/stdin <<<`; o comentário, `pushd -n`, `popd -n`, a função `cd` e a
  chave vazia; as opções lidas como o programa (começo do nome, dígito no grupo, tabela por programa, `git diff` com
  caminhos, `env -S`, `env -C`, `sudo -D`, `pwsh -wd`, `Start-Process -WorkingDirectory` e `-ArgumentList`);
  `projects.\\`, a lista com vírgula e `~+/..`; `command -v` segue.
- HOOK-F5: o `eval` aninhado sobre chaves expandidas decide em menos de 1 s (antes, 3,7 KB levavam 7 s).
- HOOK-F2: no Windows, o destino com ponto no fim de um nome (`<raiz>.\\state\\x`) vira o marcador.

Raiz fictícia Q: (`/mnt/q`) nos comandos; fundação fictícia em pasta temporária no lembrete.
"""

from __future__ import annotations

import os
import time
import unittest

from test_hooks_1710 import decisao, ferramenta, motivo
from test_hooks_1710_aviso_copia import _Base as _BaseAviso
from test_hooks_1710_aviso_copia import iso
from test_hooks_1710_identidade import HOOK, RAIZ_L, RAIZ_W
from test_hooks_1710_identidade import _Base as _BaseIdentidade

B = chr(92)  # barra invertida
PROJ = RAIZ_L + "/projects/juridico-lab"  # a pasta da sessão no Ubuntu (o lançador abre nela)
PODA = "-type d " + B + "( -name projects -o -name state " + B + ") -prune -o"


class _Casos(_BaseIdentidade):
    def conferir(self, casos, esperado: str, tool: str = "Bash"):
        for comando, cwd in casos:
            with self.subTest(comando=comando, cwd=cwd):
                self.assertEqual(self.decide(comando, tool=tool, cwd=cwd), esperado)


class GetChildItemDoPowerShell(_Casos):
    """HOOK-F3 (média): o apelido `-s` e os parâmetros comuns com valor."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("Get-ChildItem -Recurse -ErrorAction SilentlyContinue | Select-String x | ForEach-Object Line",
                        RAIZ_W), ("gci -r -ea 0 -Filter *.txt | Select-String x", RAIZ_W),
                       ("Get-ChildItem -Recurse -ErrorAction SilentlyContinue .. | Select-String x", PROJ),
                       ("dir -s .. | Select-String x", PROJ), ("ls -s ..", PROJ),
                       (f"Get-ChildItem -s -File {RAIZ_W}{B}projects", PROJ),
                       (f"Get-ChildItem -Recurse -File -ErrorAction SilentlyContinue {RAIZ_W}{B}projects", PROJ),
                       ("Get-ChildItem -Recurse -WarningAction SilentlyContinue -OutVariable x", RAIZ_W),
                       ("gci -r -PipelineVariable p ..", PROJ), ("Get-ChildItem -Recurse .,.. | Select-String x", PROJ),
                       ("Get-ChildItem -Recurse -Path minutas,..", PROJ)), "deny", tool="PowerShell")

    def test_uso_normal_segue(self):
        self.conferir((("Get-ChildItem -Recurse -ErrorAction SilentlyContinue minutas", PROJ),
                       ("gci -r -ea 0 -Filter *.md", PROJ), ("Get-ChildItem docs *.md -Recurse", RAIZ_W),
                       (f"Get-ChildItem -s projects{B}juridico-lab -ErrorAction Stop", RAIZ_W),
                       ("Get-ChildItem -Recurse -Path minutas,modelos", PROJ)), "sem_decisao", tool="PowerShell")


class ChaveSemVirgula(_Casos):
    """HOOK-F3 (média; regressão da revisão 1): só a chave com vírgula no próprio nível (ou o `{}`) é curinga."""

    def test_uso_normal_na_raiz_segue(self):
        self.conferir((("python -c \"import json; print(json.dumps({'a': 'b/c'}))\"", RAIZ_W),
                       ('python -c "x = [1, 2]; print(x[0] / 2)"', RAIZ_W),
                       ("curl -s -d '{\"url\":\"https://exemplo.invalid/x\"}' https://api.exemplo.invalid/v1", RAIZ_W),
                       ("echo '{\"data\":\"2026/11/01\"}' > dados.json", RAIZ_W),
                       ("jq '{nome: .a, caminho: \"x/y\"}' dados.json", RAIZ_W),
                       ("node -e 'console.log({a: 1}.a / 2)'", RAIZ_W),
                       ("grep -E '[0-9]{2}/[0-9]{4}' notas.txt", RAIZ_W), ('echo "{x}/y"', RAIZ_W),
                       ("curl -d '{\"a\":{\"b\":1,\"c\":2},\"d\":\"e/f\"}' https://exemplo.invalid/api", RAIZ_W)),
                      "sem_decisao")
        corpo = "-Body '{\"arquivo\":\"docs/a.md\"}'"
        self.conferir((("'{0}/{1}' -f 'a', 'b'", RAIZ_W), ('Write-Output "{0}/{1}"', RAIZ_W),
                       ("$x = '{\"a\":\"b/c\"}' | ConvertFrom-Json; $x.a", RAIZ_W),
                       (f"Invoke-RestMethod -Uri https://api.exemplo.invalid -Method Post {corpo}", RAIZ_W)),
                      "sem_decisao", tool="PowerShell")

    def test_continuam_negados(self):
        self.conferir((("ls | xargs -I{} cp -r {} /tmp/x", RAIZ_W), ("cat proj[e]cts/reversa-lab/a", RAIZ_W),
                       ("cat {projects,zz}/reversa-lab/a", RAIZ_W), ("cat '{projects,zz}'/reversa-lab/a", RAIZ_W),
                       ("cat 'p{r,x}ojects'/reversa-lab/a", RAIZ_W), ("cat '{zz,{projects,yy}}'/reversa-lab/a", RAIZ_W),
                       ("cat */reversa-lab/a", RAIZ_W), ("grep -r x ../../*/*", PROJ),
                       (f"cat {RAIZ_L}/*/reversa-lab/a", PROJ)), "deny")
        self.conferir(((f"Get-Content {RAIZ_W}{B}*{B}reversa-lab{B}a", PROJ),), "deny", tool="PowerShell")


class ExtglobForaDeAspas(_Casos):
    """HOOK-F3 (baixa, da revisão 1): `@(...)`, `!(...)` fora de aspas ficam na palavra (casam qualquer nome)."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("cat @(projects)/reversa-lab/a", RAIZ_W), (f"cat '{RAIZ_L}/'@(projects)/reversa-lab/a", PROJ),
                       (f"cat {RAIZ_L}/!(state)/reversa-lab/a", PROJ), (f"grep -r x {RAIZ_L}/@(projects)", PROJ),
                       ("!(grep -r x ..)", PROJ)), "deny")

    def test_uso_normal_segue(self):
        self.conferir((("echo '@(x)'", PROJ), ("ls *.md", PROJ), ("ls !(*.md)", PROJ)), "sem_decisao")


class PastasPossiveisDemais(_Casos):
    """HOOK-F3 (baixa; regressão da revisão 1): nenhuma pasta possível é descartada; acima de 8, nega."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("cd /fora/n1/x; cd /fora/n2/x; cd docs || true && grep -r x .", RAIZ_W),
                       ("cd /fora/n1/x; cd /fora/n2/x; cd docs || true && grep -r x ..", PROJ),
                       ("cd a; cd b; cd c; cd d; ls", PROJ)), "deny")
        self.conferir((("sl C:" + B + "nada1; sl C:" + B + "nada2; Get-Date | sl C:" + B + "nd | sl C:" + B + "ne | "
                        "sl C:" + B + "nf; gci -r | Select-String x", RAIZ_W),), "deny", tool="PowerShell")
        texto = motivo(HOOK, {**ferramenta("Bash", command="cd a; cd b; cd c; cd d; ls"), "cwd": PROJ}, **self.env)
        self.assertIn("pastas possíveis demais", texto)

    def test_uso_normal_segue(self):
        self.conferir((("cd /tmp && grep -r x .", RAIZ_W), ("cd a; cd b; cd c; ls", PROJ)), "sem_decisao")


class ExecDoFind(_Casos):
    """HOOK-F3 (baixa; regressão da revisão 1): o `{}` do `-exec` é o ponto de partida."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("find .. -maxdepth 0 -exec grep -r x {} +", PROJ),
                       ("find .. -maxdepth 0 -exec cp -r {} /fora/copia " + B + ";", PROJ),
                       (f"find '{RAIZ_L}' {PODA} -type d -exec grep -r x {{}} +", PROJ),
                       (f"find '{RAIZ_L}' -maxdepth 0 -exec grep -r x {{}} +", PROJ),
                       ("find ../.. -maxdepth 0 -execdir grep -r x . " + B + ";", PROJ),
                       (f"find {RAIZ_L}/projects/juridico-lab -maxdepth 0 -execdir grep -r x . " + B + ";", PROJ)),
                      "deny")

    def test_uso_normal_segue(self):
        self.conferir((("find minutas -exec grep x {} " + B + ";", PROJ), ("find . -exec grep x {} " + B + ";", PROJ),
                       ("find minutas -execdir grep -r x . " + B + ";", PROJ),
                       ("find . -name '*.md' -execdir grep -l x {} +", PROJ),
                       (f"find {RAIZ_L} {PODA} -type f -exec grep -l x {{}} +", RAIZ_W)), "sem_decisao")


class TextoDadoAoLancador(_Casos):
    """HOOK-F3 (baixa; regressão da revisão 1): o here-string e o cano dados a quem lê comandos."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("bash <<< 'grep -r x ..'", PROJ), ("sh <<< 'grep -r x ..'", PROJ),
                       (". /dev/stdin <<< 'cd ../..'; grep -r x .", PROJ), ("echo 'grep -r x ..' | bash", PROJ),
                       ("printf '%s' 'cd ..; grep -r x .' | sh -s", PROJ)), "deny")
        self.conferir((("'Get-ChildItem -Recurse ..' | iex", PROJ),), "deny", tool="PowerShell")

    def test_uso_normal_segue(self):
        self.conferir((("bash <<< 'ls'", PROJ), ("echo ls | bash", PROJ), ("bash -c 'cat' <<< 'grep -r x ..'", PROJ),
                       ("cat <<< 'grep -r x ..'", PROJ)), "sem_decisao")
        self.conferir((("'Get-Date' | iex", PROJ),), "sem_decisao", tool="PowerShell")


class PastaAcompanhada(_Casos):
    """HOOK-F3 (baixa): comentário, `pushd -n`, `popd -n`, a função `cd` e a chave vazia."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("true #; cd /fora/a/b &&\ngrep -r x ..", PROJ), ("true #; cd /fora &&\ngrep -r x .", RAIZ_W),
                       ("true #; cd /tmp &&\ncat ../reversa-lab/segredo.txt", PROJ),
                       ("pushd -n /fora/a/b >/dev/null && grep -r x ..", PROJ),
                       ("pushd -n /fora >/dev/null && grep -r x .", RAIZ_W),
                       ("pushd ../.. >/dev/null && popd -n >/dev/null && grep -r x .", PROJ),
                       ("cd() { :; }; cd /fora && grep -r x .", RAIZ_W),
                       ("alias cd=true; cd /fora && grep -r x .", RAIZ_W),
                       ('cd() { builtin cd "$@"; }; cd ../.. && grep -r x .', PROJ),
                       ("{cd,} ../.. && grep -r x .", PROJ), ("cd {,} .. && grep -r x .", PROJ),
                       ('echo "$(echo a #)"\necho b\n)"\ngrep -r x ..', PROJ)), "deny")
        self.conferir((("Get-Date #x; Set-Location C:" + B + "fora &&\nGet-ChildItem -Recurse", RAIZ_W),
                       ("Write-Output a<#x#>b; Get-ChildItem -Recurse", RAIZ_W),
                       ("Set-Item function:Set-Location {}; Set-Location C:" + B + "fora && gci -r", RAIZ_W)), "deny",
                      tool="PowerShell")

    def test_uso_normal_segue(self):
        self.conferir((("echo a#b; cd minutas && grep -r x .", PROJ), ("grep -r x . # busca no projeto", PROJ),
                       ("pushd -n /tmp && popd && ls", PROJ), ('echo "x # y" && grep -r x minutas', PROJ),
                       ("echo x >#y; grep -r x ..", PROJ)), "sem_decisao")
        self.conferir((("Write-Output 'q' <# comentario #> 'r'", PROJ),), "sem_decisao", tool="PowerShell")


class OpcoesComoOProgramaLe(_Casos):
    """HOOK-F3 (baixa): começo do nome, dígito no grupo, tabela por programa, `git diff`, `env`, `sudo -D`, `pwsh -wd`
    e o Start-Process (`-WorkingDirectory` e a lista do `-ArgumentList`)."""

    def test_formas_da_revisao_negam(self):
        self.conferir((("grep --recur x ..", PROJ), ("grep -d rec x ..", PROJ), ("grep -2r x ..", PROJ),
                       ("ls --recur ..", PROJ), ("ls -1R ..", PROJ), ("ls -R --context ..", PROJ),
                       ("du -a --time ..", PROJ), ("diff --recur -N /fora/vazio ..", PROJ),
                       ("cp --recur .. /fora/copia", PROJ), ("cp --arch ../.. /fora/copia2", PROJ),
                       ("cp -r --context .. /fora/copia3", PROJ), ("tar --dir=.. -cf - reversa-lab | tar -xOf -", PROJ),
                       ("git diff /fora/vazio ..", PROJ), ("env -S 'grep -r x ..'", PROJ),
                       ("grep -r --group-separator x FICTICIO", RAIZ_W), ("rg --color never FICTICIO", RAIZ_W),
                       ("ls -R --time atime", RAIZ_W), ("env -C .. grep -r x .", PROJ), ("env --chdir=.. ls -R", PROJ),
                       ("env -iS 'grep -r x ..'", PROJ), ("sudo -D .. grep -r x .", PROJ)), "deny")
        self.conferir((("pwsh -wd .. -c 'Get-ChildItem -Recurse'", PROJ),
                       ("Start-Process -NoNewWindow -Wait powershell -ArgumentList '-c','gci -Recurse ..'", PROJ),
                       ("Start-Process -WorkingDirectory .. -Wait powershell -ArgumentList '-c','gci -r'", PROJ),
                       ("saps -wo .. pwsh -ArgumentList '-c','gci -r'", PROJ),
                       ("Start-Process bash -ArgumentList '-c','grep -r x ..'", PROJ)), "deny", tool="PowerShell")
        self.conferir((("Start-Process -WorkingDirectory minutas -Wait powershell -ArgumentList '-c','gci -r'", PROJ),
                       ("Start-Process -Wait powershell -ArgumentList '-c','Get-Date'", RAIZ_W),
                       ("Write-Output a,b,'c d'", RAIZ_W)), "sem_decisao", tool="PowerShell")

    def test_uso_normal_segue(self):
        self.conferir((("grep -rn --color=auto x projects/juridico-lab", RAIZ_W),
                       ("grep -rn --color x projects/juridico-lab", RAIZ_W),
                       ("rg --color never x projects/juridico-lab", RAIZ_W),
                       ("rg --no-ignore-vcs --hidden x projects/juridico-lab", RAIZ_W),
                       ("grep -r --include '*.md' x projects/juridico-lab", RAIZ_W),
                       ("env -C minutas grep -r x .", PROJ), ("git diff HEAD~1 -- minutas", PROJ),
                       ("ls -R --color minutas", PROJ), ("du -a --time .", PROJ)), "sem_decisao")

    def test_command_v_so_consulta(self):
        self.conferir((("command -v rg", RAIZ_W), ("command -v rg >/dev/null && rg x projects/juridico-lab", RAIZ_W),
                       ("command -V find", RAIZ_W), ("command -pv rg", RAIZ_W)), "sem_decisao")
        self.conferir((("command rg x", RAIZ_W), ("command -p rg x", RAIZ_W)), "deny")


class NomesDoMesmoCaminho(_Casos):
    """HOOK-F3 / HOOK-F4 (baixa): `projects.\\`, a lista com vírgula do PowerShell e `~+/..`."""

    def test_formas_da_revisao_negam(self):
        self.conferir(((f"Get-Content projects.{B}reversa-lab{B}segredo.txt", RAIZ_W),
                       (f"cmd /c type projects.{B}reversa-lab{B}segredo.txt", RAIZ_W),
                       (f"Get-Content '{RAIZ_W}{B}projects.{B}reversa-lab{B}segredo.txt'", PROJ),
                       (f"Get-Content minutas{B}a.md,..{B}reversa-lab{B}segredo.txt", PROJ)), "deny", tool="PowerShell")
        self.conferir((("cat ~+/../reversa-lab/segredo.txt", PROJ), ("cat $PWD/../reversa-lab/segredo.txt", PROJ),
                       ("cat projects./reversa-lab/segredo.txt", RAIZ_W)), "deny")

    def test_uso_normal_segue(self):
        self.conferir(((f"Get-Content minutas{B}a.md,minutas{B}b.md", PROJ),), "sem_decisao", tool="PowerShell")
        self.conferir((("cat ~+/minutas/a.md", PROJ), ("cat $PWD/../juridico-lab/a.md", PROJ)), "sem_decisao")


class OrcamentoUnico(_Casos):
    """HOOK-F5 (baixa): o `eval` aninhado sobre chaves expandidas decide logo (orçamento da decisão inteira)."""

    def test_eval_aninhado_com_chaves_decide_logo(self):
        palavras = " ".join(f"{{a,b}}{{c,d}}{{e,f}}{{g,h}}{{i,j}}{{k,l}}*{k}/../y" for k in range(95))
        comando = "cd a; cd b; cd c; eval eval eval " + palavras
        self.assertGreater(len(comando), 3700)
        inicio = time.perf_counter()
        self.assertEqual(self.decide(comando, cwd=PROJ), "deny")
        self.assertLess(time.perf_counter() - inicio, 1)
        inicio = time.monotonic()
        self.assertEqual(decisao(HOOK, {**ferramenta("Bash", command=comando), "cwd": PROJ}, **self.env), "deny")
        self.assertLess(time.monotonic() - inicio, 5)  # o processo inteiro, longe do prazo do perfil (10 s)

    def test_formas_novas_perto_do_teto_decidem_logo(self):
        teto = 16 * 1024 - 64
        for tool, cwd, prefixo, miolo in (("Bash", PROJ, "cd a; cd b; cd c; grep -r x ", "a "),
                                          ("Bash", PROJ, "find a b c d -exec ls ", "{} "),
                                          ("Bash", PROJ, "", "bash <<< 'grep -r x minutas'; "),
                                          ("Bash", PROJ, "", "echo @(a) !(b) "),
                                          ("PowerShell", PROJ, "Get-ChildItem -Recurse ", "a,"),
                                          ("Bash", RAIZ_W, "echo ", "'[{\"a\":1,\"b\":2},{\"a\":3,\"b\":4}]/x' ")):
            comando = prefixo + miolo * ((teto - len(prefixo)) // len(miolo))
            with self.subTest(miolo=miolo):
                inicio = time.perf_counter()
                self.decide(comando, tool=tool, cwd=cwd)
                # < 3 s, como test_a_conta_e_linear: as formas usam metade do limite nesta máquina, mas a CI roda 5
                # rodadas em duas plataformas e a máquina carregada não pode dar falha intermitente (revisão 3 da
                # rodada 4, HOOK-F5); o processo inteiro fica longe do prazo do perfil (10 s).
                self.assertLess(time.perf_counter() - inicio, 3)


@unittest.skipUnless(os.name == "nt", "o Windows tira o ponto e o espaço do fim de cada nome do caminho")
class PontoNoFimDoNome(_BaseAviso):
    """HOOK-F2 (endurecimento): `<raiz>.\\state\\x` é `<raiz>\\state\\x` no Windows."""

    def test_vira_o_marcador(self):
        raiz = str(self.raiz)
        for destino in (raiz + "." + B + "state" + B + "semanal-x", raiz + "." + B + "semanal-x",
                        raiz + "." + B + "projects" + B + "juridico-lab" + B + "semanal-x",
                        raiz + " " + B + "state" + B + "semanal-x", str(self.copias) + "." + B + "semanal-x"):
            with self.subTest(destino=destino):
                self.registrar(criada_em=iso(30), destino=destino)
                texto = self.contexto(self.rodar())
                self.assertIn("<pasta das cópias", texto)
                self.assertNotIn(destino, texto)
        self.registrar(criada_em=iso(30))  # a pasta fora da raiz continua no comando
        self.assertIn(str(self.copias), self.contexto(self.rodar()))


if __name__ == "__main__":
    unittest.main()
