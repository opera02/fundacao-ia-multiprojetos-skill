"""Revisão de segurança da 1.7.10, rodada 4, grupo HOOKS, correções da revisão 3: cada caso que nega falha no código
de antes (03d8eaa, 55a8ac8 ou 4dfcdd7, a correção da revisão 2) e o uso normal continua.

- HOOK-F3, `{}` do find (média): o `{}` vira o TEXTO do ponto de partida como foi escrito (`.`, `..`, `minutas`), não
  o absoluto resolvido — o `{}` do find nunca é irmão do ponto de partida —, então `find . -exec mv {} {}.bak` na pasta
  do próprio projeto não cita mais `projects/<p>.bak`; o `-exec` sobre `..` e a raiz continua negando.
- HOOK-F3, `git diff` com `-C` (baixa): o `-C <pasta>` é alvo só no `git grep`; no `git diff` é só a base dos
  caminhos, então `git -C <raiz> diff --stat` e `git -C <raiz> diff HEAD~1 -- RETOMADA.md` seguem, e `git -C <raiz>
  diff /fora/vazio ..` continua negando.
- HOOK-F3/F5, here-doc de dados (baixa): o corpo de `<<EOF`/`<<-EOF` é dado (não palavra de comando), então o JSON
  minificado no corpo de `cat`/`python` segue (antes negava com "escreva os caminhos por extenso"); o corpo lido por um
  lançador (`bash <<EOF`) e a substituição de comando de um corpo sem aspas continuam negando.
- HOOK-F3, mensagem das pastas possíveis (baixa): o motivo é neutro (não atribui o excesso só a `cd X;`) e dá a saída
  de cada ferramenta; cinco `cd`/`Set-Location` relativos na raiz e o `-execdir` com muitos pontos de partida negam.

Raiz fictícia Q: (`/mnt/q`) nos comandos.
"""

from __future__ import annotations

import unittest

from test_hooks_1710 import ferramenta, motivo
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

    def motivo_de(self, comando, cwd, tool: str = "Bash") -> str:
        return motivo(HOOK, {**ferramenta(tool, command=comando), "cwd": cwd}, **self.env)


class ExecDoFindTextoDoPontoDePartida(_Casos):
    """HOOK-F3 (média): o `{}` do `-exec` é o texto do ponto de partida, não o irmão absoluto do projeto."""

    def test_uso_normal_no_proprio_projeto_segue(self):
        # Falham em 4dfcdd7 (o `{}` virava `<raiz>/projects/juridico-lab`, e `{}.bak` citava projects/juridico-lab.bak).
        self.conferir((("find . -name '*.txt' -exec mv {} {}.bak " + B + ";", PROJ),
                       ("find . -iname '*.jpg' -exec convert {} {}.png " + B + ";", PROJ),
                       ("find . -type d -exec mkdir -p {}_old " + B + ";", PROJ),
                       ("find . -name '*.md' -exec echo {}: " + B + ";", PROJ),
                       ("find . -name '*.txt' -execdir mv {} {}.bak " + B + ";", PROJ),
                       ("find minutas -exec cp {} {}.orig " + B + ";", PROJ)), "sem_decisao")

    def test_exec_sobre_pai_ou_raiz_continua_negando(self):
        self.conferir((("find .. -maxdepth 0 -exec grep -r x {} +", PROJ),
                       ("find .. -maxdepth 0 -exec cp -r {} /fora/copia " + B + ";", PROJ),
                       (f"find '{RAIZ_L}' -maxdepth 0 -exec grep -r x {{}} +", PROJ),
                       ("find ../.. -maxdepth 0 -execdir grep -r x . " + B + ";", PROJ),
                       ("bash -c 'find . -name x -exec mv {} {}.bak " + B + ";'", RAIZ_W)), "deny")


