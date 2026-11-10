<#
.SYNOPSIS
Prepara o Windows para uma fundação com dados reais: chave do titular, âncora das decisões assinadas, hooks e
perfis do Claude Code em <raiz>\.claude. Rode no PowerShell comum (não como administrador): o script pede a
confirmação do administrador (UAC) só para a âncora e, no mesmo UAC, para a cópia protegida da ferramenta do titular.
Exige -Backups (a pasta das cópias de segurança; com o disco delas desligado, -BackupsAusente) ou, enquanto não há
cópias, -SemBackups: sem nenhum dos dois, recusa com o comando pronto (item 4).

.DESCRIPTION
O que faz, nesta ordem, conferindo antes o que já existe (rodar de novo não repete nada):
 1. Chave do titular (-Chave, padrão ~\.ssh\fundacao_titular): se faltar, roda o ssh-keygen do sistema; a senha
    é digitada por você no seu terminal e o script não a vê. Recusa chave que abre sem senha.
 0. Plano antes de tudo (1.7.10): as pastas de -SomenteLeitura e -Backups (separadas só na vírgula seguida de
    unidade, ",D:", e conferidas: existentes, num disco local, fora da raiz e sem conter a raiz; a raiz de um disco,
    "F:\", vale como está; o preparar-projeto.ps1 confere as de -Backups com esta mesma função e as repassa, ou repassa
    -SemBackups), o projeto das sessões do Windows e todas as saídas do ajudante são calculados ANTES da chave, do UAC e
    de qualquer gravação. Sem -Backups e sem um -SemBackups explícito, o plano para aí (código 2, com o comando pronto:
    item 4). Trocar o projeto já gravado exige -TrocarProjeto; sem ele, conflito e nada gravado.
    -SomenteLeituraAusente (o preparar-projeto.ps1 passa) leva as pastas do registry\projetos-host.json que não existem
    agora (disco não montado), e -BackupsAusente, as cópias num disco desligado agora: a forma é conferida, a
    existência não, e elas seguem negadas como as outras (as cópias, na leitura e na edição): quando o disco voltar, já
    estão protegidas.
 2. Âncora (-Ancora, padrão C:\ProgramData\FundacaoIA\confianca\allowed_signers), que só um administrador altera:
    pastas com dono Administradores e herança cortada (Administradores e Sistema: controle total; Usuários: leitura),
    arquivo herdando da pasta (nada de "(OI)(CI)" em arquivo) com dono Administradores e a linha do titular nos
    namespaces fundacao-decisao, fundacao-abertura e fundacao-copia (1.7.10: a ficha de aberturas é assinada no
    segundo; o livro de cópias assinado, core/livro_assinado.py, no terceiro, contra esta mesma âncora: folha da
    integração, I22). A linha da mesma chave sem um deles (a da 1.7.9, só com o primeiro, ou a da 1.7.10 sem
    fundacao-copia) é trocada pela nova, com a mesma chave, no mesmo UAC; a que já tem os três fica. Esta é a única
    etapa com UAC (a cópia do 2b vai no mesmo UAC). Depois, a sondagem desta conta confere que ela não altera a
    âncora (dono, direitos de escrita e de troca de permissões, herança) e que a linha é a da chave.
 2b. Cópia protegida da ferramenta do titular (1.7.10, folha da integração I11) em -Ferramentas (padrão
    C:\ProgramData\FundacaoIA\ferramentas)\<versão do kit>: assets\host\fundacao_titular.py e o pacote do kit, com o
    hashes.json (fundacao.ferramenta_titular/1) que o ajudante calcula e o Python fixado, no mesmo UAC da âncora e com a
    mesma ACL de administrador; depois, a sondagem desta conta confere que ela não altera a cópia. Só um Python instalado
    para todos os usuários é registrado: com o Python por usuário (em AppData), a forma do Windows de assinar a ficha
    fica pendente, com o motivo, e vale a do Ubuntu (wsl.exe -e /usr/bin/python3, cópia do preparar-wsl.sh).
 2c. Chave pública da cópia de segurança CIFRADA (1.7.11, -ChaveDaCopia <arquivo .asc>, o que o `preparar-chave-copia` da
    ferramenta do titular gravou) em -AncoraChaveCopia (padrão C:\ProgramData\FundacaoIA\confianca\chave-da-copia.asc), na
    mesma pasta e com a mesma ACL de administrador da âncora (pastas com dono Administradores e herança cortada, arquivo
    herdando da pasta): a PRESENÇA dela, protegida, é o que liga a cifra do `backup criar` do kit. O arquivo é conferido
    ANTES do UAC (uma chave pública OpenPGP, até 1 MiB, sem material privado, sem ligação) e o administrador reconfere o
    mesmo SHA-256. Chave já instalada e diferente: conflito, e só -TrocarChaveDaCopia a troca (a anterior fica numa cópia
    ao lado). Pede o UAC próprio quando é a única etapa que precisa dele; depois, a sondagem desta conta confere que ela
    não altera a chave. Sem -ChaveDaCopia, nada muda.
 3. Hooks da skill em <raiz>\.claude\hooks: guarda_caminho.py, guarda_identidade.py, sinais_sessao.py,
    guarda_ferramentas.py, guarda_rede.py, guarda_leitura.py, aviso_copia.py e regras_codigo.py (os do Ubuntu também
    saem daqui). O regras_codigo.py só é registrado no perfil do Ubuntu (o lançador liga o campo regras_codigo do
    projeto); no Windows ele é apenas copiado.
    O sinais_sessao lembra a conferência da RETOMADA após compactação e mostra somente o projeto na linha de status;
    não lê conteúdo, identidade ou caso. Esta cópia da skill só está preparada; executar o preparo ativa.
 4. <raiz>\.claude\settings.json (sessões do Windows), gerado pelo modelo da skill: o projeto das sessões no env
    (-Projeto; 1.7.10), Read negado de cada outro projeto, de projects\*\data e das cópias (-Backups), WebFetch e
    WebSearch negados, Edit negado nas pastas só de leitura, nas cópias e, lidas pelo ajudante, nas origens e nas
    pastas só de leitura de TODOS os projetos de registry\projetos-host.json (I21: este script rodado sozinho, sem
    -SomenteLeitura, não deixa uma origem registrada gravável; caminho só do Ubuntu fica de fora), hooks com -I -B (no
    Windows não há sandbox: são guarda-corpos). O perfil é refeito inteiro a cada preparo, só com o que recebe: por
    isso, sem -Backups e sem um -SemBackups explícito, recusa com código 2 antes de gravar qualquer coisa, também na
    simulação, com o motivo e o comando pronto com -Backups; os dois juntos também são recusados (folha da integração,
    I21; revisão da terceira rodada, defeitos 1 e 2: rodado sozinho sem -Backups, ele tirava em silêncio o Read e o
    Edit negados das cópias, que têm os dados de todos os projetos; -Backups só com espaços não é cópia). Com
    -SemBackups (ainda não há cópias), o perfil sai sem essa negação, com a pendência no relatório. Com uma cópia
    registrada em registry\ultima-copia.json (o backup criar do kit grava; o ajudante o lê como o hook aviso_copia.py,
    sem seguir ligação e até 64 KiB), o -SemBackups é recusado (código 2), e o comando pronto traz a pasta de cima da
    última cópia no lugar do texto entre < > (com -BackupsAusente, se ela não existe agora). O registro só recusa e
    sugere, nunca aceita: uma sessão o forja (revisão seguinte da terceira rodada, defeito 2). Pasta de -SomenteLeitura
    ou nome de -NegarSkill ou -NegarAgente fora do registry\projetos-host.json vira pendência no relatório e na tela: o próximo
    preparar-projeto.ps1 refaz o perfil só com o registro, e eles sumiriam (registre-os com preparo_host.py
    registrar-projeto ou rode este script por último; defeito 3).
    <raiz>\.claude\settings.local.json fica só com a identidade (o projeto sai dele). O perfil
    único do Ubuntu da 1.7.9 (.claude\settings.wsl.json) é aposentado em .claude\anteriores: na 1.7.10 cada projeto
    tem o seu, na área do titular no Ubuntu (preparar-wsl.sh). -NegarSkill nome1,nome2 nega por nome skills aninhadas
    em pastas de dados (scripts/instrucoes_aninhadas.py lista quais), somadas às de registry\projetos-host.json.
    -NegarAgente nome1,nome2 faz o mesmo com agentes aninhados (Agent(<nome>) no perfil; 1.7.11, lote A3).
O Python que roda o ajudante e os hooks do Windows é o de -Python ou, sem ele, o das instalações registradas do
Windows e do PATH, nunca o do perfil existente; antes de rodar, o script confere que é o python.exe do instalador
oficial (Authenticode Valid, sujeito e emissor completos e pin do certificado comprovado para a release em
pins-python.json), sem ligação no caminho e sem escrita para outras contas comuns. Certificado/release novos exigem
novo pin datado de artefato oficial: não há fallback só pelo nome. Timestamp válido não é recusado pelo NotAfter.
Arquivo trocado vai antes para <raiz>\.claude\anteriores\<data>. Imprime a impressão digital da chave e os SHA-256
e grava um relatório JSON (-Relatorio; no modo real, padrão em <raiz>\evidence\host).

Códigos: 0 pronto e conferido · 1 parou ou há conflito (veja o relatório) · 2 uso incorreto (nada alterado; também
sem -Backups nem -SemBackups, ou com -SemBackups e uma cópia registrada, com o comando pronto; e rodado de dentro de
<raiz>\projects\: no modo real, de projects\ de qualquer fundação, e na simulação, contra a fundação que o contém) · 3
tudo feito menos a âncora ou a cópia protegida, que esperam o administrador (UAC recusado ou -SemUAC). A elevação relança
este script pelo powershell.exe da pasta do sistema, com -NoProfile e -ExecutionPolicy Bypass, e os cmdlets que decidem
(Start-Process, Get-Acl, Get-AuthenticodeSignature, Get-Item, Get-ChildItem, Get-Command, ConvertFrom-Json, Add-Type,
Resolve-Path) vão pelo nome qualificado: uma função ou um alias do perfil do PowerShell não os pega (revisão de
segurança da 1.7.10, CI-F1 e CI-F3).

.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-maquina.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Backups "E:\Backups-IA" -Simular
.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-maquina.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Projeto juridico-lab -Backups "E:\Backups-IA"
.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-maquina.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Projeto juridico-lab -SemBackups
.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-maquina.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Projeto juridico-lab -BackupsAusente "F:\Backups-IA"
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $Raiz,
    [string] $Titular,
    [string] $Projeto,
    [string[]] $Backups = @(),
    # As cópias num disco desligado agora (revisão seguinte da terceira rodada da integração, defeito 2): a forma é
    # conferida, a existência não, e elas saem com o Read e o Edit negados como as de -Backups.
    [string[]] $BackupsAusente = @(),
    # Sem cópias de segurança ainda: o perfil sai sem a negação delas, de propósito (sem -Backups e sem esta opção, o
    # plano recusa; revisão da terceira rodada da integração, defeito 1).
    [switch] $SemBackups,
    [string[]] $SomenteLeitura = @(),
    [string[]] $SomenteLeituraAusente = @(),
    [string[]] $NegarSkill = @(),
    [string[]] $NegarAgente = @(),
    [string] $Chave = (Join-Path $HOME '.ssh\fundacao_titular'),
    [string] $Ancora = (Join-Path $env:ProgramData 'FundacaoIA\confianca\allowed_signers'),
    # A cópia protegida da ferramenta do titular (core/aberturas_comando.FERRAMENTA_WINDOWS do kit; folha da
    # integração, I11). Outro valor só para ensaio, como -Ancora.
    [string] $Ferramentas = (Join-Path $env:ProgramData 'FundacaoIA\ferramentas'),
    [string] $Python,
    [switch] $Simular,
    [switch] $SemUAC,
    [switch] $TrocarChave,
    [switch] $TrocarProjeto,
    [string] $Relatorio,
    # Uso interno: a etapa da âncora, que o próprio script roda como administrador depois do UAC.
    [switch] $EtapaAncora,
    [string] $ChavePublica,
    [string] $ImpressaoEsperada,
    [string] $RegistroEtapa,
    # Uso interno: a etapa da cópia protegida da ferramenta do titular, no mesmo UAC (I11): o hashes.json planejado
    # (arquivo) e o SHA-256 dele conferido antes do UAC.
    [switch] $EtapaFerramenta,
    [string] $PlanoFerramenta,
    [string] $FerramentaEsperada,
    # A chave pública da cópia cifrada (1.7.11): o arquivo .asc a instalar na pasta da âncora, onde ela vai (outro valor só
    # para ensaio, como -Ancora), a troca de uma chave já instalada e, de uso interno, a etapa do administrador e o
    # SHA-256 conferido antes do UAC.
    [string] $ChaveDaCopia,
    [string] $AncoraChaveCopia = (Join-Path $env:ProgramData 'FundacaoIA\confianca\chave-da-copia.asc'),
    [switch] $TrocarChaveDaCopia,
    [switch] $EtapaChaveCopia,
    [string] $ChaveDaCopiaEsperada
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$PARAMETROS_DADOS = $PSBoundParameters  # para o comando pronto da recusa sem -Backups nem -SemBackups (defeito 1)
# Aberto a partir de um PowerShell 7 (pwsh: terminal do Windows, GitHub Actions), o Windows PowerShell herda os
# caminhos de módulo do 7 e não carrega Microsoft.PowerShell.Security (Get-Acl, Set-Acl): ficam só os caminhos
# que não são do PowerShell 7 (CI pública da 1.7.1).
if ($PSVersionTable.PSEdition -eq 'Desktop' -and $env:PSModulePath) {
    $env:PSModulePath = (@($env:PSModulePath -split ';') | Where-Object { $_ -and $_ -notmatch '\\PowerShell\\' }) -join ';'
}

$NAMESPACE = 'fundacao-decisao'
# 1.7.10: a ficha de aberturas é assinada em fundacao-abertura; o livro de cópias assinado (core/livro_assinado.py) é
# conferido em fundacao-copia contra esta mesma âncora (folha da integração, I22: sem ele, a adoção do livro não confere).
$NAMESPACES = 'fundacao-decisao,fundacao-abertura,fundacao-copia'
# A elevação relança este script com o powershell.exe da pasta do sistema (revisão de segurança da 1.7.10, CI-F3).
$POWERSHELL_DO_SISTEMA = 'WindowsPowerShell\v1.0\powershell.exe'
$SID_ADMINS = 'S-1-5-32-544'
$SID_SISTEMA = 'S-1-5-18'
$SID_USUARIOS = 'S-1-5-32-545'
$SKILL = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$AJUDANTE = Join-Path $SKILL 'assets\host\preparo_host.py'
$HOOKS = @('guarda_caminho.py', 'guarda_identidade.py', 'sinais_sessao.py', 'guarda_ferramentas.py', 'guarda_rede.py',
           'guarda_leitura.py', 'aviso_copia.py', 'regras_codigo.py')
$IDENTIFICADOR = '^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$'
# Projeto: a forma do kit e do porteiro ([a-z0-9-], 1 a 40, sem '--'), a mesma do preparo_host.py.
$ID_PROJETO = '^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$'
$BARRA = [char]92
$DIREITOS_ARQUIVO = [ordered]@{ WRITE_DAC = 0x40000; WRITE_OWNER = 0x80000; DELETE = 0x10000; GENERIC_WRITE = 0x40000000 }
$DIREITOS_PASTA = [ordered]@{ WRITE_DAC = 0x40000; WRITE_OWNER = 0x80000; DELETE = 0x10000; ADD_FILE = 0x2
    ADD_SUBDIRECTORY = 0x4; DELETE_CHILD = 0x40 }
# Nas pastas acima da cópia protegida (fundacao_titular._ACIMA): o que troca ou apaga a pasta de baixo.
$DIREITOS_ACIMA = [ordered]@{ WRITE_DAC = 0x40000; WRITE_OWNER = 0x80000; DELETE = 0x10000; DELETE_CHILD = 0x40 }
$ESQUEMA_FERRAMENTA = 'fundacao.ferramenta_titular/1'  # o hashes.json da cópia (core/aberturas_comando.ESQUEMA_HASHES)
$REL_FERRAMENTA = 'assets/host/fundacao_titular.py'
$REL_KIT_DA_FERRAMENTA = 'assets/fundacao-kit/fundacao/'
# Direitos que permitem alterar: gravar, acrescentar, atributos, apagar, apagar filhos, trocar permissões ou dono e
# os genéricos de escrita e de controle total.
$MASCARA_ESCRITA = [int64](0x2 -bor 0x4 -bor 0x10 -bor 0x100 -bor 0x40 -bor 0x10000 -bor 0x40000 -bor 0x80000) -bor
    [int64]0x10000000 -bor [int64]0x40000000
# Na pasta acima da instalação do Python, o que troca a pasta dela: apagar filhos, trocar permissões ou dono, tudo.
$MASCARA_TROCA = [int64](0x40 -bor 0x40000 -bor 0x80000) -bor [int64]0x10000000
$SID_INSTALADOR = 'S-1-5-80-956008885-3418522649-1831038044-1853292631-2271478464'  # TrustedInstaller
# Escrita para um destes é escrita para qualquer outra conta comum: Todos, Usuários autenticados, Usuários, Interativo,
# Convidados, Anônimo, Local, Logon no console, Rede, Esta organização, Conta local e pacotes de aplicativos.
$SIDS_AMPLOS = @('S-1-1-0', 'S-1-5-11', 'S-1-5-32-545', 'S-1-5-4', 'S-1-5-32-546', 'S-1-5-7', 'S-1-2-0', 'S-1-2-1',
                 'S-1-5-2', 'S-1-5-15', 'S-1-5-113', 'S-1-15-2-1', 'S-1-15-2-2')
$ASSINANTE_PYTHON = 'Python Software Foundation'

