"""O LEIA-ME.txt gerado em cada cópia cifrada (1.7.11; desenho DESENHO-COPIA-CIFRADA-1.7.11, §4.4): o que a pasta é, como
conferir sem senha, como o titular confere e decifra com a ferramenta dele e, por último, o roteiro à mão com o gpg do Git para
o dia em que o kit faltar. Não tem segredo nem nome de arquivo da cópia; o SHA-256 dele vai no manifesto externo (alterá-lo
é percebido pela conferência sem senha), mas quem o lê deve conferir os comandos antes de rodá-los."""

from __future__ import annotations

TEXTO = r"""Copia de seguranca CIFRADA da Fundacao de IA (formato @FORMATO@).

Esta pasta so tem texto cifrado. Quem abre e o titular, com a chave privada e a senha dele; sem elas, ninguem abre,
nem o kit, nem o coordenador, nem a Anthropic. Perdida a senha, perdem-se as copias desta chave.

  manifesto-cifrado.json   destinatario, tamanho e SHA-256 de cada parte (sem nomes de arquivo)
  parte-001.gpg, ...       tar PAX cifrado com GnuPG (chave publica), uma parte por ~1 GiB, cada uma independente
  parte-final.gpg          o banco da fundacao e o manifesto interno
  LEIA-ME.txt              este texto

1) Conferir SEM senha (a ancora e o codigo que o `backup criar` devolveu, guardado fora da copia):
   python -m fundacao --raiz <raiz da fundacao> backup verificar --origem <esta pasta> --sha256-manifesto <codigo>

2) Conferir o CONTEUDO, com a senha (uma vez por mes), pela ferramenta do titular (a cartilha mostra o comando pronto):
   python -I -B -S <pasta das ferramentas>\<versao>\assets\host\fundacao_titular.py conferir-copia --origem <esta pasta>

3) Decifrar para restaurar (a pasta nova fica em claro; apague-a depois da restauracao):
   python -I -B -S <pasta das ferramentas>\<versao>\assets\host\fundacao_titular.py decifrar-copia --origem <esta pasta> --destino <pasta nova> --sha256-manifesto <codigo>
   (o codigo e o do papel, guardado fora do computador; o livro de copias da raiz nao basta, a sessao grava nele)
   depois: backup restaurar --origem <pasta decifrada> --destino <pasta nova> --retiradas <registro> --sha256-manifesto <o
   sha256_manifesto_interno que o decifrar-copia mostra>

4) Sem o kit (ultimo recurso; PowerShell, gpg do Git para Windows e o chaveiro da chave da copia). O gpg entrega o texto
   claro ANTES de conferir a integridade: so use o resultado de uma parte se o gpg sair com codigo 0 (por isso duas etapas).
   $gpg = 'C:\Program Files\Git\usr\bin\gpg.exe'; $casa = "$env:APPDATA\FundacaoIA\gnupg-copia"
   $origem = '<esta pasta>'; $destino = "$env:LOCALAPPDATA\FundacaoIA\decifrada"
   $m = Get-Content -Raw -Encoding UTF8 "$origem\manifesto-cifrado.json" | ConvertFrom-Json
   New-Item -ItemType Directory $destino | Out-Null
   foreach ($p in $m.partes) {
     $arq = Join-Path $origem $p.nome
     if ((Get-FileHash $arq -Algorithm SHA256).Hash.ToLower() -ne $p.sha256) { Remove-Item -Recurse -Force $destino; throw "parte alterada: $($p.nome)" }
     & $gpg --homedir $casa --output "$destino\parte.tar" --decrypt $arq
     if ($LASTEXITCODE -ne 0) { Remove-Item -Recurse -Force $destino; throw "nao decifrou: $($p.nome)" }
     tar.exe -xf "$destino\parte.tar" -C $destino; Remove-Item "$destino\parte.tar"
   }
   (O chaveiro precisa estar com a chave privada: gpg --homedir <chaveiro> --import chave-privada-protegida.asc, com a senha.)
"""


def texto(formato: str) -> str:
    return TEXTO.replace("@FORMATO@", formato)