class GitDiffComC(_Casos):
    """HOOK-F3 (baixa): o `-C` do `git diff` é só a base dos caminhos, não um alvo."""

    def test_uso_normal_segue(self):
        # Falham em 4dfcdd7 (o `-C <raiz>` virava alvo de todo git diff).
        self.conferir(((f"git -C '{RAIZ_W}' diff --stat", RAIZ_W), ("git -C . diff --stat", RAIZ_W),
                       (f"git -C {RAIZ_L} diff HEAD~1 -- RETOMADA.md", PROJ),
                       ("git diff --stat", RAIZ_W), ("git -C .. diff --stat", PROJ)), "sem_decisao")
        self.conferir(((f"git -C '{RAIZ_W}' diff --stat", RAIZ_W),), "sem_decisao", tool="PowerShell")

    def test_diff_com_caminho_de_fora_continua_negando(self):
        self.conferir(((f"git -C {RAIZ_L} diff /fora/vazio ..", PROJ), ("git diff /fora/vazio ..", PROJ),
                       (f"git -C {RAIZ_L} diff -- ../reversa-lab", PROJ)), "deny")


class HereDocDeDados(_Casos):
    """HOOK-F3/F5 (baixa): o corpo do here-doc é dado, não palavra de comando."""

    JSON = ('[{"id":1,"nome":"a","ok":true},{"id":2,"nome":"b","ok":false},'
            '{"id":3,"nome":"c","ok":true},{"id":4,"nome":"d","ok":false}]')  # 3^4 = 81 combinações de chave

    def test_json_minificado_no_corpo_segue(self):
        # Falham em 55a8ac8 e 4dfcdd7 (o corpo era lido como palavras: `{...}` com mais de 64 combinações negava).
        py = "DADOS = [{'a':1,'b':2,'c':3},{'a':4,'b':5,'c':6},{'a':7,'b':8,'c':9},{'a':10,'b':11,'c':12}]"
        self.conferir((("cat > dados.json <<'EOF'\n" + self.JSON + "\nEOF", PROJ),
                       ("cat > dados.json <<EOF\n" + self.JSON + "\nEOF", PROJ),
                       ("python3 - <<'EOF'\n" + py + "\nEOF", PROJ),
                       ("cat <<'EOF'\n$(grep -r x ..)\nEOF", PROJ),
                       ("cat <<-EOF\n\t" + self.JSON + "\n\tEOF", PROJ)), "sem_decisao")

    def test_corpo_lido_por_lancador_ou_substituicao_nega(self):
        # bash/sh leem o corpo como comando (a aspa no delimitador só tira a expansão, não a execução); o corpo sem
        # aspas ainda roda o $(...).
        self.conferir((("bash <<EOF\ngrep -r x ..\nEOF", PROJ), ("bash <<'EOF'\ngrep -r x ..\nEOF", PROJ),
                       ("sh <<EOF\ncat ../reversa-lab/segredo.txt\nEOF", PROJ),
                       ("cat > out.txt <<EOF\n$(grep -r x ..)\nEOF", PROJ)), "deny")


class PastasPossiveisNeutras(_Casos):
    """HOOK-F3 (baixa): o motivo do excesso de pastas é neutro e dá a saída de cada ferramenta."""

    def test_cinco_cd_relativos_na_raiz_negam(self):
        self.conferir((("cd a; cd b; cd c; cd d; cd e; grep -r x .", RAIZ_W),
                       ("find src tests docs scripts lib bin etc conf -name '*.pyc' -execdir rm {} +", PROJ)), "deny")
        self.conferir((("Set-Location docs; Set-Location ..; Set-Location scripts; Set-Location ..; "
                        "Set-Location tests; Get-ChildItem", RAIZ_W),), "deny", tool="PowerShell")

    def test_cadeia_curta_segue(self):
        # A cadeia de poucos cd/Set-Location com `;` fica dentro do limite (o PowerShell 5.1 não tem `&&`).
        self.conferir((("cd minutas; cd modelos; ls", PROJ), ("cd minutas; grep -r x .", PROJ)), "sem_decisao")
        self.conferir((("Set-Location minutas; Set-Location modelos; Get-ChildItem", PROJ),
                       ("Set-Location docs; Set-Location scripts; Get-ChildItem", RAIZ_W)), "sem_decisao",
                      tool="PowerShell")

    def test_mensagem_nomeia_as_tres_causas_e_os_dois_shells(self):
        texto = self.motivo_de("find src tests docs scripts lib bin etc conf -name '*.pyc' -execdir rm {} +", PROJ)
        self.assertIn("pastas possíveis demais", texto)
        self.assertIn("-execdir", texto)  # não atribui o excesso só a `cd X;`
        self.assertIn("PowerShell", texto)
        self.assertIn("-LiteralPath", texto)


if __name__ == "__main__":
    unittest.main()