# ------------------------------------------------------------------ programas externos
function ConvertTo-ArgumentoNativo([string] $Texto) {
    # Regras da linha de comando do Windows: aspas em volta de vazio, espaço ou aspas; barras invertidas dobradas
    # antes de aspas e no fim. (O PowerShell 5.1 descarta argumento vazio, como o -P "" do ssh-keygen.)
    if ($Texto.Length -gt 0 -and $Texto -notmatch '[\s"]') { return $Texto }
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append('"')
    $n = 0
    foreach ($c in $Texto.ToCharArray()) {
        if ($c -eq $BARRA) { $n++; continue }
        if ($c -eq [char]'"') { [void]$sb.Append($BARRA, 2 * $n + 1); [void]$sb.Append('"'); $n = 0; continue }
        if ($n -gt 0) { [void]$sb.Append($BARRA, $n); $n = 0 }
        [void]$sb.Append($c)
    }
    [void]$sb.Append($BARRA, 2 * $n)
    [void]$sb.Append('"')
    $sb.ToString()
}

function Invoke-Nativo {
    param([Parameter(Mandatory = $true)] [string] $Exe, [string[]] $Argumentos = @())
    $psi = New-Object System.Diagnostics.ProcessStartInfo
    $psi.FileName = $Exe
    $psi.Arguments = (@($Argumentos) | ForEach-Object { ConvertTo-ArgumentoNativo $_ }) -join ' '
    $psi.UseShellExecute = $false
    $psi.CreateNoWindow = $true
    $psi.RedirectStandardOutput = $true
    $psi.RedirectStandardError = $true
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    $psi.StandardOutputEncoding = $utf8
    $psi.StandardErrorEncoding = $utf8
    $p = [System.Diagnostics.Process]::Start($psi)
    $saida = $p.StandardOutput.ReadToEndAsync()
    $erro = $p.StandardError.ReadToEndAsync()
    $p.WaitForExit()
    [pscustomobject]@{ Codigo = $p.ExitCode; Saida = $saida.Result; Erro = $erro.Result }
}

function Get-ProgramaDoSistema([string] $Relativo) {
    # Revisão de segurança da 1.7.10, CI-F3: os programas do Windows (ssh-keygen, icacls, o powershell.exe da elevação)
    # pela pasta do sistema que a API dá ([Environment]::SystemDirectory), nunca pelo $env:SystemRoot, que um perfil
    # do PowerShell troca.
    [IO.Path]::Combine([Environment]::SystemDirectory, $Relativo)
}

function Get-FundacaoQueContem([string] $Pasta) {
    # Revisão de segurança da 1.7.10, CI-F1: a raiz de fundação que contém a pasta (o pai de uma pasta projects, sem
    # caixa, que tem registry\), ou $null. Um script dali é de uma pasta que as sessões dos projetos gravam.
    $p = [IO.Path]::GetFullPath($Pasta).TrimEnd($BARRA)
    while ($p) {
        $pai = [IO.Path]::GetDirectoryName($p)
        if (-not $pai) { break }
        if ([IO.Path]::GetFileName($p) -ieq 'projects' -and [IO.Directory]::Exists([IO.Path]::Combine($pai, 'registry'))) {
            return $pai.TrimEnd($BARRA)
        }
        $p = $pai
    }
    $null
}

function Test-MesmaPasta([string] $Pasta, [string] $Outra) {
    # As duas resolvem para a mesma pasta (sem caixa; a outra pelo caminho do PowerShell). Inexistente: $false.
    if (-not $Pasta -or -not $Outra) { return $false }
    try { $cheia = (Microsoft.PowerShell.Management\Resolve-Path -LiteralPath $Outra -ErrorAction Stop).ProviderPath } catch { return $false }
    [IO.Path]::GetFullPath($Pasta).TrimEnd($BARRA) -ieq [IO.Path]::GetFullPath($cheia).TrimEnd($BARRA)
}

function Get-RecusaDeProjects([string] $Fundacao, [string] $Script) {
    # A mensagem da recusa do CI-F1, com o programa da skill instalada.
    $instalada = [IO.Path]::Combine([Environment]::GetFolderPath('UserProfile'), '.claude\skills\fundacao-ia-multiprojetos\assets\host\windows', $Script)
    "este $Script fica dentro de $Fundacao\projects\, pasta que as sessões dos projetos gravam: ele não roda daqui (nada foi alterado). Rode o da skill instalada, com o comando do modelo da skill (nunca o de uma cópia que a sessão mostrou ou guardou num projeto): $instalada"
}

function Get-Sha256Bytes([byte[]] $Bytes) {
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { -join ($sha.ComputeHash($Bytes) | ForEach-Object { $_.ToString('x2') }) } finally { $sha.Dispose() }
}

function Get-Sha256Arquivo([string] $Caminho) {
    if (-not (Test-Path -LiteralPath $Caminho -PathType Leaf)) { return $null }
    Get-Sha256Bytes ([IO.File]::ReadAllBytes($Caminho))
}

# ------------------------------------------------------------------ chave e linha da âncora
function Get-ImpressaoDigital([string] $LinhaPublica) {
    # SHA256:<base64 sem '='> do blob da chave, igual ao ssh-keygen -l.
    $partes = @($LinhaPublica.Trim() -split '\s+')
    if ($partes.Count -lt 2) { return $null }
    try { $blob = [Convert]::FromBase64String($partes[1]) } catch { return $null }
    $sha = [System.Security.Cryptography.SHA256]::Create()
    try { 'SHA256:' + [Convert]::ToBase64String($sha.ComputeHash($blob)).TrimEnd('=') } finally { $sha.Dispose() }
}

function Get-LinhaAncora([string] $Titular, [string] $LinhaPublica) {
    $Titular + ' namespaces="' + $NAMESPACES + '" ' + ((@($LinhaPublica.Trim() -split '\s+')) -join ' ')
}

function Test-NamespacesCobrem($Existentes, $Pedidos) {
    # Linha sem namespaces= vale para todos; com eles, tem de conter cada namespace pedido.
    if ($null -eq $Existentes) { return $true }
    $tem = @(([string]$Existentes) -split ',' | ForEach-Object { $_.Trim() })
    foreach ($n in @(([string]$Pedidos) -split ',' | ForEach-Object { $_.Trim() } | Where-Object { $_ })) {
        if ($tem -notcontains $n) { return $false }
    }
    $true
}

function Get-PartesAncora([string] $Linha) {
    $t = $Linha.Trim()
    if (-not $t -or $t.StartsWith('#')) { return $null }
    $k = [regex]::Match($t, '(ssh-ed25519|ssh-rsa|ecdsa-sha2-nistp[0-9]+|sk-ssh-ed25519@openssh\.com|sk-ecdsa-sha2-nistp256@openssh\.com)\s+([A-Za-z0-9+/=]+)')
    $ns = [regex]::Match($t, 'namespaces="([^"]*)"')
    $chave = $null
    if ($k.Success) { $chave = $k.Groups[1].Value + ' ' + $k.Groups[2].Value }
    $nsValor = $null
    if ($ns.Success) { $nsValor = $ns.Groups[1].Value }
    [pscustomobject]@{ Principais = @((@($t -split '\s+'))[0] -split ','); Chave = $chave; Namespaces = $nsValor }
}

function Merge-Ancora {
    # Junta a linha do titular à âncora sem perder as outras linhas e sem trocar chave em silêncio: a mesma chave com os
    # namespaces pedidos (comentário à parte) = igual; a mesma chave sem um deles = 'namespaces' (a linha é trocada
    # pela nova, que acrescenta o que falta: fundacao-abertura, da ficha de aberturas, e fundacao-copia, do livro de
    # cópias assinado; 1.7.10, I22; exige o UAC como as outras); outra chave do titular = conflito, salvo -Trocar.
    param([string[]] $Linhas = @(), [Parameter(Mandatory = $true)] [string] $Titular,
          [Parameter(Mandatory = $true)] [string] $LinhaNova, [switch] $Trocar)
    $nova = Get-PartesAncora $LinhaNova
    $igual = $false
    $diferente = $false
    $faltaNamespace = $false
    foreach ($linha in @($Linhas)) {
        $p = Get-PartesAncora $linha
        if ($null -ne $p -and $p.Principais -contains $Titular) {
            if ($p.Chave -ne $nova.Chave) { $diferente = $true }
            elseif (Test-NamespacesCobrem $p.Namespaces $nova.Namespaces) { $igual = $true }
            else { $faltaNamespace = $true }
        }
    }
    if ($diferente -and -not $Trocar) { return [pscustomobject]@{ Acao = 'conflito'; Linhas = @($Linhas) } }
    if (-not $diferente -and -not $faltaNamespace -and $igual) { return [pscustomobject]@{ Acao = 'igual'; Linhas = @($Linhas) } }
    if (-not $diferente -and -not $faltaNamespace) { return [pscustomobject]@{ Acao = 'acrescentar'; Linhas = @(@($Linhas) + $LinhaNova) } }
    $acao = 'namespaces'
    if ($diferente) { $acao = 'trocar' }
    $saida = New-Object System.Collections.Generic.List[string]
    $posta = $false
    foreach ($linha in @($Linhas)) {
        $p = Get-PartesAncora $linha
        if ($null -ne $p -and $p.Principais -contains $Titular) {
            if (-not $posta) { $saida.Add($LinhaNova); $posta = $true }
            continue
        }
        $saida.Add($linha)
    }
    [pscustomobject]@{ Acao = $acao; Linhas = $saida.ToArray() }
}

# ------------------------------------------------------------------ sondagem e permissões da âncora
if (-not ('FundacaoAcesso' -as [type])) {
    Microsoft.PowerShell.Utility\Add-Type -TypeDefinition @'
using System;
using System.Runtime.InteropServices;
public static class FundacaoAcesso {
    [DllImport("kernel32.dll", SetLastError = true, CharSet = CharSet.Unicode)]
    private static extern IntPtr CreateFileW(string nome, uint acesso, uint compartilhamento, IntPtr seguranca,
                                             uint disposicao, uint atributos, IntPtr modelo);
    [DllImport("kernel32.dll", SetLastError = true)]
    private static extern bool CloseHandle(IntPtr h);
    // Pede o direito ao abrir (OPEN_EXISTING, BACKUP_SEMANTICS para pasta) e fecha na hora: não cria, não trunca
    // e não grava nada.
    public static bool Pode(string caminho, uint acesso) {
        IntPtr h = CreateFileW(caminho, acesso, 7, IntPtr.Zero, 3, 0x02000000, IntPtr.Zero);
        if (h == new IntPtr(-1)) { return false; }
        CloseHandle(h);
        return true;
    }
}
'@
}

function Get-Direitos([string] $Caminho, $Tabela) {
    $out = [ordered]@{}
    foreach ($k in @($Tabela.Keys)) { $out[$k] = [FundacaoAcesso]::Pode($Caminho, [uint32]$Tabela[$k]) }
    $out
}

function Get-InfoAcl([string] $Caminho) {
    # CI-F3 (revisão de segurança da 1.7.10): cmdlet pelo nome qualificado, que uma função ou alias do perfil não pega.
    $acl = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $Caminho
    $extras = New-Object System.Collections.Generic.List[string]
    foreach ($r in @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))) {
        $sid = $r.IdentityReference.Value
        if ($r.AccessControlType -eq 'Allow' -and @($SID_ADMINS, $SID_SISTEMA) -notcontains $sid -and
            (([int64]$r.FileSystemRights -band $MASCARA_ESCRITA) -ne 0) -and -not $extras.Contains($sid)) {
            $extras.Add($sid)
        }
    }
    [pscustomobject]@{ Dono = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
                       HerancaCortada = $acl.AreAccessRulesProtected; Extras = $extras.ToArray() }
}

function Get-SondagemAncora([string] $Ancora) {
    # Vista DESTA conta (rode sem elevação): ela não pode alterar a âncora, a pasta dela nem a pasta acima. O dono
    # troca as permissões sem UAC (em 2026-10-20 o arquivo nasceu com o usuário como dono e a sondagem antiga, só de
    # escrita, disse "protegida"); por isso o dono tem de ser o grupo Administradores.
    $pasta = Split-Path -Parent $Ancora
    $base = Split-Path -Parent $pasta
    $acima = Split-Path -Parent $base
    $motivos = New-Object System.Collections.Generic.List[string]
    $s = [ordered]@{ ancora = $Ancora; existe = (Test-Path -LiteralPath $Ancora -PathType Leaf) }
    foreach ($par in @(@('arquivo', $Ancora, $DIREITOS_ARQUIVO, 'Leaf'), @('pasta', $pasta, $DIREITOS_PASTA, 'Container'),
                       @('base', $base, $DIREITOS_PASTA, 'Container'))) {
        $nome, $caminho, $tabela, $tipo = $par
        if (-not (Test-Path -LiteralPath $caminho -PathType $tipo)) {
            $s[$nome] = [ordered]@{ caminho = $caminho; existe = $false }
            $motivos.Add("$nome ausente: $caminho")
            continue
        }
        $info = Get-InfoAcl $caminho
        $direitos = Get-Direitos $caminho $tabela
        $s[$nome] = [ordered]@{ caminho = $caminho; existe = $true; dono_sid = $info.Dono
            dono_administradores = ($info.Dono -eq $SID_ADMINS); heranca_cortada = $info.HerancaCortada
            direitos = $direitos; regras_extras = $info.Extras }
        if ($info.Dono -ne $SID_ADMINS) {
            $motivos.Add("o dono de $caminho não é o grupo Administradores ($($info.Dono)): o dono troca as permissões sem UAC")
        }
        $concedidos = @($direitos.Keys | Where-Object { $direitos[$_] })
        if ($concedidos.Count -gt 0) { $motivos.Add("esta conta tem $($concedidos -join ', ') em $caminho") }
        if ($nome -ne 'arquivo' -and -not $info.HerancaCortada) { $motivos.Add("herança não cortada em $caminho") }
        if ($info.Extras.Count -gt 0) { $motivos.Add("regras de escrita para outras contas em ${caminho}: $($info.Extras -join ', ')") }
    }
    if ($acima -and (Test-Path -LiteralPath $acima -PathType Container)) {
        $d = Get-Direitos $acima ([ordered]@{ DELETE_CHILD = 0x40 })
        $s['acima'] = [ordered]@{ caminho = $acima; direitos = $d }
        if ($d['DELETE_CHILD']) { $motivos.Add("esta conta pode apagar ou renomear $base pela pasta acima ($acima)") }
    }
    $s['protegida'] = ($s['existe'] -and $motivos.Count -eq 0)
    $s['motivos'] = $motivos.ToArray()
    [pscustomobject]$s
}

function Set-AclProtegida {
    # Pasta com herança cortada e só três regras, que valem para ela e para o que estiver dentro: Administradores e
    # Sistema com controle total, Usuários com leitura. Dono: Administradores (-SemDono só nos testes sem UAC).
    param([Parameter(Mandatory = $true)] [string] $Pasta, [switch] $SemDono)
    $sd = New-Object System.Security.AccessControl.DirectorySecurity
    $sd.SetAccessRuleProtection($true, $false)
    $heranca = [System.Security.AccessControl.InheritanceFlags]'ContainerInherit, ObjectInherit'
    foreach ($par in @(@($SID_ADMINS, 'FullControl'), @($SID_SISTEMA, 'FullControl'), @($SID_USUARIOS, 'ReadAndExecute'))) {
        $sid = New-Object System.Security.Principal.SecurityIdentifier($par[0])
        $regra = New-Object System.Security.AccessControl.FileSystemAccessRule($sid,
            [System.Security.AccessControl.FileSystemRights]$par[1], $heranca,
            [System.Security.AccessControl.PropagationFlags]::None, [System.Security.AccessControl.AccessControlType]::Allow)
        $sd.AddAccessRule($regra)
    }
    if (-not $SemDono) { $sd.SetOwner((New-Object System.Security.Principal.SecurityIdentifier($SID_ADMINS))) }
    (Microsoft.PowerShell.Management\Get-Item -LiteralPath $Pasta -Force).SetAccessControl($sd)
}

function Set-AclArquivoHerdada {
    # Arquivo sem regra própria, herdando da pasta (em 2026-10-20, "(OI)(CI)" aplicado ao arquivo o deixou ilegível
    # para todos). Dono: Administradores.
    param([Parameter(Mandatory = $true)] [string] $Arquivo, [switch] $SemDono)
    $icacls = Get-ProgramaDoSistema 'icacls.exe'
    $r = Invoke-Nativo -Exe $icacls -Argumentos @($Arquivo, '/reset', '/Q')
    if ($r.Codigo -ne 0) { throw "icacls /reset falhou em ${Arquivo}: $($r.Saida) $($r.Erro)" }
    if (-not $SemDono) {
        $r = Invoke-Nativo -Exe $icacls -Argumentos @($Arquivo, '/setowner', ('*' + $SID_ADMINS), '/Q')
        if ($r.Codigo -ne 0) { throw "icacls /setowner falhou em ${Arquivo}: $($r.Saida) $($r.Erro)" }
    }
}

function Test-Elevado {
    $id = [Security.Principal.WindowsIdentity]::GetCurrent()
    (New-Object Security.Principal.WindowsPrincipal($id)).IsInRole([Security.Principal.WindowsBuiltInRole]::Administrator)
}

function Test-CaminhoAncora([string] $Ancora) {
    # A âncora fica em <base>\<pasta>\<arquivo>; o script corta a herança da base e da pasta, então nenhuma das duas
    # pode ser a raiz de um disco nem uma pasta do sistema ou do perfil.
    if (-not $Ancora -or -not [IO.Path]::IsPathRooted($Ancora)) { return 'a âncora precisa de caminho absoluto' }
    $pasta = Split-Path -Parent $Ancora
    $base = Split-Path -Parent $pasta
    if (-not $base -or [IO.Path]::GetPathRoot($base).TrimEnd($BARRA) -eq $base.TrimEnd($BARRA)) {
        return "a pasta acima da âncora não pode ser a raiz de um disco: $base"
    }
    $proibidas = @($env:ProgramData, $env:SystemRoot, $env:ProgramFiles, ${env:ProgramFiles(x86)}, $env:USERPROFILE,
                   $HOME, (Join-Path $env:SystemDrive 'Users')) | Where-Object { $_ } | ForEach-Object { $_.TrimEnd($BARRA) }
    foreach ($p in @($pasta, $base)) {
        if ($proibidas -contains $p.TrimEnd($BARRA)) {
            return "a âncora não pode ficar direto em ${p}: use uma pasta própria, como FundacaoIA\confianca"
        }
    }
    $null
}

function Test-CertificadoPython($Assinatura, [string] $Versao, $Politica = $null) {
    # R177-HOST-01 / 1.7.9: Valid continua sendo decisão do Authenticode do Windows, inclusive o timestamp.
    # A lista não deriva do Python instalado: pins-python.json registra o artefato oficial não executado, hash e data.
    # Emissor + sujeito completos + thumbprint + release precisam corresponder ao MESMO pin. Nunca há fallback por CN.
    # Não comparar NotAfter com o relógio: uma assinatura timestamped antiga ainda pode ser Authenticode Valid.
    $motivos = New-Object System.Collections.Generic.List[string]
    $aceito = $null
    try {
        if ($null -eq $Politica) {
            $Politica = [IO.File]::ReadAllText((Join-Path $PSScriptRoot 'pins-python.json'), [Text.Encoding]::UTF8) |
                Microsoft.PowerShell.Utility\ConvertFrom-Json
        }
        if ($Politica.schema_version -cne '1') { throw 'schema de pins desconhecido' }
        $pins = @($Politica.pins)
        foreach ($pin in $pins) {
            if ($pin.python_version -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$' -or
                $pin.thumbprint -cnotmatch '^[0-9A-F]{40}$' -or
                -not $pin.subject -or -not $pin.issuer -or
                $pin.verified_on -cnotmatch '^[0-9]{4}-[0-9]{2}-[0-9]{2}$' -or
                $pin.source_url -cnotmatch '^https://www\.python\.org/ftp/python/' -or
                $pin.source_sha256 -cnotmatch '^[0-9a-f]{64}$' -or
                $pin.python_exe_sha256 -cnotmatch '^[0-9a-f]{64}$') { throw 'pin sem proveniencia completa' }
        }
        if ([string]$Assinatura.Status -cne 'Valid' -or $null -eq $Assinatura.SignerCertificate) {
            $motivos.Add('assinatura Authenticode precisa ser Valid antes de conferir o pin')
        } else {
            $cert = $Assinatura.SignerCertificate
            foreach ($pin in $pins) {
                if ($Versao -ceq $pin.python_version -and $cert.Thumbprint -ceq $pin.thumbprint -and
                    $cert.Subject -ceq $pin.subject -and $cert.Issuer -ceq $pin.issuer) { $aceito = $pin; break }
            }
            if ($null -eq $aceito) {
                $motivos.Add('certificado ou release sem pin comprovado: o titular precisa incorporar em pins-python.json ' +
                    'o pin de um artefato oficial publicado em https://www.python.org/ftp/python/ e conferido com ' +
                    'Get-AuthenticodeSignature -LiteralPath <python.exe-extraido-sem-executar>; depois, refazer o preparo')
            }
        }
    } catch {
        $motivos.Add('manifesto de pins ausente ou invalido: o preparo recusa sem fallback pelo nome do assinante')
    }
    [pscustomobject]@{ Ok = ($motivos.Count -eq 0 -and $null -ne $aceito); Motivos = $motivos.ToArray()
                       Thumbprint = $(if ($null -ne $aceito) { $aceito.thumbprint } else { $null }) }
}

function Get-SshKeygen {
    # O do sistema, por caminho fixo, como a conferência das decisões (um ssh-keygen posto antes no PATH não decide);
    # a pasta do sistema pela API, não pelo $env:SystemRoot (CI-F3: um perfil trocava o ssh-keygen que gera a chave e
    # recebe a senha dela).
    $sistema = Get-ProgramaDoSistema 'OpenSSH\ssh-keygen.exe'
    if ([IO.File]::Exists($sistema)) { return $sistema }
    $null
}

function Get-NomeDaConta([string] $Sid) {
    try { (New-Object System.Security.Principal.SecurityIdentifier($Sid)).Translate([System.Security.Principal.NTAccount]).Value } catch { $Sid }
}

function Test-Interpretador([string] $Caminho) {
    # O python.exe que roda o ajudante e, pelo perfil gerado, os hooks das sessões do Windows [Decisão; auditoria Codex
    # Security da 1.7.6, #3]: caminho absoluto local, sem ligação, o próprio python.exe, assinatura Authenticode válida
    # da Python Software Foundation e nenhuma escrita para grupos amplos (qualquer conta comum) no arquivo, na pasta
    # dele e, para trocar a pasta, na de cima; dono só esta conta, Administradores, Sistema ou TrustedInstaller.
    # Escrita dada a uma conta ou grupo nominal vai para Avisos. Só confere: nada é executado aqui.
    $motivos = New-Object System.Collections.Generic.List[string]
    $avisos = New-Object System.Collections.Generic.List[string]
    $r = [ordered]@{ Caminho = $Caminho; Origem = $null; Motivos = $null; Avisos = $null; Assinante = $null; Sha256 = $null
                    Versao = $null; CertificadoThumbprint = $null }
    try {
        if (-not $Caminho -or -not [IO.Path]::IsPathRooted($Caminho) -or $Caminho.StartsWith('\\')) {
            $motivos.Add("caminho absoluto num disco local esperado: $Caminho")
        } elseif (-not (Test-Path -LiteralPath $Caminho -PathType Leaf)) {
            $motivos.Add("arquivo ausente: $Caminho")
        } else {
            $r.Caminho = [IO.Path]::GetFullPath($Caminho)
            if ([IO.Path]::GetFileName($r.Caminho) -ne 'python.exe') { $motivos.Add("não é o python.exe: $($r.Caminho)") }
            $p = $r.Caminho
            while ($p) {
                if ((Microsoft.PowerShell.Management\Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    $motivos.Add("ligação (link simbólico ou junção) no caminho: $p")
                }
                $p = Split-Path -Parent $p
            }
            $a = Microsoft.PowerShell.Security\Get-AuthenticodeSignature -LiteralPath $r.Caminho
            if ($a.SignerCertificate) {
                $r.Assinante = $a.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
            }
            if ($a.Status -ne 'Valid') {
                $motivos.Add("assinatura Authenticode $($a.Status): o python.exe do instalador oficial (python.org) é assinado pela $ASSINANTE_PYTHON")
            } elseif ($r.Assinante -cne $ASSINANTE_PYTHON) {
                $motivos.Add("assinatura de $($r.Assinante), não da $ASSINANTE_PYTHON")
            }
            $r.Versao = [Diagnostics.FileVersionInfo]::GetVersionInfo($r.Caminho).ProductVersion
            $pin = Test-CertificadoPython -Assinatura $a -Versao $r.Versao
            foreach ($motivo in @($pin.Motivos)) { $motivos.Add($motivo) }
            $r.CertificadoThumbprint = $pin.Thumbprint
            $confiaveis = @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value, $SID_ADMINS, $SID_SISTEMA, $SID_INSTALADOR)
            $pasta = Split-Path -Parent $r.Caminho
            foreach ($par in @(@($r.Caminho, $MASCARA_ESCRITA), @($pasta, $MASCARA_ESCRITA), @((Split-Path -Parent $pasta), $MASCARA_TROCA))) {
                $alvo, $mascara = $par
                if (-not $alvo) { continue }
                $acl = Microsoft.PowerShell.Security\Get-Acl -LiteralPath $alvo
                $dono = $acl.GetOwner([System.Security.Principal.SecurityIdentifier]).Value
                if ($confiaveis -notcontains $dono) { $motivos.Add("o dono de $alvo é outra conta ($(Get-NomeDaConta $dono)): o dono troca as permissões") }
                foreach ($regra in @($acl.GetAccessRules($true, $true, [System.Security.Principal.SecurityIdentifier]))) {
                    $sid = $regra.IdentityReference.Value
                    if ($regra.AccessControlType -ne 'Allow' -or ($regra.PropagationFlags -band [System.Security.AccessControl.PropagationFlags]::InheritOnly) -or
                        (([int64]$regra.FileSystemRights -band $mascara) -eq 0) -or $confiaveis -contains $sid -or @('S-1-3-0', 'S-1-3-4') -contains $sid) { continue }
                    if ($SIDS_AMPLOS -contains $sid -or $sid -match '^S-1-5-21-[0-9-]+-513$') {
                        $motivos.Add("qualquer conta comum pode alterar $alvo ($(Get-NomeDaConta $sid), $sid)")
                    } else {
                        $avisos.Add("escrita dada a $(Get-NomeDaConta $sid) ($sid) em $alvo")
                    }
                }
            }
            $r.Sha256 = Get-Sha256Arquivo $r.Caminho
        }
    } catch {
        $motivos.Add("não consegui conferir $($Caminho): $($_.Exception.Message)")
    }
    $r.Motivos = $motivos.ToArray()
    $r.Avisos = $avisos.ToArray()
    [pscustomobject]$r
}

function Get-CandidatosPython {
    # Instalações registradas pelo instalador oficial (PEP 514; HKLM antes de HKCU, versão mais nova primeiro) e, por
    # último, o PATH sem os atalhos da Microsoft Store. O perfil de destino (.claude) não indica o interpretador: o
    # preparo existe para refazê-lo, e um hook ali pode apontar qualquer executável [auditoria Codex Security, #3].
    $saida = New-Object System.Collections.Generic.List[object]
    foreach ($par in @(@('HKLM:\SOFTWARE\Python\PythonCore', 'registro do Windows (HKLM)'),
                       @('HKLM:\SOFTWARE\WOW6432Node\Python\PythonCore', 'registro do Windows (HKLM)'),
                       @('HKCU:\SOFTWARE\Python\PythonCore', 'registro do Windows (HKCU)'))) {
        $chave, $origem = $par
        $versoes = @(Microsoft.PowerShell.Management\Get-ChildItem -LiteralPath $chave -ErrorAction SilentlyContinue | Sort-Object -Descending -Property {
            $m = [regex]::Match($_.PSChildName, '^(\d+)\.(\d+)')
            if ($m.Success) { [version]($m.Groups[1].Value + '.' + $m.Groups[2].Value) } else { [version]'0.0' } })
        foreach ($v in $versoes) {
            $k = $v.OpenSubKey('InstallPath')
            if (-not $k) { continue }
            $exe = [string]$k.GetValue('ExecutablePath')
            if (-not $exe -and $k.GetValue('')) { $exe = Join-Path ([string]$k.GetValue('')) 'python.exe' }
            $k.Close()
            if ($exe) { $saida.Add([pscustomobject]@{ Caminho = $exe; Origem = $origem }) }
        }
    }
    foreach ($c in @(Microsoft.PowerShell.Core\Get-Command python.exe -CommandType Application -All -ErrorAction SilentlyContinue)) {
        if ($c.Source -notlike '*\WindowsApps\*') { $saida.Add([pscustomobject]@{ Caminho = $c.Source; Origem = 'PATH' }) }
    }
    $saida.ToArray()
}

function Find-Python([string] $Indicado) {
    # Com -Python, só ele, conferido; sem, o primeiro candidato que passa na conferência. Nenhum candidato: $null.
    if ($Indicado) {
        $t = Test-Interpretador $Indicado
        $t.Origem = 'informado (-Python)'
        return $t
    }
    $vistos = @{}
    $recusados = New-Object System.Collections.Generic.List[string]
    foreach ($c in @(Get-CandidatosPython)) {
        if ($vistos.ContainsKey($c.Caminho.ToLowerInvariant())) { continue }
        $vistos[$c.Caminho.ToLowerInvariant()] = $true
        $t = Test-Interpretador $c.Caminho
        $t.Origem = $c.Origem
        if ($t.Motivos.Count -eq 0) { return $t }
        $recusados.Add($t.Caminho + ': ' + ($t.Motivos -join '; '))
    }
    if ($recusados.Count -eq 0) { return $null }
    [pscustomobject]@{ Caminho = $null; Origem = 'nenhum candidato passou'; Motivos = $recusados.ToArray(); Avisos = @()
                       Assinante = $null; Sha256 = $null }
}

function Invoke-Ajudante([string] $Py, [string[]] $Argumentos) {
    # -I: sem PYTHONPATH, PYTHONHOME e site do usuário (o interpretador conferido roda só o ajudante da skill).
    Invoke-Nativo -Exe $Py -Argumentos (@('-I', '-B', $AJUDANTE) + @($Argumentos))
}

# ------------------------------------------------------------------ plano (1.7.10): pastas e projeto das sessões
function Split-ListaDeUnidades([string[]] $Valores) {
    # Com -File, o PowerShell entrega "D:\a,E:\b" como um texto só: separa só na vírgula seguida de letra de unidade e
    # dois-pontos (",D:"), que não aparece em nome de pasta do Windows (mapa do Windows, 31/10/2026: o caminho juntado
    # passava em silêncio e nenhuma origem ficava protegida).
    $saida = New-Object System.Collections.Generic.List[string]
    foreach ($v in @($Valores)) {
        if (-not $v) { continue }
        foreach ($parte in [regex]::Split([string]$v, ',(?=\s*[A-Za-z]:)')) { if ($parte.Trim()) { $saida.Add($parte.Trim()) } }
    }
    $saida.ToArray()
}

function Get-PastasConferidas([string[]] $Valores, [string] $Rotulo, [switch] $AceitarAusente, [string] $SeAusente) {
    # Cada pasta: caminho absoluto num disco local (sem rede), existente, sem curinga nem quebra de linha, fora da raiz,
    # sem conter a raiz e sem repetição. Qualquer falha: nada é gravado (código 2), antes da chave e do UAC. Com
    # -AceitarAusente (as pastas registradas que sumiram, -SomenteLeituraAusente; as cópias num disco desligado,
    # -BackupsAusente), a existência não é exigida: o resto, sim. -SeAusente: o que a recusa da pasta inexistente diz a
    # mais. A raiz de um disco fica com a barra ("F:\", um disco só das cópias): sem ela, "F:" não é pasta nenhuma para o
    # ajudante (regra_windows) e voltava a este script como "caminho absoluto esperado"; e a pasta que contém a raiz da
    # fundação negaria às sessões a própria fundação (revisão seguinte da terceira rodada da integração, defeito 1).
    $lista = New-Object System.Collections.Generic.List[string]
    foreach ($p in @(Split-ListaDeUnidades $Valores)) {
        if ($p -notmatch '^[A-Za-z]:[\\/]' -or $p -match '[\*\?\r\n]') {
            return @{ Erro = "${Rotulo}: caminho absoluto num disco local esperado: $p"; Lista = @() }
        }
        if (-not $AceitarAusente -and -not (Test-Path -LiteralPath $p -PathType Container)) {
            return @{ Erro = "${Rotulo}: pasta inexistente (ou disco não montado): $p$SeAusente"; Lista = @() }
        }
        try { $cheio = [IO.Path]::GetFullPath($p) } catch {  # ", <, > ou | no nome: nenhuma pasta do Windows os tem
            return @{ Erro = "${Rotulo}: caminho absoluto num disco local esperado: $p"; Lista = @() }
        }
        if ($cheio -notmatch '^[A-Za-z]:\\$') { $cheio = $cheio.TrimEnd($BARRA) }
        $semBarra = $cheio.TrimEnd($BARRA)  # a comparação com a raiz é pelo texto sem a barra final
        $raizCheia = $Raiz.TrimEnd($BARRA)
        if ($semBarra -ieq $raizCheia -or $semBarra.StartsWith($raizCheia + $BARRA, [StringComparison]::OrdinalIgnoreCase)) {
            return @{ Erro = "${Rotulo}: pasta dentro da raiz da fundação não serve: $p"; Lista = @() }
        }
        if (($raizCheia + $BARRA).StartsWith($semBarra + $BARRA, [StringComparison]::OrdinalIgnoreCase)) {
            return @{ Erro = "${Rotulo}: a pasta contém a raiz da fundação: use uma subpasta que não a contenha: $p"; Lista = @() }
        }
        if (-not ($lista | Where-Object { $_ -ieq $cheio })) { $lista.Add($cheio) }
    }
    @{ Erro = $null; Lista = $lista.ToArray() }
}

function ConvertTo-AspasPowerShell([string] $Texto) {
    # Literal do PowerShell entre aspas simples: nada dentro é expandido ($, crase); a aspa simples, também as
    # tipográficas que o PowerShell trata como ela (U+2018 a U+201B), se dobra (a regra do comando_titular do kit).
    # Daqui para os dois scripts: o preparar-projeto.ps1 a usa pelo Get-ComandoComBackups.
    $sb = New-Object System.Text.StringBuilder
    [void]$sb.Append("'")
    foreach ($c in $Texto.ToCharArray()) {
        if ($c -eq [char]39 -or ([int]$c -ge 0x2018 -and [int]$c -le 0x201B)) { [void]$sb.Append($c) }
        [void]$sb.Append($c)
    }
    [void]$sb.Append("'")
    $sb.ToString()
}

function Get-ComandoComBackups([string] $Script, $Dados, [string[]] $Excluir = @(), $Sugestao = $null) {
    # O comando pronto da recusa sem -Backups nem -SemBackups (folha da integração, I21; revisão da terceira rodada,
    # defeito 1, que pôs o mesmo portão aqui): o script de $Script com os mesmos parâmetros dados (menos -Backups,
    # -BackupsAusente, -SemBackups e os de $Excluir) e -Backups com a pasta das cópias por preencher (nenhum valor da
    # raiz vira sugestão de pasta) ou, com $Sugestao (Get-SugestaoDasCopias: a pasta de cima da última cópia
    # registrada; revisão seguinte, defeito 2), a opção e a pasta dela. Cada valor vai citado (ConvertTo-AspasPowerShell);
    # listas, juntas na vírgula, como o -File as entrega.
    $partes = New-Object System.Collections.Generic.List[string]
    $partes.Add('powershell -ExecutionPolicy Bypass -File ' + (ConvertTo-AspasPowerShell $Script))
    foreach ($nome in @($Dados.Keys)) {
        if (@('Backups', 'BackupsAusente', 'SemBackups') + @($Excluir) -contains $nome) { continue }
        $valor = $Dados[$nome]
        if ($valor -is [System.Management.Automation.SwitchParameter]) {
            if ($valor.IsPresent) { $partes.Add('-' + $nome) }
            continue
        }
        $partes.Add('-' + $nome + ' ' + (ConvertTo-AspasPowerShell ((@($valor) | ForEach-Object { [string]$_ }) -join ',')))
    }
    if ($Sugestao) { $partes.Add($Sugestao.Opcao + ' ' + (ConvertTo-AspasPowerShell $Sugestao.Pasta)) }
    else { $partes.Add("-Backups '<pasta das cópias de segurança, em outro disco>'") }
    $partes -join ' '
}

function Get-UltimaCopia([string] $Py) {
    # O registro da última cópia (registry\ultima-copia.json, fundacao.ultima_copia/1, que o backup criar do kit grava),
    # lido pelo ajudante como o hook aviso_copia.py o lê: sem seguir ligação nem vínculo físico, até 64 KiB, sem tocar o
    # disco das cópias (revisão seguinte da terceira rodada da integração, defeito 2). Ajudante que falha: 'recusado'.
    $vazio = [ordered]@{ registro = 'recusado'; destino = $null; destino_windows = $null; pasta_das_copias = $null
                         motivo = $null }
    $r = Invoke-Ajudante $Py @('ultima-copia', '--raiz', $Raiz)
    try {
        if ($r.Codigo -ne 0) { throw ($r.Saida + $r.Erro).Trim() }
        $u = $r.Saida | Microsoft.PowerShell.Utility\ConvertFrom-Json
        if (@('ausente', 'lido', 'recusado') -notcontains [string](Get-Campo $u 'registro')) { throw 'resposta fora da forma' }
        return $u
    } catch {
        $vazio.motivo = 'o ajudante não leu o registro: ' + $_.Exception.Message
        return [pscustomobject]$vazio
    }
}

function Get-SugestaoDasCopias($Ultima) {
    # A pasta de cima da última cópia registrada, para o comando pronto no lugar do texto entre < > (defeito 2): só a
    # que passa pelas regras de -Backups (Get-PastasConferidas, sem exigir que exista) e não tem caractere que uma pasta
    # do Windows não tem. O valor é da sessão até prova em contrário (ela grava registry\): nunca vira argumento quebrado
    # nem pasta da raiz. Existe agora: -Backups; não existe (disco desligado): -BackupsAusente. Sem pasta boa: $null.
    if (-not $Ultima -or [string](Get-Campo $Ultima 'registro') -cne 'lido') { return $null }
    $pasta = [string](Get-Campo $Ultima 'pasta_das_copias')
    if (-not $pasta -or $pasta -notmatch '^[A-Za-z]:\\' -or $pasta.Length -gt 400 -or
        $pasta -match '[\x00-\x1f\x7f"<>|*?]' -or $pasta.Substring(2).Contains(':')) { return $null }
    $c = Get-PastasConferidas -Valores @($pasta) -Rotulo 'registro' -AceitarAusente
    if ($c.Erro -or @($c.Lista).Count -ne 1) { return $null }
    $opcao = '-BackupsAusente'
    if (Test-Path -LiteralPath $c.Lista[0] -PathType Container) { $opcao = '-Backups' }
    [pscustomobject]@{ Opcao = $opcao; Pasta = [string]$c.Lista[0] }
}

function Get-TituloDoComandoPronto([string] $PastaSugerida) {
    # A linha antes do comando pronto, nos dois scripts: com a pasta lida do registro da última cópia, o titular confere
    # se é a das cópias dele (o registro pode ter sido forjado); sem ela, troca o texto entre < >.
    $titulo = 'Comando pronto (no PowerShell comum, sem "Executar como administrador"; '
    if ($PastaSugerida) { return $titulo + 'a pasta veio do registro da última cópia, registry\ultima-copia.json: confira se é a das suas cópias):' }
    $titulo + 'troque o texto entre < > pela pasta das cópias):'
}

function Test-DentroDeAlguma([string] $Caminho, [string[]] $Pastas) {
    # O caminho é uma das pastas ou fica dentro dela (sem caixa; a raiz de um disco, "F:\", cobre o disco).
    $alvo = $Caminho.TrimEnd($BARRA) + $BARRA
    foreach ($p in @($Pastas)) {
        if ($p -and $alvo.StartsWith(([string]$p).TrimEnd($BARRA) + $BARRA, [StringComparison]::OrdinalIgnoreCase)) { return $true }
    }
    $false
}

function Get-PortaoDasCopias {
    # O portão das cópias de segurança, o mesmo nos dois scripts (folha da integração, I21; revisão da terceira rodada,
    # defeitos 1 e 2; revisão seguinte, defeito 2): o .claude\settings.json é refeito inteiro, só com o que o preparo
    # recebe, e sem as cópias sairia sem o Read e o Edit negados delas, que têm os dados de todos os projetos. Decide
    # pelas listas conferidas (-Backups e -BackupsAusente, nunca o valor cru) e pelo registro da última cópia
    # (Get-UltimaCopia): com um destino no Windows registrado, o -SemBackups é recusado, e o comando pronto traz a pasta
    # dele. O registro só recusa e sugere, nunca aceita: uma sessão o forja (no Windows não há sandbox), e com ele forjado
    # o pior é uma recusa a mais. Codigo 0 = segue, com as Pendencias; 2 = recusa, com a Mensagem e o ComandoPronto.
    param($Copias, $Ausentes, [bool] $SemBackups, $Ultima, [string] $Script, $Dados, [string[]] $Excluir = @(),
          [string] $Quem = 'este script')
    $r = [ordered]@{ Codigo = 0; Mensagem = $null; ComandoPronto = $null; PastaSugerida = $null
                     Pendencias = (New-Object System.Collections.Generic.List[string]) }
    $todas = @(@($Copias) + @($Ausentes) | Where-Object { $_ })
    if ($todas.Count -gt 0 -and $SemBackups) {
        $r.Codigo = 2
        $r.Mensagem = '-Backups (ou -BackupsAusente) e -SemBackups juntos: use um só (nada foi alterado)'
        return [pscustomobject]$r
    }
    $destino = $null
    if ($Ultima -and [string](Get-Campo $Ultima 'registro') -ceq 'lido') { $destino = [string](Get-Campo $Ultima 'destino_windows') }
    if ($todas.Count -eq 0 -and ($destino -or -not $SemBackups)) {
        $sugestao = $null
        if ($destino) { $sugestao = Get-SugestaoDasCopias $Ultima }
        $r.Codigo = 2
        $r.ComandoPronto = Get-ComandoComBackups -Script $Script -Dados $Dados -Excluir $Excluir -Sugestao $sugestao
        if ($sugestao) { $r.PastaSugerida = $sugestao.Pasta }
        $porque = "$Quem refaz inteiro o .claude\settings.json das sessões do Windows e, sem -Backups, ele sairia sem o Read e o Edit negados das cópias, que têm os dados de todos os projetos"
        if ($SemBackups) {
            $r.Mensagem = "-SemBackups recusado: há cópia de segurança registrada em $destino (registry\ultima-copia.json), e $porque. Use -Backups com a pasta das cópias (o comando pronto está acima; com o disco delas desligado, -BackupsAusente). Nada foi alterado"
        } elseif ($destino) {
            $r.Mensagem = "falta -Backups (a pasta das cópias de segurança): $porque. Há cópia registrada em $destino (registry\ultima-copia.json): rode de novo com -Backups (o comando pronto está acima, com a pasta dela; com o disco desligado, -BackupsAusente). Nada foi alterado"
        } else {
            $r.Mensagem = "falta -Backups (a pasta das cópias de segurança): $porque. Rode de novo com -Backups (o comando pronto está acima) ou, se ainda não há cópias, com -SemBackups. Nada foi alterado"
        }
        return [pscustomobject]$r
    }
    $estado = ''
    if ($Ultima) { $estado = [string](Get-Campo $Ultima 'registro') }
    if ($SemBackups -and $estado -ceq 'recusado') {
        $r.Pendencias.Add('o registro da última cópia (registry\ultima-copia.json) foi recusado (' + [string](Get-Campo $Ultima 'motivo') + '): se há cópias de segurança, rode de novo com -Backups (ou -BackupsAusente), para o perfil negar a leitura e a edição delas')
    }
    if ($destino -and $todas.Count -gt 0 -and -not (Test-DentroDeAlguma $destino $todas)) {
        $r.Pendencias.Add("a última cópia registrada ($destino, em registry\ultima-copia.json) fica fora das pastas de -Backups e -BackupsAusente: o perfil não nega a leitura dela; se ela é sua, inclua a pasta dela e rode de novo")
    }
    [pscustomobject]$r
}

function Get-ProjetoRegistrado([string] $Claude) {
    # O projeto que as sessões do Windows já usam: o do env do settings.json (1.7.10) ou, antes dele, o do
    # settings.local.json (1.7.9). Só o valor, conferido como identificador; nada dali é executado.
    foreach ($nome in @('settings.json', 'settings.local.json')) {
        $arq = Join-Path $Claude $nome
        if (-not (Test-Path -LiteralPath $arq -PathType Leaf)) { continue }
        try { $j = [IO.File]::ReadAllText($arq) | Microsoft.PowerShell.Utility\ConvertFrom-Json } catch { continue }
        $amb = Get-Campo $j 'env'
        $p = $null
        if ($amb) { $p = Get-Campo $amb 'FUNDACAO_PROJECT' }
        if ($p -and ([string]$p -cmatch $ID_PROJETO) -and ([string]$p -notlike '*--*')) {
            return [pscustomobject]@{ Projeto = [string]$p; Origem = $nome }
        }
    }
    $null
}

# ------------------------------------------------------------------ etapa do administrador (depois do UAC)
function Invoke-EtapaAncoraInterna($Acoes) {
    if (-not (Test-Elevado)) { return @{ codigo = 4; erro = 'esta etapa só roda como administrador (confirmação do UAC)' } }
    $fundacaoDoScript = Get-FundacaoQueContem $PSScriptRoot  # CI-F1: como administrador, nunca de dentro de projects\
    if ($fundacaoDoScript) { return @{ codigo = 2; erro = (Get-RecusaDeProjects $fundacaoDoScript 'preparar-maquina.ps1') } }
    $problema = Test-CaminhoAncora $Ancora
    if ($problema) { return @{ codigo = 2; erro = $problema } }
    if (-not ($Titular -cmatch $IDENTIFICADOR)) { return @{ codigo = 2; erro = "titular inválido: $Titular" } }
    if (-not $ChavePublica -or -not (Test-Path -LiteralPath $ChavePublica -PathType Leaf)) {
        return @{ codigo = 2; erro = "chave pública ausente: $ChavePublica" }
    }
    $linhaPublica = ([IO.File]::ReadAllText($ChavePublica)).Trim()
    $fp = Get-ImpressaoDigital $linhaPublica
    if (-not $fp -or $fp -cne $ImpressaoEsperada) {
        return @{ codigo = 5; erro = "a chave pública não é a conferida antes do UAC (esperada $ImpressaoEsperada, encontrada $fp): nada foi gravado" }
    }
    $pasta = Split-Path -Parent $Ancora
    $base = Split-Path -Parent $pasta
    $linhas = @()
    if (Test-Path -LiteralPath $Ancora -PathType Leaf) { $linhas = @([IO.File]::ReadAllLines($Ancora)) }
    $m = Merge-Ancora -Linhas $linhas -Titular $Titular -LinhaNova (Get-LinhaAncora $Titular $linhaPublica) -Trocar:$TrocarChave
    if ($m.Acao -eq 'conflito') {
        return @{ codigo = 6; erro = "a âncora já tem outra chave para ${Titular}: para trocar, rode com -TrocarChave" }
    }
    try {
        foreach ($p in @($base, $pasta)) {
            if (-not (Test-Path -LiteralPath $p -PathType Container)) {
                New-Item -ItemType Directory -Path $p | Out-Null
                $Acoes.Add("pasta criada: $p")
            }
        }
        foreach ($p in @($base, $pasta)) { Set-AclProtegida -Pasta $p; $Acoes.Add("dono Administradores e herança cortada: $p") }
        if ($m.Acao -ne 'igual') {
            if (Test-Path -LiteralPath $Ancora -PathType Leaf) {
                $copia = $Ancora + '.anterior-' + (Get-Date -Format 'yyyyMMddTHHmmss')
                Copy-Item -LiteralPath $Ancora -Destination $copia
                Set-AclArquivoHerdada -Arquivo $copia
                $Acoes.Add("cópia da âncora anterior: $copia")
            }
            [IO.File]::WriteAllText($Ancora, ((@($m.Linhas) -join "`r`n") + "`r`n"), (New-Object System.Text.UTF8Encoding($false)))
            $Acoes.Add("âncora gravada ($($m.Acao)): linha de $Titular com $fp")
        }
        Set-AclArquivoHerdada -Arquivo $Ancora
        $Acoes.Add("arquivo herdando da pasta, dono Administradores: $Ancora")
    } catch {
        return @{ codigo = 1; erro = $_.Exception.Message }
    }
    @{ codigo = 0; erro = $null }
}

function Invoke-EtapaAncora {
    $acoes = New-Object System.Collections.Generic.List[string]
    $r = Invoke-EtapaAncoraInterna $acoes
    if ($RegistroEtapa) {
        $registro = [ordered]@{ etapa = 'ancora'; ancora = $Ancora; titular = $Titular; codigo = $r.codigo; erro = $r.erro
                                acoes = $acoes.ToArray(); fim = (Get-Date).ToString('o') }
        try { [IO.File]::WriteAllText($RegistroEtapa, (ConvertTo-Json -InputObject $registro -Depth 4), (New-Object System.Text.UTF8Encoding($false))) } catch { }
    }
    foreach ($a in $acoes) { Write-Host "  $a" }
    if ($r.erro) { Write-Host "Etapa da âncora NÃO concluída: $($r.erro)" }
    [int]$r.codigo
}

# ------------------------------------------------------------------ cópia protegida da ferramenta do titular (I11)
function Get-SondagemPython([string] $Python) {
    # O Python que o hashes.json da cópia protegida registra tem de ser instalado para todos os usuários (folha da
    # integração, I11): vista DESTA conta, sem elevação, ela não altera o python.exe, a pasta dele, Lib,
    # Lib\site-packages e DLLs (um .pth plantado roda antes da ferramenta, também com -I; reconferência do ABERTURAS) nem
    # troca a pasta de cima. É a sondagem da âncora, sem alterar nada.
    $motivos = New-Object System.Collections.Generic.List[string]
    $pasta = Split-Path -Parent $Python
    $pedidos = @(, @($Python, $DIREITOS_ARQUIVO, 'Leaf'))
    foreach ($sub in @('', 'Lib', 'Lib\site-packages', 'DLLs')) {
        $c = $pasta
        if ($sub) { $c = Join-Path $pasta $sub }
        if ($sub -eq '' -or (Test-Path -LiteralPath $c -PathType Container)) { $pedidos += , @($c, $DIREITOS_PASTA, 'Container') }
    }
    $acima = Split-Path -Parent $pasta
    if ($acima) { $pedidos += , @($acima, $DIREITOS_ACIMA, 'Container') }
    foreach ($par in $pedidos) {
        $caminho, $tabela, $tipo = $par
        if (-not (Test-Path -LiteralPath $caminho -PathType $tipo)) { $motivos.Add("ausente: $caminho"); continue }
        $d = Get-Direitos $caminho $tabela
        $concedidos = @($d.Keys | Where-Object { $d[$_] })
        if ($concedidos.Count -gt 0) { $motivos.Add("esta conta tem $($concedidos -join ', ') em $caminho") }
    }
    [pscustomobject]@{ python = $Python; todos = ($motivos.Count -eq 0); motivos = $motivos.ToArray() }
}

function Test-RelDaCopia([string] $Rel) {
    # Caminho de arquivo da cópia protegida, como o plano do ajudante o escreve: a ferramenta ou um arquivo do pacote
    # do kit, relativo, com '/', sem parte vazia, '.', '..', barra invertida, ':' nem controle.
    if (-not $Rel -or $Rel -match '[\\:\x00-\x1f]' -or $Rel.StartsWith('/')) { return $false }
    if ($Rel -cne $REL_FERRAMENTA -and -not $Rel.StartsWith($REL_KIT_DA_FERRAMENTA, [StringComparison]::Ordinal)) { return $false }
    -not (@($Rel -split '/') | Where-Object { $_ -eq '' -or $_ -eq '.' -or $_ -eq '..' })
}

function Test-ReparsePoint([string] $Caminho) {
    [bool]((Microsoft.PowerShell.Management\Get-Item -LiteralPath $Caminho -Force).Attributes -band [IO.FileAttributes]::ReparsePoint)
}

function Get-ArquivosSemSeguir([string] $Pasta) {
    # Os arquivos sob a pasta (caminho relativo com '/'), as pastas (caminho completo, a própria inclusive) e as
    # ligações achadas, sem atravessar junção nem link simbólico (o Get-ChildItem -Recurse do PowerShell 5.1 entra).
    $arquivos = New-Object System.Collections.Generic.List[string]
    $pastas = New-Object System.Collections.Generic.List[string]
    $ligacoes = New-Object System.Collections.Generic.List[string]
    $pilha = New-Object System.Collections.Generic.Stack[string]
    $pilha.Push($Pasta)
    while ($pilha.Count -gt 0) {
        $atual = $pilha.Pop()
        $pastas.Add($atual)
        foreach ($filho in @(Microsoft.PowerShell.Management\Get-ChildItem -LiteralPath $atual -Force)) {
            $rel = $filho.FullName.Substring($Pasta.TrimEnd($BARRA).Length + 1) -replace '\\', '/'
            if ($filho.Attributes -band [IO.FileAttributes]::ReparsePoint) { $ligacoes.Add($rel) }
            elseif ($filho.PSIsContainer) { $pilha.Push($filho.FullName) }
            else { $arquivos.Add($rel) }
        }
    }
    [pscustomobject]@{ Arquivos = $arquivos.ToArray(); Pastas = $pastas.ToArray(); Ligacoes = $ligacoes.ToArray() }
}

function Remove-PastaSemSeguir([string] $Caminho) {
    # Apaga sem atravessar ligação: junção ou link simbólico sai só como nome e o alvo fica (o Remove-Item -Recurse do
    # PowerShell 5.1 entra em junção; aqui roda como administrador).
    $item = Microsoft.PowerShell.Management\Get-Item -LiteralPath $Caminho -Force
    if ($item.Attributes -band [IO.FileAttributes]::ReparsePoint) {
        if ($item.PSIsContainer) { [IO.Directory]::Delete($Caminho, $false) } else { [IO.File]::Delete($Caminho) }
        return
    }
    if (-not $item.PSIsContainer) {
        $item.Attributes = [IO.FileAttributes]::Normal
        [IO.File]::Delete($Caminho)
        return
    }
    foreach ($filho in @(Microsoft.PowerShell.Management\Get-ChildItem -LiteralPath $Caminho -Force)) { Remove-PastaSemSeguir $filho.FullName }
    [IO.Directory]::Delete($Caminho, $false)
}

function Get-EstadoFerramenta([byte[]] $HashesBytes, $Arquivos, [string] $Destino) {
    # A cópia instalada contra o plano: o hashes.json byte a byte, cada arquivo pelo SHA-256, nenhum a mais, nenhuma
    # ligação; e a sondagem desta conta (a da ferramenta, fundacao_titular.conferir_copia): nenhum direito de alterar
    # arquivo nem pasta da cópia, nem de trocar as pastas de cima. Igual = o conteúdo; protegida = os direitos.
    $motivos = New-Object System.Collections.Generic.List[string]
    $estado = [ordered]@{ existe = (Test-Path -LiteralPath $Destino -PathType Container); igual = $false; protegida = $false
                          motivos = $null }
    if (-not $estado.existe) { $motivos.Add("ausente: $Destino"); $estado.motivos = $motivos.ToArray(); return [pscustomobject]$estado }
    $lista = Get-ArquivosSemSeguir $Destino
    foreach ($l in @($lista.Ligacoes)) { $motivos.Add("ligação na cópia: $l") }
    $esperados = @{}
    foreach ($p in $Arquivos.PSObject.Properties) { $esperados[$p.Name] = [string]$p.Value }
    $esperados['hashes.json'] = Get-Sha256Bytes $HashesBytes
    foreach ($rel in @($lista.Arquivos)) {
        if (-not $esperados.ContainsKey($rel)) { $motivos.Add("arquivo a mais na cópia: $rel"); continue }
        if ((Get-Sha256Arquivo (Join-Path $Destino ($rel -replace '/', '\'))) -cne $esperados[$rel]) { $motivos.Add("arquivo diferente na cópia: $rel") }
    }
    foreach ($rel in @($esperados.Keys)) { if (@($lista.Arquivos) -notcontains $rel) { $motivos.Add("falta na cópia: $rel") } }
    $estado.igual = ($motivos.Count -eq 0)
    $direitos = New-Object System.Collections.Generic.List[string]
    foreach ($rel in @($lista.Arquivos)) {
        $d = Get-Direitos (Join-Path $Destino ($rel -replace '/', '\')) $DIREITOS_ARQUIVO
        $c = @($d.Keys | Where-Object { $d[$_] })
        if ($c.Count -gt 0) { $direitos.Add("esta conta tem $($c -join ', ') em $rel") }
    }
    foreach ($p in @($lista.Pastas)) {
        $d = Get-Direitos $p $DIREITOS_PASTA
        $c = @($d.Keys | Where-Object { $d[$_] })
        if ($c.Count -gt 0) { $direitos.Add("esta conta tem $($c -join ', ') em $p") }
    }
    $acima = Split-Path -Parent $Destino
    while ($acima) {
        $d = Get-Direitos $acima $DIREITOS_ACIMA
        $c = @($d.Keys | Where-Object { $d[$_] })
        if ($c.Count -gt 0) { $direitos.Add("esta conta tem $($c -join ', ') em $acima") }
        $acima = Split-Path -Parent $acima
    }
    $estado.protegida = ($direitos.Count -eq 0)
    foreach ($m in $direitos) { $motivos.Add($m) }
    $estado.motivos = $motivos.ToArray()
    [pscustomobject]$estado
}

function Get-ItemFerramenta([string] $Py) {
    # A cópia protegida da ferramenta do titular no Windows (folha da integração, I11; core/aberturas_comando do kit),
    # planejada antes do UAC: a árvore que a ferramenta confere (o plano e o hashes.json vêm do ajudante, a mesma conta
    # da cópia do Ubuntu) e, no hashes.json, o Python fixado, só se instalado para todos os usuários. Por usuário (o
    # Python desta máquina, em AppData), a forma do Windows fica pendente com o motivo, e nada pede o UAC por ela.
    $item = [ordered]@{ id = 'ferramenta-titular'; caminho = $Ferramentas; exige_admin = $true; acao = $null
                        python = $Py; python_todos = $false; versao = $null; sha256 = $null; protegida = $false
                        detalhe = $null; sondagem = $null; etapa_administrador = $null; plano = $null }
    $sp = Get-SondagemPython $Py
    $item.python_todos = $sp.todos
    if (-not $sp.todos) {
        $item.acao = 'pendente'
        $item.sondagem = $sp
        $item.detalhe = "o Python fixado ($Py) é instalado só para este usuário (esta conta o altera: " +
            ((@($sp.motivos) | Select-Object -First 2) -join '; ') + "): a cópia protegida do Windows registra só um Python " +
            "instalado para todos os usuários, e a ficha de aberturas não é assinada pela forma do Windows. Assine pela " +
            "forma do Ubuntu (executar_ubuntu, pelo wsl.exe; a cópia dele vem do preparar-wsl.sh) ou instale o Python " +
            "para todos os usuários (instalador oficial do python.org, 'Install for all users') e rode este script de novo"
        return [pscustomobject]$item
    }
    $r = Invoke-Ajudante $Py @('plano-ferramenta', '--python', $Py)
    if ($r.Codigo -ne 0) {
        $item.acao = 'erro'
        $item.detalhe = 'o ajudante recusou o plano da cópia protegida: ' + ($r.Saida + $r.Erro).Trim()
        return [pscustomobject]$item
    }
    $plano = $r.Saida | Microsoft.PowerShell.Utility\ConvertFrom-Json
    $bytes = (New-Object System.Text.UTF8Encoding($false)).GetBytes([string]$plano.hashes_json)
    if ((Get-Sha256Bytes $bytes) -cne [string]$plano.sha256 -or [string]$plano.versao -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$') {
        $item.acao = 'erro'
        $item.detalhe = 'o plano da cópia protegida veio fora da forma do ajudante'
        return [pscustomobject]$item
    }
    $item.versao = [string]$plano.versao
    $item.caminho = Join-Path $Ferramentas $item.versao
    $item.sha256 = [string]$plano.sha256
    $item.plano = [pscustomobject]@{ bytes = $bytes; arquivos = $plano.arquivos }
    $estado = Get-EstadoFerramenta $bytes $plano.arquivos $item.caminho
    $item.sondagem = $estado
    $item.protegida = $estado.protegida
    if ($estado.igual -and $estado.protegida) { $item.acao = 'igual' }
    elseif ($estado.existe) { $item.acao = 'atualizar' }
    else { $item.acao = 'criar' }
    [pscustomobject]$item
}

function Install-CopiaFerramenta([byte[]] $PlanoBytes, [string] $Base, $Acoes, [switch] $SemDono) {
    # A cópia protegida do plano (o hashes.json que o ajudante calculou), em <Base>\<versão>: cada arquivo lido uma vez
    # da skill (sem ligação abaixo dela), conferido pelo SHA-256 do plano e gravado numa pasta nova ao lado; o
    # hashes.json do plano; a ACL de administrador (Set-AclProtegida: herança cortada, Administradores e Sistema com
    # controle total, Usuários só leem; dono Administradores) e a troca de nome no fim. A anterior sai sem atravessar
    # ligação (uma pasta pré-criada por uma sessão pode ter junção). Python registrado: na forma que o kit aceita e com o
    # SHA-256 do python.exe de agora. Erro = exceção, e a pasta nova sai. -SemDono só nos testes sem UAC.
    try { $plano = (New-Object System.Text.UTF8Encoding($false)).GetString($PlanoBytes) | Microsoft.PowerShell.Utility\ConvertFrom-Json } catch {
        throw 'plano da cópia ilegível'
    }
    $arquivos = @()
    if (Get-Campo $plano 'arquivos') { $arquivos = @($plano.arquivos.PSObject.Properties) }
    if ([string](Get-Campo $plano 'schema_version') -cne $ESQUEMA_FERRAMENTA -or
        [string](Get-Campo $plano 'versao') -cnotmatch '^[0-9]+\.[0-9]+\.[0-9]+$' -or $arquivos.Count -eq 0 -or
        @($arquivos | Where-Object { -not (Test-RelDaCopia $_.Name) -or [string]$_.Value -cnotmatch '^[0-9a-f]{64}$' }).Count -gt 0 -or
        @($arquivos | Where-Object { $_.Name -ceq $REL_FERRAMENTA }).Count -ne 1) {
        throw 'plano da cópia fora da forma (esquema, versão ou caminhos)'
    }
    $python = Get-Campo $plano 'python'
    if ($python) {
        $caminho = [string](Get-Campo $python 'caminho')
        if ($caminho -notmatch '^[A-Za-z]:\\(?:[^\\/:*?"<>|`$''\r\n;&]+\\)*python\.exe$' -or
            (Get-Sha256Arquivo $caminho) -cne [string](Get-Campo $python 'sha256')) {
            throw "o Python registrado no plano ($caminho) não confere com o python.exe de agora"
        }
    }
    $destino = Join-Path $Base ([string]$plano.versao)
    $novo = Join-Path $Base ('.novo-' + $plano.versao + '-' + [guid]::NewGuid().ToString('N').Substring(0, 12))
    try {
        foreach ($p in @((Split-Path -Parent $Base), $Base)) {
            if (-not (Test-Path -LiteralPath $p -PathType Container)) {
                New-Item -ItemType Directory -Path $p | Out-Null
                $Acoes.Add("pasta criada: $p")
            }
            if (Test-ReparsePoint $p) { throw "$p é ligação: nada foi gravado" }
            if (-not $SemDono) { Set-AclProtegida -Pasta $p }
        }
        New-Item -ItemType Directory -Path $novo | Out-Null
        foreach ($a in $arquivos) {
            $origem = $SKILL
            foreach ($parte in @($a.Name -split '/')) {
                $origem = Join-Path $origem $parte
                if (Test-ReparsePoint $origem) { throw "ligação na skill: $origem (nada foi instalado)" }
            }
            $bytes = [IO.File]::ReadAllBytes($origem)
            if ((Get-Sha256Bytes $bytes) -cne [string]$a.Value) { throw "$($a.Name) mudou depois do plano: nada foi instalado" }
            $alvo = Join-Path $novo ($a.Name -replace '/', '\')
            [void][IO.Directory]::CreateDirectory((Split-Path -Parent $alvo))
            [IO.File]::WriteAllBytes($alvo, $bytes)
        }
        [IO.File]::WriteAllBytes((Join-Path $novo 'hashes.json'), $PlanoBytes)
        Set-AclProtegida -Pasta $novo -SemDono:$SemDono
        if (-not $SemDono) {
            $icacls = Get-ProgramaDoSistema 'icacls.exe'
            $r = Invoke-Nativo -Exe $icacls -Argumentos @($novo, '/setowner', ('*' + $SID_ADMINS), '/T', '/C', '/Q')
            if ($r.Codigo -ne 0) { throw "icacls /setowner falhou em ${novo}: $($r.Saida) $($r.Erro)" }
        }
        if (Test-Path -LiteralPath $destino) {
            $antigo = Join-Path $Base ('.antigo-' + $plano.versao + '-' + [guid]::NewGuid().ToString('N').Substring(0, 12))
            [IO.Directory]::Move($destino, $antigo)
            [IO.Directory]::Move($novo, $destino)
            try { Remove-PastaSemSeguir $antigo } catch { $Acoes.Add("a cópia anterior ficou em ${antigo}: $($_.Exception.Message)") }
            $Acoes.Add("cópia protegida da ferramenta do titular trocada: $destino")
        } else {
            [IO.Directory]::Move($novo, $destino)
            $Acoes.Add("cópia protegida da ferramenta do titular gravada: $destino")
        }
    } catch {
        if (Test-Path -LiteralPath $novo) { try { Remove-PastaSemSeguir $novo } catch { } }
        throw
    }
    $destino
}

function Invoke-EtapaFerramentaInterna($Acoes) {
    # Como administrador (depois do UAC; folha da integração, I11): o plano conferido pelo SHA-256 de antes do UAC e a
    # cópia gravada por Install-CopiaFerramenta. A conferência de que esta conta não altera a cópia é do passo comum,
    # depois (Get-EstadoFerramenta, sem elevação).
    if (-not (Test-Elevado)) { return @{ codigo = 4; erro = 'esta etapa só roda como administrador (confirmação do UAC)' } }
    $fundacaoDoScript = Get-FundacaoQueContem $PSScriptRoot  # CI-F1: como administrador, nunca de dentro de projects\
    if ($fundacaoDoScript) { return @{ codigo = 2; erro = (Get-RecusaDeProjects $fundacaoDoScript 'preparar-maquina.ps1') } }
    $problema = Test-CaminhoAncora (Join-Path $Ferramentas 'hashes.json')
    if ($problema) { return @{ codigo = 2; erro = ($problema -replace 'a âncora', 'a cópia da ferramenta') } }
    if (-not $PlanoFerramenta -or -not (Test-Path -LiteralPath $PlanoFerramenta -PathType Leaf)) {
        return @{ codigo = 2; erro = "plano da cópia ausente: $PlanoFerramenta" }
    }
    $bytesPlano = [IO.File]::ReadAllBytes($PlanoFerramenta)
    if ((Get-Sha256Bytes $bytesPlano) -cne $FerramentaEsperada) {
        return @{ codigo = 5; erro = 'o plano da cópia não é o conferido antes do UAC: nada foi gravado' }
    }
    try { [void](Install-CopiaFerramenta $bytesPlano $Ferramentas $Acoes) } catch {
        return @{ codigo = 1; erro = $_.Exception.Message }
    }
    @{ codigo = 0; erro = $null }
}

# ------------------------------------------------------------------ chave pública da cópia cifrada (1.7.11)
function Get-PlanoChaveCopia([string] $Arquivo) {
    # O arquivo da chave PÚBLICA da cópia, conferido antes do UAC e de novo pelo administrador: caminho absoluto, arquivo
    # comum (não ligação) até 1 MiB, uma única chave pública OpenPGP armada e nenhum material privado. O conteúdo
    # semântico (uma principal com subchave de cifra válida) é do kit, que recusa a chave na hora de cifrar.
    $p = [ordered]@{ arquivo = $Arquivo; erro = $null; sha256 = $null; bytes = $null }
    if (-not $Arquivo -or -not [IO.Path]::IsPathRooted($Arquivo)) { $p.erro = 'informe o caminho completo do arquivo da chave pública'; return [pscustomobject]$p }
    if (-not (Test-Path -LiteralPath $Arquivo -PathType Leaf)) { $p.erro = "arquivo da chave pública ausente: $Arquivo"; return [pscustomobject]$p }
    if (Test-ReparsePoint $Arquivo) { $p.erro = "o arquivo da chave pública é ligação: $Arquivo"; return [pscustomobject]$p }
    if ((Microsoft.PowerShell.Management\Get-Item -LiteralPath $Arquivo -Force).Length -gt 1048576) { $p.erro = 'o arquivo da chave pública passa de 1 MiB'; return [pscustomobject]$p }
    $bytes = [IO.File]::ReadAllBytes($Arquivo)
    $texto = (New-Object System.Text.UTF8Encoding($false)).GetString($bytes)
    if ($texto -match 'PRIVATE KEY') { $p.erro = 'o arquivo tem material de chave PRIVADA: informe só a chave pública'; return [pscustomobject]$p }
    if (([regex]::Matches($texto, '-----BEGIN PGP PUBLIC KEY BLOCK-----')).Count -ne 1 -or
        $texto -cnotmatch '(?s)^\s*-----BEGIN PGP PUBLIC KEY BLOCK-----.*-----END PGP PUBLIC KEY BLOCK-----\s*$') {
        $p.erro = 'o arquivo não é uma única chave pública OpenPGP armada (BEGIN/END PGP PUBLIC KEY BLOCK)'
        return [pscustomobject]$p
    }
    $p.bytes = $bytes
    $p.sha256 = Get-Sha256Bytes $bytes
    [pscustomobject]$p
}

function Install-ChaveDaCopia([byte[]] $Bytes, [string] $Destino, $Acoes, [switch] $SemDono, [switch] $Trocar) {
    # Como a âncora: as duas pastas acima do arquivo com dono Administradores e herança cortada, o arquivo herdando da
    # pasta e com dono Administradores. Chave diferente já instalada: só com -Trocar, e a anterior fica ao lado. -SemDono
    # só nos testes sem UAC.
    $pasta = Split-Path -Parent $Destino
    $base = Split-Path -Parent $pasta
    foreach ($p in @($base, $pasta)) {
        if (-not (Test-Path -LiteralPath $p -PathType Container)) {
            New-Item -ItemType Directory -Path $p | Out-Null
            $Acoes.Add("pasta criada: $p")
        }
        if (Test-ReparsePoint $p) { throw "$p é ligação: nada foi gravado" }
    }
    if (Test-Path -LiteralPath $Destino) {
        if (Test-ReparsePoint $Destino) { throw "$Destino é ligação: nada foi gravado" }
        if ((Get-Sha256Arquivo $Destino) -cne (Get-Sha256Bytes $Bytes) -and -not $Trocar) {
            throw "já há outra chave da cópia em ${Destino}: para trocar de chave de propósito, rode com -TrocarChaveDaCopia"
        }
    }
    if (-not $SemDono) {  # com a ACL de administrador, só o administrador grava dentro (nos testes sem UAC, -SemDono, ela fica de fora)
        foreach ($p in @($base, $pasta)) { Set-AclProtegida -Pasta $p; $Acoes.Add("dono Administradores e herança cortada: $p") }
    }
    if (Test-Path -LiteralPath $Destino -PathType Leaf) {
        if ((Get-Sha256Arquivo $Destino) -ceq (Get-Sha256Bytes $Bytes)) {
            Set-AclArquivoHerdada -Arquivo $Destino -SemDono:$SemDono
            $Acoes.Add("chave da cópia já era esta; permissões refeitas: $Destino")
            return
        }
        $copia = $Destino + '.anterior-' + (Get-Date -Format 'yyyyMMddTHHmmss')
        Copy-Item -LiteralPath $Destino -Destination $copia
        Set-AclArquivoHerdada -Arquivo $copia -SemDono:$SemDono
        $Acoes.Add("cópia da chave anterior: $copia")
    }
    [IO.File]::WriteAllBytes($Destino, $Bytes)
    Set-AclArquivoHerdada -Arquivo $Destino -SemDono:$SemDono
    $Acoes.Add("chave pública da cópia gravada, herdando da pasta, dono Administradores: $Destino")
}

function Invoke-EtapaChaveCopiaInterna($Acoes) {
    # Como administrador (depois do UAC): o arquivo conferido pelo SHA-256 de antes do UAC e a chave instalada por
    # Install-ChaveDaCopia. A conferência de que esta conta não a altera é do passo comum, depois (Get-SondagemAncora).
    if (-not (Test-Elevado)) { return @{ codigo = 4; erro = 'esta etapa só roda como administrador (confirmação do UAC)' } }
    $fundacaoDoScript = Get-FundacaoQueContem $PSScriptRoot  # CI-F1: como administrador, nunca de dentro de projects\
    if ($fundacaoDoScript) { return @{ codigo = 2; erro = (Get-RecusaDeProjects $fundacaoDoScript 'preparar-maquina.ps1') } }
    $problema = Test-CaminhoAncora $AncoraChaveCopia
    if ($problema) { return @{ codigo = 2; erro = ($problema -replace 'a âncora', 'a chave da cópia') } }
    $plano = Get-PlanoChaveCopia $ChaveDaCopia
    if ($plano.erro) { return @{ codigo = 2; erro = $plano.erro } }
    if (-not $ChaveDaCopiaEsperada -or $plano.sha256 -cne $ChaveDaCopiaEsperada) {
        return @{ codigo = 5; erro = 'a chave pública não é a conferida antes do UAC: nada foi gravado' }
    }
    try { Install-ChaveDaCopia $plano.bytes $AncoraChaveCopia $Acoes -Trocar:$TrocarChaveDaCopia } catch {
        return @{ codigo = 1; erro = $_.Exception.Message }
    }
    @{ codigo = 0; erro = $null }
}

function Invoke-EtapaChaveCopia {
    $acoes = New-Object System.Collections.Generic.List[string]
    $r = Invoke-EtapaChaveCopiaInterna $acoes
    if ($RegistroEtapa) {
        $registro = [ordered]@{ etapa = 'chave-da-copia'; destino = $AncoraChaveCopia; codigo = $r.codigo; erro = $r.erro
                                acoes = $acoes.ToArray(); fim = (Get-Date).ToString('o') }
        try { [IO.File]::WriteAllText($RegistroEtapa, (ConvertTo-Json -InputObject $registro -Depth 4), (New-Object System.Text.UTF8Encoding($false))) } catch { }
    }
    foreach ($a in $acoes) { Write-Host "  $a" }
    if ($r.erro) { Write-Host "Etapa da chave da cópia NÃO concluída: $($r.erro)" }
    [int]$r.codigo
}

function Invoke-EtapaAdministrador {
    # A etapa como administrador, num UAC só (I11): a âncora (-EtapaAncora) e a cópia protegida da ferramenta do
    # titular (-EtapaFerramenta). Só a âncora: a etapa de sempre, com o mesmo registro.
    if (-not $EtapaFerramenta) { return (Invoke-EtapaAncora) }
    $registro = [ordered]@{ etapa = 'administrador'; codigo = 0; fim = $null }
    $codigo = 0
    if ($EtapaAncora) {
        $acoes = New-Object System.Collections.Generic.List[string]
        $r = Invoke-EtapaAncoraInterna $acoes
        $registro.ancora = [ordered]@{ ancora = $Ancora; titular = $Titular; codigo = $r.codigo; erro = $r.erro; acoes = $acoes.ToArray() }
        foreach ($a in $acoes) { Write-Host "  $a" }
        if ($r.erro) { Write-Host "Etapa da âncora NÃO concluída: $($r.erro)" }
        $codigo = [int]$r.codigo
    }
    $acoesF = New-Object System.Collections.Generic.List[string]
    $rf = Invoke-EtapaFerramentaInterna $acoesF
    $registro.ferramenta = [ordered]@{ ferramentas = $Ferramentas; codigo = $rf.codigo; erro = $rf.erro; acoes = $acoesF.ToArray() }
    foreach ($a in $acoesF) { Write-Host "  $a" }
    if ($rf.erro) { Write-Host "Etapa da cópia da ferramenta do titular NÃO concluída: $($rf.erro)" }
    if ($codigo -eq 0) { $codigo = [int]$rf.codigo }
    $registro.codigo = $codigo
    $registro.fim = (Get-Date).ToString('o')
    if ($RegistroEtapa) {
        try { [IO.File]::WriteAllText($RegistroEtapa, (ConvertTo-Json -InputObject $registro -Depth 5), (New-Object System.Text.UTF8Encoding($false))) } catch { }
    }
    $codigo
}

# ------------------------------------------------------------------ arquivos em <raiz>\.claude
function Get-ComandosDosHooks([string] $Perfil) {
    # Só leitura, para o relatório: os comandos dos hooks de um perfil existente.
    if (-not (Test-Path -LiteralPath $Perfil -PathType Leaf)) { return @() }
    try {
        $j = [IO.File]::ReadAllText($Perfil) | Microsoft.PowerShell.Utility\ConvertFrom-Json
        @(foreach ($g in @($j.hooks.PreToolUse)) { foreach ($h in @($g.hooks)) { [string]$h.command } }) |
            Where-Object { $_ } | Select-Object -Unique
    } catch { @() }
}

function Set-ArquivoGerado {
    # Igual = nada muda; diferente = cópia do atual em .claude\anteriores\<data> antes de trocar.
    param([string] $Id, [string] $Destino, [byte[]] $Bytes, [string] $Anteriores, [string] $Relativo, [bool] $Sim)
    $item = [ordered]@{ id = $Id; caminho = $Destino; exige_admin = $false; acao = $null; sha256 = (Get-Sha256Bytes $Bytes)
                        anterior = $null; detalhe = $null }
    if (Test-Path -LiteralPath $Destino -PathType Leaf) {
        if ((Get-Sha256Arquivo $Destino) -eq $item.sha256) { $item.acao = 'igual'; return [pscustomobject]$item }
        $item.acao = 'atualizar'
        $item.anterior = Join-Path $Anteriores $Relativo
    } else {
        $item.acao = 'criar'
    }
    if (-not $Sim) {
        if ($item.anterior) {
            New-Item -ItemType Directory -Force -Path (Split-Path -Parent $item.anterior) | Out-Null
            Copy-Item -LiteralPath $Destino -Destination $item.anterior
        }
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Destino) | Out-Null
        $novo = $Destino + '.novo'
        [IO.File]::WriteAllBytes($novo, $Bytes)
        Move-Item -LiteralPath $novo -Destination $Destino -Force
    }
    [pscustomobject]$item
}

# ------------------------------------------------------------------ relatório
function Get-VersaoSkill {
    $md = Join-Path $SKILL 'SKILL.md'
    if (Test-Path -LiteralPath $md -PathType Leaf) {
        $m = [regex]::Match([IO.File]::ReadAllText($md), 'version:\s*"([^"]+)"')
        if ($m.Success) { return $m.Groups[1].Value }
    }
    $null
}

function Get-Campo($Objeto, [string] $Nome) {
    $p = $Objeto.PSObject.Properties[$Nome]
    if ($p) { return $p.Value }
    $null
}

function Write-Resumo($Rel) {
    $titulo = 'Fundação de IA: preparo desta máquina (Windows)'
    if ($Rel.simulacao) { $titulo += '   [SIMULAÇÃO: nada foi alterado]' }
    Write-Host $titulo
    Write-Host ('Raiz: ' + $Rel.raiz)
    foreach ($i in @($Rel.itens)) {
        $linha = '  [' + $i.acao + '] ' + $i.id + '  ' + $i.caminho
        if ($i.exige_admin -and $i.acao -ne 'igual') { $linha += '   (exige administrador)' }
        Write-Host $linha
        foreach ($campo in @('detalhe', 'anterior')) {
            $v = Get-Campo $i $campo
            if ($v) { Write-Host ('      ' + $(if ($campo -eq 'anterior') { 'cópia do anterior: ' } else { '' }) + $v) }
        }
        $fp = Get-Campo $i 'impressao_digital'
        if ($fp) { Write-Host ('      Impressão digital: ' + $fp + '   (compare com a sua anotação, fora do computador)') }
        $h = Get-Campo $i 'sha256'
        if ($h) { Write-Host ('      SHA-256: ' + $h) }
    }
    foreach ($p in @($Rel.pendencias)) { Write-Host ('Pendente: ' + $p) }
    if ($Rel.comando_pronto) {
        Write-Host (Get-TituloDoComandoPronto $Rel.pasta_sugerida)
        Write-Host ('  ' + $Rel.comando_pronto)
    }
    Write-Host ('Resultado (código ' + $Rel.codigo + '): ' + $Rel.mensagem)
}

function Complete-Preparo($Rel, [int] $Codigo, [string] $Mensagem, [bool] $Sim, [string] $Carimbo) {
    $Rel.codigo = $Codigo
    $Rel.mensagem = $Mensagem
    $Rel.fim = (Get-Date).ToString('o')
    # 'pendente' (a cópia protegida sem Python para todos os usuários, I11) é passo do titular: não é nada a fazer aqui.
    $Rel.nada_a_fazer = ($Codigo -eq 0 -and @($Rel.itens | Where-Object { @('igual', 'pendente') -notcontains $_.acao }).Count -eq 0)
    $destino = $Relatorio
    if (-not $destino -and -not $Sim -and $Codigo -ne 2) {
        $destino = Join-Path $Raiz ('evidence\host\preparar-maquina-' + $Carimbo + '.json')
    }
    if ($destino) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $destino) | Out-Null
        [IO.File]::WriteAllText($destino, (ConvertTo-Json -InputObject $Rel -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
    }
    Write-Resumo $Rel
    if ($destino) { Write-Host ('Relatório: ' + $destino) }
    $Codigo
}

# ------------------------------------------------------------------ principal
function Invoke-Preparo {
    $sim = [bool]$Simular -or [bool]$WhatIfPreference
    $carimbo = Get-Date -Format 'yyyyMMddTHHmmss'
    $rel = [ordered]@{ script = 'preparar-maquina.ps1'; versao_skill = (Get-VersaoSkill); simulacao = $sim
        inicio = (Get-Date).ToString('o'); raiz = $Raiz; titular = $Titular; projeto = $Projeto
        backups = @(); backups_ausentes = @(); sem_backups = [bool]$SemBackups; ultima_copia = $null
        comando_pronto = $null; pasta_sugerida = $null; negacoes_fora_do_registro = $null
        itens = (New-Object System.Collections.ArrayList); pendencias = (New-Object System.Collections.ArrayList)
        nada_a_fazer = $false; codigo = $null; mensagem = $null }
    # Revisão de segurança da 1.7.10, CI-F1: este script não roda de dentro de <raiz>\projects\ (uma cópia da skill que
    # a sessão guardou ou mostrou num checklist): no modo real, de projects\ de qualquer fundação; na simulação, contra
    # a fundação que o contém. Antes de tudo: nada é lido nem gravado.
    $fundacaoDoScript = Get-FundacaoQueContem $PSScriptRoot
    if ($fundacaoDoScript -and (-not $sim -or (Test-MesmaPasta $fundacaoDoScript $Raiz))) {
        return (Complete-Preparo $rel 2 (Get-RecusaDeProjects $fundacaoDoScript 'preparar-maquina.ps1') $sim $carimbo)
    }
    if (-not $Raiz -or -not $Titular) { return (Complete-Preparo $rel 2 'informe -Raiz e -Titular' $sim $carimbo) }
    if (-not ($Titular -cmatch $IDENTIFICADOR)) {
        return (Complete-Preparo $rel 2 "titular inválido: $Titular (letras minúsculas, dígitos, '.', '_' ou '-')" $sim $carimbo)
    }
    if ($Projeto -and (-not ($Projeto -cmatch $ID_PROJETO) -or $Projeto -like '*--*')) {
        return (Complete-Preparo $rel 2 "projeto inválido: $Projeto (1 a 40 letras minúsculas, dígitos ou -, sem - nas pontas nem --)" $sim $carimbo)
    }
    if (-not (Test-Path -LiteralPath $Raiz -PathType Container)) { return (Complete-Preparo $rel 2 "a raiz não existe: $Raiz" $sim $carimbo) }
    $script:Raiz = (Microsoft.PowerShell.Management\Resolve-Path -LiteralPath $Raiz).Path.TrimEnd($BARRA)
    $rel.raiz = $Raiz
    if ([IO.Path]::GetPathRoot($Raiz + $BARRA).TrimEnd($BARRA) -eq $Raiz) {
        return (Complete-Preparo $rel 2 "a raiz da fundação não pode ser a raiz de um disco: $Raiz" $sim $carimbo)
    }
    if (-not @('registry', 'fundacao', 'RETOMADA.md' | Where-Object { Test-Path -LiteralPath (Join-Path $Raiz $_) })) {
        return (Complete-Preparo $rel 2 "não parece a raiz de uma fundação (sem registry, fundacao nem RETOMADA.md): $Raiz" $sim $carimbo)
    }
    if ($Projeto -and -not (Test-Path -LiteralPath (Join-Path $Raiz ('projects' + $BARRA + $Projeto)) -PathType Container)) {
        return (Complete-Preparo $rel 2 "o projeto $Projeto não existe em $Raiz" $sim $carimbo)
    }
    if (Test-Elevado) {
        return (Complete-Preparo $rel 2 "rode no PowerShell comum, sem 'Executar como administrador': o script pede o UAC só para a âncora e confere a âncora com a sua conta comum" $sim $carimbo)
    }
    $problema = Test-CaminhoAncora $Ancora
    if ($problema) { return (Complete-Preparo $rel 2 $problema $sim $carimbo) }
    $planoChave = $null  # 1.7.11: a chave pública da cópia cifrada, conferida antes da chave, do UAC e de qualquer gravação
    if ($ChaveDaCopia) {
        $problema = Test-CaminhoAncora $AncoraChaveCopia
        if ($problema) { return (Complete-Preparo $rel 2 ($problema -replace 'a âncora', 'a chave da cópia') $sim $carimbo) }
        $planoChave = Get-PlanoChaveCopia $ChaveDaCopia
        if ($planoChave.erro) { return (Complete-Preparo $rel 2 ('-ChaveDaCopia: ' + $planoChave.erro + ': nada foi alterado') $sim $carimbo) }
    }
    $ssh = Get-SshKeygen
    if (-not $ssh) {
        return (Complete-Preparo $rel 2 'falta o Cliente OpenSSH do Windows (Configurações > Sistema > Recursos opcionais > Cliente OpenSSH)' $sim $carimbo)
    }
    # O interpretador sai de -Python ou das instalações registradas e do PATH, conferido antes de rodar; nunca do
    # .claude\settings.json existente, que este preparo refaz [auditoria Codex Security da 1.7.6, #3].
    $interp = Find-Python $Python
    if (-not $interp -or -not $interp.Caminho -or @($interp.Motivos).Count -gt 0) {
        $rel.python_conferencia = $interp
        if ($Python) { $msg = 'o python.exe de -Python não serve: ' + (@($interp.Motivos) -join '; ') }
        elseif ($interp) { $msg = 'nenhum Python confiável nas instalações registradas nem no PATH (o perfil atual não conta): ' + (@($interp.Motivos) -join ' | ') }
        else { $msg = 'Python não encontrado nas instalações registradas nem no PATH (o perfil atual não conta)' }
        return (Complete-Preparo $rel 2 ($msg + '. Informe -Python com o python.exe do instalador oficial (python.org), assinado pela Python Software Foundation') $sim $carimbo)
    }
    $py = $interp.Caminho
    $faltam = @(@($HOOKS | ForEach-Object { Join-Path $SKILL ('assets\hooks\' + $_) }) + $AJUDANTE |
                Where-Object { -not (Test-Path -LiteralPath $_ -PathType Leaf) })
    if ($faltam.Count -gt 0) { return (Complete-Preparo $rel 2 ('arquivos da skill ausentes: ' + ($faltam -join ', ')) $sim $carimbo) }
    $rel.python = $py
    $rel.python_conferencia = [ordered]@{ origem = $interp.Origem; assinante = $interp.Assinante; sha256 = $interp.Sha256
                                          versao = $interp.Versao; certificado_thumbprint = $interp.CertificadoThumbprint
                                          avisos = @($interp.Avisos) }

    # 0. Plano, antes da chave, do UAC e de qualquer gravação (1.7.10; DESENHO §4): as pastas informadas, o projeto das
    # sessões do Windows e todas as saídas do ajudante. Antes, a troca de projeto era recusada só no fim, com hooks e
    # perfis já regravados: a máquina ficava meio trocada (mapa do Windows, 7 vezes entre 27 e 31/10/2026).
    $claude = Join-Path $Raiz '.claude'
    $leitura = Get-PastasConferidas -Valores $SomenteLeitura -Rotulo '-SomenteLeitura'
    if ($leitura.Erro) { return (Complete-Preparo $rel 2 ($leitura.Erro + ': nada foi alterado') $sim $carimbo) }
    # As registradas que não existem agora seguem negadas: uma origem não volta a ser gravável quando o disco voltar
    # (reconferência do lote 2: uma pasta sumida de um projeto parava o preparo de todos).
    $ausentes = Get-PastasConferidas -Valores $SomenteLeituraAusente -Rotulo '-SomenteLeituraAusente' -AceitarAusente
    if ($ausentes.Erro) { return (Complete-Preparo $rel 2 ($ausentes.Erro + ': nada foi alterado') $sim $carimbo) }
    $rel['somente_leitura_ausente'] = @($ausentes.Lista)
    $copias = Get-PastasConferidas -Valores $Backups -Rotulo '-Backups' -SeAusente ('; com o disco das cópias desligado agora, use -BackupsAusente com a mesma pasta (a negação vale quando ele voltar)')
    if ($copias.Erro) { return (Complete-Preparo $rel 2 ($copias.Erro + ': nada foi alterado') $sim $carimbo) }
    $copiasAusentes = Get-PastasConferidas -Valores $BackupsAusente -Rotulo '-BackupsAusente' -AceitarAusente
    if ($copiasAusentes.Erro) { return (Complete-Preparo $rel 2 ($copiasAusentes.Erro + ': nada foi alterado') $sim $carimbo) }
    # O portão da I21 (b) também aqui (revisão da terceira rodada da integração, defeitos 1 e 2): este script refaz
    # inteiro o .claude\settings.json, só com o que recebe, e rodado sozinho sem -Backups (a folha o manda rodar por
    # último; a I22 o pede de novo a toda instalação da 1.7.10) tirava em silêncio o Read e o Edit negados das cópias,
    # que têm os dados de todos os projetos. Decide pelas listas conferidas (-Backups ' ' não é cópia) e pelo registro da
    # última cópia (com cópia registrada, -SemBackups não vale: revisão seguinte, defeito 2), ainda no plano: antes da
    # chave, do UAC e de qualquer gravação, também na simulação; as etapas de administrador não passam aqui.
    $rel.backups = @($copias.Lista)
    $rel.backups_ausentes = @($copiasAusentes.Lista)
    $rel.ultima_copia = Get-UltimaCopia $py
    $portao = Get-PortaoDasCopias -Copias $copias.Lista -Ausentes $copiasAusentes.Lista -SemBackups ([bool]$SemBackups) `
        -Ultima $rel.ultima_copia -Script $PSCommandPath -Dados $PARAMETROS_DADOS -Excluir @('EtapaAncora', 'ChavePublica',
        'ImpressaoEsperada', 'RegistroEtapa', 'EtapaFerramenta', 'PlanoFerramenta', 'FerramentaEsperada',
        'EtapaChaveCopia', 'ChaveDaCopiaEsperada')
    $rel.comando_pronto = $portao.ComandoPronto
    $rel.pasta_sugerida = $portao.PastaSugerida
    if ($portao.Codigo -ne 0) { return (Complete-Preparo $rel $portao.Codigo $portao.Mensagem $sim $carimbo) }
    if ($SemBackups) {
        [void]$rel.pendencias.Add('cópias de segurança: com -SemBackups, o perfil das sessões do Windows sai sem o Read e o Edit negados delas, que têm os dados de todos os projetos; quando houver cópias, rode este script de novo com -Backups')
    }
    foreach ($pendencia in @($portao.Pendencias)) { [void]$rel.pendencias.Add($pendencia) }
    $registrado = Get-ProjetoRegistrado $claude
    $anterior = $null
    if ($registrado -and (Test-Path -LiteralPath (Join-Path $Raiz ('projects' + $BARRA + $registrado.Projeto)) -PathType Container)) {
        $anterior = $registrado.Projeto
    }
    $projetoSessoes = $anterior
    if ($Projeto) { $projetoSessoes = $Projeto }
    $itemProjeto = [ordered]@{ id = 'projeto'; caminho = (Join-Path $claude 'settings.json'); exige_admin = $false
                               acao = 'igual'; projeto = $projetoSessoes; projeto_anterior = $anterior; anterior = $null
                               detalhe = $null }
    if ($Projeto -and $anterior -and $anterior -cne $Projeto) {
        if (-not $TrocarProjeto) {
            $itemProjeto.acao = 'conflito'
            $itemProjeto.detalhe = "as sessões do Windows são do projeto $anterior (em .claude\$($registrado.Origem)); para trocá-las de propósito para $Projeto, rode de novo com -TrocarProjeto (o perfil anterior fica em .claude\anteriores). Para só preparar a sessão do Ubuntu de outro projeto, sem mexer nas sessões do Windows, rode o preparar-projeto.ps1 sem -ProjetoWindows (ou este script sem -Projeto)"
            [void]$rel.itens.Add([pscustomobject]$itemProjeto)
            return (Complete-Preparo $rel 1 'troca do projeto das sessões do Windows sem -TrocarProjeto: nada foi gravado' $sim $carimbo)
        }
        $itemProjeto.acao = 'trocar'
        $itemProjeto.detalhe = "projeto das sessões do Windows: $anterior -> $Projeto"
    } elseif ($Projeto -and -not $anterior) {
        $itemProjeto.acao = 'criar'
    } elseif (-not $projetoSessoes) {
        $itemProjeto.acao = 'ausente'
        $itemProjeto.detalhe = 'sem -Projeto: as sessões do Windows não gravam nem leem projeto nenhum (rode com -Projeto <id>)'
    }
    $negar = @()  # -File entrega "a,b" como um texto só: os nomes vão separados por vírgula
    foreach ($s in @($NegarSkill)) { foreach ($n in ($s -split ',')) { if ($n.Trim()) { $negar += @('--negar-skill', $n.Trim()) } } }
    foreach ($s in @($NegarAgente)) { foreach ($n in ($s -split ',')) { if ($n.Trim()) { $negar += @('--negar-agente', $n.Trim()) } } }
    $argsPerfil = @('perfil-windows', '--raiz', $Raiz, '--python', $py) + $negar
    if ($projetoSessoes) { $argsPerfil += @('--projeto', $projetoSessoes) }
    foreach ($d in @(@($leitura.Lista) + @($ausentes.Lista))) { $argsPerfil += @('--somente-leitura', $d) }
    foreach ($d in @(@($copias.Lista) + @($copiasAusentes.Lista))) { $argsPerfil += @('--backups', $d) }
    $rPerfil = Invoke-Ajudante $py $argsPerfil
    if ($rPerfil.Codigo -ne 0) {
        [void]$rel.itens.Add([pscustomobject][ordered]@{ id = 'settings.json'; caminho = (Join-Path $claude 'settings.json')
            exige_admin = $false; acao = 'erro'; sha256 = $null; anterior = $null
            detalhe = ('o gerador de perfis recusou: ' + ($rPerfil.Saida + $rPerfil.Erro).Trim()) })
        return (Complete-Preparo $rel 1 'o gerador de perfis recusou: nada foi gravado' $sim $carimbo)
    }
    # As negações que só a linha de comando trouxe (revisão seguinte da terceira rodada da integração, defeito 3): o
    # preparar-projeto.ps1 refaz o perfil só com o registry\projetos-host.json, e uma pasta de -SomenteLeitura ou um nome
    # de -NegarSkill fora dele sumiria em silêncio no próximo preparo de qualquer projeto. O ajudante diz quais o
    # registro não cobre; a pendência vai ao relatório e à tela. Sem nenhuma dessas negações, não há o que conferir.
    $dadasNaLinha = @(@(@($leitura.Lista) + @($ausentes.Lista)) | ForEach-Object { '--somente-leitura'; $_ }) + $negar
    $rFora = [pscustomobject]@{ Codigo = 0; Saida = '{"somente_leitura": [], "negar_skill": [], "negar_agente": []}'; Erro = '' }
    if ($dadasNaLinha.Count -gt 0) { $rFora = Invoke-Ajudante $py (@('fora-do-registro', '--raiz', $Raiz) + $dadasNaLinha) }
    $soDaLinha = @()
    if ($rFora.Codigo -eq 0) {
        try {
            $fora = $rFora.Saida | Microsoft.PowerShell.Utility\ConvertFrom-Json
            $rel.negacoes_fora_do_registro = [ordered]@{ somente_leitura = @($fora.somente_leitura); negar_skill = @($fora.negar_skill); negar_agente = @($fora.negar_agente) }
            $soDaLinha = @(@($fora.somente_leitura | ForEach-Object { '-SomenteLeitura ' + $_ }) +
                           @($fora.negar_skill | ForEach-Object { '-NegarSkill ' + $_ }) +
                           @($fora.negar_agente | ForEach-Object { '-NegarAgente ' + $_ }))
        } catch { $soDaLinha = @('(não conferidas: resposta do ajudante fora da forma)') }
    } else {
        $soDaLinha = @('(não conferidas: ' + ($rFora.Saida + $rFora.Erro).Trim() + ')')
    }
    if ($soDaLinha.Count -gt 0) {
        [void]$rel.pendencias.Add('estas negações vêm só da linha de comando, fora do registry\projetos-host.json: ' +
            ($soDaLinha -join '; ') + '. O próximo preparar-projeto.ps1, de qualquer projeto, refaz o perfil sem elas: ' +
            'registre-as no projeto delas com preparo_host.py registrar-projeto (--somente-leitura <pasta> ou ' +
            '--negar-skill <nome> ou --negar-agente <nome>, com uma --origem do projeto) ou rode este script por último')
    }
    # Identidade das sessões: só acrescenta; outra identidade já gravada é decisão do titular (conflito). O projeto sai
    # do settings.local.json (vai ao env do settings.json; um FUNDACAO_PROJECT no local passaria por cima dele). Com
    # -Projeto, fica só a identidade (--estrito; o anterior vai para .claude\anteriores) [auditoria Codex Security, #5].
    $local = Join-Path $claude 'settings.local.json'
    $argsLocal = @('identidade', '--titular', $Titular, '--sem-projeto')
    if (Test-Path -LiteralPath $local -PathType Leaf) { $argsLocal += @('--atual', $local) }
    if ($Projeto) { $argsLocal += '--estrito' }
    $rLocal = Invoke-Ajudante $py $argsLocal
    if ($rLocal.Codigo -ne 0) {
        $acaoLocal = 'erro'
        if ($rLocal.Codigo -eq 1) { $acaoLocal = 'conflito' }
        [void]$rel.itens.Add([pscustomobject][ordered]@{ id = 'settings.local.json'; caminho = $local; exige_admin = $false
            acao = $acaoLocal; sha256 = (Get-Sha256Arquivo $local); anterior = $null; detalhe = ($rLocal.Saida + $rLocal.Erro).Trim() })
        return (Complete-Preparo $rel 1 'a identidade do settings.local.json não confere: nada foi gravado' $sim $carimbo)
    }
    [void]$rel.itens.Add([pscustomobject]$itemProjeto)

    # 1. Chave do titular
    $pub = $Chave + '.pub'
    $linhaPublica = $null
    $item = [ordered]@{ id = 'chave'; caminho = $Chave; exige_admin = $false; acao = $null; estado_da_senha = 'nao_conferida'
                        impressao_digital = $null; sha256 = $null; anterior = $null; detalhe = $null }
    if (Test-Path -LiteralPath $Chave -PathType Leaf) {
        if (-not (Test-Path -LiteralPath $pub -PathType Leaf)) {
            $item.acao = 'erro'
            $item.detalhe = "falta a chave pública $pub; recrie-a no seu terminal com: ssh-keygen -y -f `"$Chave`" > `"$pub`""
            [void]$rel.itens.Add([pscustomobject]$item)
            return (Complete-Preparo $rel 1 'chave pública ausente' $sim $carimbo)
        }
        $item.acao = 'igual'
    } elseif ($sim) {
        $item.acao = 'criar'
        $item.detalhe = 'será gerada pelo ssh-keygen do sistema (ed25519); você digita a senha no seu terminal e o script não a vê'
    } elseif ([Console]::IsInputRedirected -or ([Environment]::GetCommandLineArgs() -match '^-noni')) {
        # Sem console interativo o ssh-keygen espera a senha para sempre (08/11: teste parado 4h36): recusa antes dele.
        $item.acao = 'erro'
        $item.detalhe = "a chave não existe e este processo não tem console interativo para você digitar a senha; no seu terminal, rode: ssh-keygen -t ed25519 -a 100 -f `"$Chave`" e depois rode este script de novo"
        [void]$rel.itens.Add([pscustomobject]$item)
        return (Complete-Preparo $rel 1 'chave ausente e sem console interativo: nada foi gerado' $sim $carimbo)
    } else {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Chave) | Out-Null
        Write-Host 'Gerando a chave das suas decisões. Digite uma senha só sua, duas vezes (ela não aparece na tela).'
        Write-Host 'Guarde a senha fora do computador: sem ela, as decisões não podem ser assinadas.'
        & $ssh -t ed25519 -a 100 -C ($Titular + '-decisoes-fundacao') -f $Chave
        if ($LASTEXITCODE -ne 0 -or -not (Test-Path -LiteralPath $pub -PathType Leaf)) {
            $item.acao = 'erro'
            $item.detalhe = "o ssh-keygen não gerou a chave (código $LASTEXITCODE)"
            [void]$rel.itens.Add([pscustomobject]$item)
            return (Complete-Preparo $rel 1 'chave não gerada' $sim $carimbo)
        }
        $item.acao = 'criar'
    }
    if (Test-Path -LiteralPath $pub -PathType Leaf) {
        $linhaPublica = ([IO.File]::ReadAllText($pub)).Trim()
        $item.impressao_digital = Get-ImpressaoDigital $linhaPublica
        $item.sha256 = Get-Sha256Arquivo $pub
    }
    if (-not $sim -and (Test-Path -LiteralPath $Chave -PathType Leaf)) {
        # Confere só que a chave NÃO abre sem senha (-P vazio); a senha verdadeira nunca passa por aqui.
        $r = Invoke-Nativo -Exe $ssh -Argumentos @('-y', '-P', '', '-f', $Chave)
        if ($r.Codigo -eq 0) {
            $item.estado_da_senha = 'ausente'
            $item.detalhe = "a chave abre sem senha: defina uma no seu terminal com ssh-keygen -p -f `"$Chave`" e rode de novo"
            [void]$rel.itens.Add([pscustomobject]$item)
            return (Complete-Preparo $rel 1 'chave sem senha: nada foi alterado' $sim $carimbo)
        }
        if (($r.Erro + $r.Saida) -notmatch 'passphrase') {
            $item.acao = 'erro'
            $item.detalhe = 'não consegui conferir a chave: ' + ($r.Erro + $r.Saida).Trim()
            [void]$rel.itens.Add([pscustomobject]$item)
            return (Complete-Preparo $rel 1 'chave ilegível' $sim $carimbo)
        }
        $item.estado_da_senha = 'presente'
    }
    [void]$rel.itens.Add([pscustomobject]$item)

    # 2b, planejada antes do UAC: a cópia protegida da ferramenta do titular (folha da integração, I11), gravada no
    # mesmo UAC da âncora (ou num só dela, se a âncora não precisar). Python por usuário: pendente, sem UAC.
    $itemF = Get-ItemFerramenta $py
    $argsFerramenta = @()
    $planoArq = $null
    if (-not $sim -and -not $SemUAC -and @('criar', 'atualizar') -contains $itemF.acao) {
        $planoArq = Join-Path $env:TEMP ('fundacao-plano-ferramenta-' + $carimbo + '.json')
        [IO.File]::WriteAllBytes($planoArq, $itemF.plano.bytes)
        $argsFerramenta = @('-EtapaFerramenta', '-Ferramentas', $Ferramentas, '-PlanoFerramenta', $planoArq,
                            '-FerramentaEsperada', $itemF.sha256)
    }
    $codigoFerramenta = $null

    # 2. Âncora (a única etapa com administrador, com a cópia protegida acima)
    $item = [ordered]@{ id = 'ancora'; caminho = $Ancora; exige_admin = $true; acao = $null; protegida = $false
                        conteudo_confere = $false; sha256 = $null; anterior = $null; detalhe = $null; sondagem = $null }
    $sond = Get-SondagemAncora $Ancora
    $item.sondagem = $sond
    $item.protegida = $sond.protegida
    $item.sha256 = Get-Sha256Arquivo $Ancora
    $fp = $null
    $mescla = $null
    if ($linhaPublica) {
        $fp = Get-ImpressaoDigital $linhaPublica
        $atuais = @()
        if ($sond.existe) { $atuais = @([IO.File]::ReadAllLines($Ancora)) }
        $mescla = Merge-Ancora -Linhas $atuais -Titular $Titular -LinhaNova (Get-LinhaAncora $Titular $linhaPublica) -Trocar:$TrocarChave
        $item.conteudo_confere = ($mescla.Acao -eq 'igual')
    }
    $precisa = 'atualizar'
    if (-not $sond.existe) { $precisa = 'criar' }
    if ($mescla -and $mescla.Acao -eq 'conflito') {
        $item.acao = 'conflito'
        $item.detalhe = "a âncora já tem outra chave para $Titular. Se você trocou de chave de propósito, rode de novo com -TrocarChave (a linha anterior fica numa cópia ao lado)"
    } elseif ($sond.protegida -and $item.conteudo_confere) {
        $item.acao = 'igual'
    } else {
        $item.detalhe = 'exige administrador: o Windows pede confirmação (UAC) e só esta etapa roda como administrador. ' +
            (@($sond.motivos) -join '; ')
        if ($mescla -and $mescla.Acao -eq 'namespaces') {
            $item.detalhe += ' Acrescenta à linha da sua chave os namespaces que faltam entre fundacao-decisao, fundacao-abertura (a ficha de aberturas da 1.7.10) e fundacao-copia (o livro de cópias assinado); a chave não muda.'
        }
        if ($sim) {
            $item.acao = $precisa
        } elseif ($SemUAC) {
            $item.acao = 'pendente_admin'
            [void]$rel.pendencias.Add('âncora: rode de novo sem -SemUAC e confirme o UAC')
        } else {
            Write-Host ''
            Write-Host ('Confira a impressão digital da sua chave: ' + $fp)
            Write-Host 'Ela precisa ser igual à que você anotou fora do computador. O Windows vai pedir confirmação de administrador agora.'
            $registro = Join-Path $env:TEMP ('fundacao-etapa-ancora-' + $carimbo + '.json')
            $argumentos = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-EtapaAncora', '-Ancora', $Ancora,
                            '-Titular', $Titular, '-ChavePublica', $pub, '-ImpressaoEsperada', $fp, '-RegistroEtapa', $registro)
            if ($TrocarChave) { $argumentos += '-TrocarChave' }
            $comFerramenta = ($argsFerramenta.Count -gt 0)
            $argumentos += $argsFerramenta  # o mesmo UAC grava a cópia protegida da ferramenta do titular (I11)
            $argsFerramenta = @()
            $codigoEtapa = $null
            try {
                # Revisão de segurança da 1.7.10, CI-F3: o powershell.exe da pasta do sistema (não o deste processo, que
                # pode ser outro), com -NoProfile e -ExecutionPolicy Bypass, pelo Start-Process qualificado.
                $proc = Microsoft.PowerShell.Management\Start-Process -FilePath (Get-ProgramaDoSistema $POWERSHELL_DO_SISTEMA) `
                    -Verb RunAs -Wait -PassThru -ArgumentList ((@($argumentos) | ForEach-Object { ConvertTo-ArgumentoNativo $_ }) -join ' ')
                $codigoEtapa = $proc.ExitCode
            } catch {
                $item.acao = 'pendente_admin'
                $item.detalhe = 'a confirmação de administrador (UAC) não foi dada: nada mudou na âncora'
                [void]$rel.pendencias.Add('âncora: rode de novo e confirme o UAC')
                if ($comFerramenta) {
                    $itemF.acao = 'pendente_admin'
                    $itemF.detalhe = 'a confirmação de administrador (UAC) não foi dada: a cópia protegida não foi gravada'
                    [void]$rel.pendencias.Add('cópia protegida da ferramenta do titular: rode de novo e confirme o UAC')
                }
            }
            if ($null -ne $codigoEtapa) {
                $etapa = $null
                if (Test-Path -LiteralPath $registro -PathType Leaf) {
                    try { $etapa = [IO.File]::ReadAllText($registro) | Microsoft.PowerShell.Utility\ConvertFrom-Json; $item.etapa_administrador = $etapa } catch { }
                }
                if ($comFerramenta) {  # no registro conjunto, o código de cada etapa (I11)
                    $parteAncora = $null
                    $parteFerramenta = $null
                    if ($etapa) { $parteAncora = Get-Campo $etapa 'ancora'; $parteFerramenta = Get-Campo $etapa 'ferramenta' }
                    $codigoEtapa = -1
                    if ($parteAncora) { $codigoEtapa = [int](Get-Campo $parteAncora 'codigo') }
                    $codigoFerramenta = -1
                    if ($parteFerramenta) { $codigoFerramenta = [int](Get-Campo $parteFerramenta 'codigo'); $itemF.etapa_administrador = $parteFerramenta }
                }
                # A conferência é desta conta, sem elevação: só ela mostra o que o executor consegue fazer.
                $depois = Get-SondagemAncora $Ancora
                $confere = $false
                if ($depois.existe) {
                    $m2 = Merge-Ancora -Linhas @([IO.File]::ReadAllLines($Ancora)) -Titular $Titular -LinhaNova (Get-LinhaAncora $Titular $linhaPublica)
                    $confere = ($m2.Acao -eq 'igual')
                }
                $item.sondagem = $depois
                $item.protegida = $depois.protegida
                $item.conteudo_confere = $confere
                $item.sha256 = Get-Sha256Arquivo $Ancora
                if ($codigoEtapa -eq 0 -and $depois.protegida -and $confere) {
                    $item.acao = $precisa
                    $item.detalhe = 'feito como administrador e conferido por esta conta: ela não altera a âncora'
                } else {
                    $item.acao = 'erro'
                    $item.detalhe = "a etapa de administrador terminou com código $codigoEtapa; protegida: $($depois.protegida); linha confere: ${confere}. " +
                        (@($depois.motivos) -join '; ')
                }
            }
        }
    }
    [void]$rel.itens.Add([pscustomobject]$item)

    # 2b. A cópia protegida da ferramenta do titular, num UAC só dela se a âncora não pediu o seu (I11); conferida
    # depois por esta conta, sem elevação, como a âncora.
    if ($argsFerramenta.Count -gt 0) {
        Write-Host 'O Windows vai pedir confirmação de administrador para gravar a cópia protegida da ferramenta do titular.'
        $registroF = Join-Path $env:TEMP ('fundacao-etapa-ferramenta-' + $carimbo + '.json')
        $argumentos = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath) + $argsFerramenta + @('-RegistroEtapa', $registroF)
        try {
            $proc = Microsoft.PowerShell.Management\Start-Process -FilePath (Get-ProgramaDoSistema $POWERSHELL_DO_SISTEMA) `
                -Verb RunAs -Wait -PassThru -ArgumentList ((@($argumentos) | ForEach-Object { ConvertTo-ArgumentoNativo $_ }) -join ' ')
            $codigoFerramenta = $proc.ExitCode
            if (Test-Path -LiteralPath $registroF -PathType Leaf) {
                try {
                    $parte = Get-Campo ([IO.File]::ReadAllText($registroF) | Microsoft.PowerShell.Utility\ConvertFrom-Json) 'ferramenta'
                    if ($parte) { $itemF.etapa_administrador = $parte; $codigoFerramenta = [int](Get-Campo $parte 'codigo') }
                } catch { }
            }
        } catch {
            $itemF.acao = 'pendente_admin'
            $itemF.detalhe = 'a confirmação de administrador (UAC) não foi dada: a cópia protegida não foi gravada'
            [void]$rel.pendencias.Add('cópia protegida da ferramenta do titular: rode de novo e confirme o UAC')
        }
    }
    if ($null -ne $codigoFerramenta) {
        $depoisF = Get-EstadoFerramenta $itemF.plano.bytes $itemF.plano.arquivos $itemF.caminho
        $itemF.sondagem = $depoisF
        $itemF.protegida = $depoisF.protegida
        if ($codigoFerramenta -eq 0 -and $depoisF.igual -and $depoisF.protegida) {
            $itemF.detalhe = 'feita como administrador e conferida por esta conta: ela não altera a cópia; a ficha de aberturas ' +
                'é assinada pela forma do Windows que o kit mostra (executar_windows)'
        } else {
            $itemF.acao = 'erro'
            $itemF.detalhe = "a etapa de administrador da cópia terminou com código $codigoFerramenta; igual ao plano: " +
                "$($depoisF.igual); protegida: $($depoisF.protegida). " + ((@($depoisF.motivos) | Select-Object -First 4) -join '; ')
        }
    } elseif ($SemUAC -and @('criar', 'atualizar') -contains $itemF.acao) {
        $itemF.acao = 'pendente_admin'
        $itemF.detalhe = 'exige administrador (UAC): a cópia protegida da ferramenta do titular espera'
        [void]$rel.pendencias.Add('cópia protegida da ferramenta do titular: rode de novo sem -SemUAC e confirme o UAC')
    }
    if ($itemF.acao -eq 'pendente') { [void]$rel.pendencias.Add('ficha de aberturas pela forma do Windows: ' + $itemF.detalhe) }
    if ($planoArq -and (Test-Path -LiteralPath $planoArq -PathType Leaf)) { Remove-Item -LiteralPath $planoArq -Force }
    $itemF.plano = $null  # os bytes do plano não vão ao relatório
    [void]$rel.itens.Add($itemF)

    # 2c. A chave pública da cópia cifrada (1.7.11): na pasta da âncora, com a ACL dela; o UAC é o desta etapa (a âncora e a cópia
    # da ferramenta já tiveram o seu acima); conferida depois por esta conta, sem elevação, como a âncora.
    if ($planoChave) {
        $itemC = [ordered]@{ id = 'chave-da-copia'; caminho = $AncoraChaveCopia; exige_admin = $true; acao = $null
                             protegida = $false; conteudo_confere = $false; sha256 = $planoChave.sha256; detalhe = $null
                             sondagem = $null; etapa_administrador = $null }
        $sondC = Get-SondagemAncora $AncoraChaveCopia
        $itemC.sondagem = $sondC
        $itemC.protegida = $sondC.protegida
        $existeC = [bool]$sondC.existe
        $itemC.conteudo_confere = ($existeC -and ((Get-Sha256Arquivo $AncoraChaveCopia) -ceq $planoChave.sha256))
        $precisaC = 'criar'
        if ($existeC) { $precisaC = 'atualizar' }
        if ($existeC -and -not $itemC.conteudo_confere -and -not $TrocarChaveDaCopia) {
            $itemC.acao = 'conflito'
            $itemC.detalhe = "já há outra chave da cópia em ${AncoraChaveCopia}: se você trocou de chave de propósito, rode de novo com -TrocarChaveDaCopia (a anterior fica numa cópia ao lado)"
        } elseif ($itemC.conteudo_confere -and $sondC.protegida) {
            $itemC.acao = 'igual'
        } else {
            $itemC.detalhe = 'exige administrador: o Windows pede confirmação (UAC) só para esta etapa. ' + (@($sondC.motivos) -join '; ')
            if ($sim) {
                $itemC.acao = $precisaC
            } elseif ($SemUAC) {
                $itemC.acao = 'pendente_admin'
                [void]$rel.pendencias.Add('chave pública da cópia cifrada: rode de novo sem -SemUAC e confirme o UAC')
            } else {
                Write-Host ''
                Write-Host 'O Windows vai pedir confirmação de administrador para instalar a chave pública da cópia cifrada.'
                Write-Host ('Arquivo: ' + $ChaveDaCopia + ' (SHA-256 ' + $planoChave.sha256.Substring(0, 16) + '...). Confira a impressão digital que o preparar-chave-copia mostrou, a do seu papel.')
                $registroC = Join-Path $env:TEMP ('fundacao-etapa-chave-copia-' + $carimbo + '.json')
                $argumentosC = @('-NoProfile', '-ExecutionPolicy', 'Bypass', '-File', $PSCommandPath, '-EtapaChaveCopia', '-ChaveDaCopia', $ChaveDaCopia,
                                 '-AncoraChaveCopia', $AncoraChaveCopia, '-ChaveDaCopiaEsperada', $planoChave.sha256, '-RegistroEtapa', $registroC)
                if ($TrocarChaveDaCopia) { $argumentosC += '-TrocarChaveDaCopia' }
                $codigoC = $null
                try {
                    $procC = Microsoft.PowerShell.Management\Start-Process -FilePath (Get-ProgramaDoSistema $POWERSHELL_DO_SISTEMA) `
                        -Verb RunAs -Wait -PassThru -ArgumentList ((@($argumentosC) | ForEach-Object { ConvertTo-ArgumentoNativo $_ }) -join ' ')
                    $codigoC = $procC.ExitCode
                } catch {
                    $itemC.acao = 'pendente_admin'
                    $itemC.detalhe = 'a confirmação de administrador (UAC) não foi dada: a chave da cópia não foi instalada'
                    [void]$rel.pendencias.Add('chave pública da cópia cifrada: rode de novo e confirme o UAC')
                }
                if ($null -ne $codigoC) {
                    if (Test-Path -LiteralPath $registroC -PathType Leaf) {
                        try { $itemC.etapa_administrador = [IO.File]::ReadAllText($registroC) | Microsoft.PowerShell.Utility\ConvertFrom-Json } catch { }
                    }
                    $depoisC = Get-SondagemAncora $AncoraChaveCopia
                    $confereC = ($depoisC.existe -and ((Get-Sha256Arquivo $AncoraChaveCopia) -ceq $planoChave.sha256))
                    $itemC.sondagem = $depoisC
                    $itemC.protegida = $depoisC.protegida
                    $itemC.conteudo_confere = $confereC
                    if ($codigoC -eq 0 -and $depoisC.protegida -and $confereC) {
                        $itemC.acao = $precisaC
                        $itemC.detalhe = 'feito como administrador e conferido por esta conta: ela não altera a chave da cópia; o `backup criar` do kit passa a cifrar'
                    } else {
                        $itemC.acao = 'erro'
                        $itemC.detalhe = "a etapa de administrador terminou com código $codigoC; protegida: $($depoisC.protegida); conteúdo confere: ${confereC}. " + (@($depoisC.motivos) -join '; ')
                    }
                }
            }
        }
        [void]$rel.itens.Add([pscustomobject]$itemC)
    }

    # 3. Hooks e perfis em <raiz>\.claude (área do titular; arquivo trocado vai antes para .claude\anteriores), com as
    # saídas do ajudante calculadas no plano (passo 0).
    $anteriores = Join-Path $claude ('anteriores' + $BARRA + $carimbo)
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    foreach ($nome in $HOOKS) {
        $origem = Join-Path $SKILL ('assets\hooks\' + $nome)
        [void]$rel.itens.Add((Set-ArquivoGerado -Id ('hook:' + $nome) -Destino (Join-Path $claude ('hooks' + $BARRA + $nome)) `
            -Bytes ([IO.File]::ReadAllBytes($origem)) -Anteriores $anteriores -Relativo ('hooks' + $BARRA + $nome) -Sim $sim))
    }
    # Só para o relatório: os interpretadores que o perfil anterior chamava nos hooks (nunca escolhidos nem executados).
    $hooksAnteriores = @(Get-ComandosDosHooks (Join-Path $claude 'settings.json') | Where-Object { $_ -ne $py })
    $item = Set-ArquivoGerado -Id 'settings.json' -Destino (Join-Path $claude 'settings.json') -Bytes $utf8.GetBytes($rPerfil.Saida) `
        -Anteriores $anteriores -Relativo 'settings.json' -Sim $sim
    if ($hooksAnteriores.Count -gt 0 -and $item.acao -ne 'igual') {
        $item.detalhe = 'o perfil anterior chamava nos hooks outro interpretador (' + ($hooksAnteriores -join ', ') +
            '), que não foi usado nem executado; o novo chama ' + $py
    }
    [void]$rel.itens.Add($item)
    if ((Test-Path -LiteralPath $local -PathType Leaf) -and
        ((ConvertTo-Json -Compress -Depth 20 -InputObject ([IO.File]::ReadAllText($local) | Microsoft.PowerShell.Utility\ConvertFrom-Json)) -eq
         (ConvertTo-Json -Compress -Depth 20 -InputObject ($rLocal.Saida | Microsoft.PowerShell.Utility\ConvertFrom-Json)))) {
        [void]$rel.itens.Add([pscustomobject][ordered]@{ id = 'settings.local.json'; caminho = $local; exige_admin = $false; acao = 'igual'
            sha256 = (Get-Sha256Arquivo $local); anterior = $null; detalhe = $null })
    } else {
        $item = Set-ArquivoGerado -Id 'settings.local.json' -Destino $local -Bytes $utf8.GetBytes($rLocal.Saida) `
            -Anteriores $anteriores -Relativo 'settings.local.json' -Sim $sim
        if ($item.acao -eq 'atualizar') {
            $item.detalhe = 'só a identidade das sessões do Windows (o projeto vai ao env do settings.json)'
        }
        [void]$rel.itens.Add($item)
    }
    # O perfil único do Ubuntu da 1.7.9 deixa de valer: cada projeto tem o seu na área do titular (preparar-wsl.sh).
    $wslAntigo = Join-Path $claude 'settings.wsl.json'
    if (Test-Path -LiteralPath $wslAntigo -PathType Leaf) {
        $destinoAntigo = Join-Path $anteriores 'settings.wsl.json'
        $item = [ordered]@{ id = 'settings.wsl.json'; caminho = $wslAntigo; exige_admin = $false; acao = 'aposentar'
                            sha256 = (Get-Sha256Arquivo $wslAntigo); anterior = $destinoAntigo
                            detalhe = '1.7.10: o perfil único do Ubuntu saiu; cada projeto tem o seu na área do titular no Ubuntu (preparar-wsl.sh)' }
        if (-not $sim) {
            New-Item -ItemType Directory -Force -Path $anteriores | Out-Null
            Move-Item -LiteralPath $wslAntigo -Destination $destinoAntigo
        }
        [void]$rel.itens.Add([pscustomobject]$item)
    }

    $acoes = @($rel.itens | ForEach-Object { $_.acao })
    if ($acoes -contains 'erro' -or $acoes -contains 'conflito') {
        return (Complete-Preparo $rel 1 'há item com erro ou conflito: veja o detalhe de cada item' $sim $carimbo)
    }
    if ($acoes -contains 'pendente_admin') {
        return (Complete-Preparo $rel 3 'tudo feito, menos o que espera a confirmação de administrador (UAC): a âncora ou a cópia protegida da ferramenta do titular' $sim $carimbo)
    }
    if ($sim) {
        if (@($acoes | Where-Object { @('igual', 'pendente') -notcontains $_ }).Count -eq 0) {
            return (Complete-Preparo $rel 0 'nada a fazer: esta máquina já está preparada' $sim $carimbo)
        }
        return (Complete-Preparo $rel 0 'simulação: o plano acima mostra o que a execução real faria' $sim $carimbo)
    }
    Complete-Preparo $rel 0 'máquina preparada e conferida' $sim $carimbo
}

if ($MyInvocation.InvocationName -ne '.') {
    if ($EtapaChaveCopia) { exit ([int](Invoke-EtapaChaveCopia | Select-Object -Last 1)) }
    if ($EtapaAncora -or $EtapaFerramenta) { exit ([int](Invoke-EtapaAdministrador | Select-Object -Last 1)) }
    exit ([int](Invoke-Preparo | Select-Object -Last 1))
}
