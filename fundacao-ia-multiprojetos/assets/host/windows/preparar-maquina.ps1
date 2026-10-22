<#
.SYNOPSIS
Prepara o Windows para uma fundação com dados reais: chave do titular, âncora das decisões assinadas, hooks e
perfis do Claude Code em <raiz>\.claude. Rode no PowerShell comum (não como administrador): o script pede a
confirmação do administrador (UAC) só para a âncora.

.DESCRIPTION
O que faz, nesta ordem, conferindo antes o que já existe (rodar de novo não repete nada):
 1. Chave do titular (-Chave, padrão ~\.ssh\fundacao_titular): se faltar, roda o ssh-keygen do sistema; a senha
    é digitada por você no seu terminal e o script não a vê. Recusa chave que abre sem senha.
 2. Âncora (-Ancora, padrão C:\ProgramData\FundacaoIA\confianca\allowed_signers), que só um administrador altera:
    pastas com dono Administradores e herança cortada (Administradores e Sistema: controle total; Usuários: leitura),
    arquivo herdando da pasta (nada de "(OI)(CI)" em arquivo) com dono Administradores e a linha do titular no
    namespace fundacao-decisao. Esta é a única etapa com UAC. Depois, a sondagem desta conta confere que ela não
    altera a âncora (dono, direitos de escrita e de troca de permissões, herança) e que a linha é a da chave.
 3. Hooks guarda_caminho.py e guarda_identidade.py da skill em <raiz>\.claude\hooks.
 4. <raiz>\.claude\settings.json (sessões do Windows) e, com -Projeto, <raiz>\.claude\settings.wsl.json (sessão
    de dados reais no WSL2), gerados pelos modelos da skill; <raiz>\.claude\settings.local.json com a identidade e,
    com -Projeto, o projeto autenticado das sessões (FUNDACAO_PROJECT) e nada mais, porque a sessão de dados reais
    carrega o arquivo inteiro. -NegarSkill nome1,nome2 nega por nome, nos dois perfis, skills aninhadas em pastas de
    dados (scripts/instrucoes_aninhadas.py lista quais).
O Python que roda o ajudante e os hooks do Windows é o de -Python ou, sem ele, o das instalações registradas do
Windows e do PATH, nunca o do perfil existente; antes de rodar, o script confere que é o python.exe do instalador
oficial (assinatura da Python Software Foundation), sem ligação no caminho e sem escrita para outras contas comuns.
Arquivo trocado vai antes para <raiz>\.claude\anteriores\<data>. Imprime a impressão digital da chave e os SHA-256
e grava um relatório JSON (-Relatorio; no modo real, padrão em <raiz>\evidence\host).

Códigos: 0 pronto e conferido · 1 parou ou há conflito (veja o relatório) · 2 uso incorreto (nada alterado)
· 3 tudo feito menos a âncora, que espera o administrador (UAC recusado ou -SemUAC).

.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-maquina.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Simular
.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-maquina.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Projeto juridico-lab -Backups "E:\Backups-IA"
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $Raiz,
    [string] $Titular,
    [string] $Projeto,
    [string[]] $Backups = @(),
    [string[]] $SomenteLeitura = @(),
    [string[]] $NegarSkill = @(),
    [string] $Chave = (Join-Path $HOME '.ssh\fundacao_titular'),
    [string] $Ancora = (Join-Path $env:ProgramData 'FundacaoIA\confianca\allowed_signers'),
    [string] $Python,
    [switch] $Simular,
    [switch] $SemUAC,
    [switch] $TrocarChave,
    [string] $Relatorio,
    # Uso interno: a etapa da âncora, que o próprio script roda como administrador depois do UAC.
    [switch] $EtapaAncora,
    [string] $ChavePublica,
    [string] $ImpressaoEsperada,
    [string] $RegistroEtapa
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
# Aberto a partir de um PowerShell 7 (pwsh: terminal do Windows, GitHub Actions), o Windows PowerShell herda os
# caminhos de módulo do 7 e não carrega Microsoft.PowerShell.Security (Get-Acl, Set-Acl): ficam só os caminhos
# que não são do PowerShell 7 (CI pública da 1.7.1).
if ($PSVersionTable.PSEdition -eq 'Desktop' -and $env:PSModulePath) {
    $env:PSModulePath = (@($env:PSModulePath -split ';') | Where-Object { $_ -and $_ -notmatch '\\PowerShell\\' }) -join ';'
}

$NAMESPACE = 'fundacao-decisao'
$SID_ADMINS = 'S-1-5-32-544'
$SID_SISTEMA = 'S-1-5-18'
$SID_USUARIOS = 'S-1-5-32-545'
$SKILL = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$AJUDANTE = Join-Path $SKILL 'assets\host\preparo_host.py'
$HOOKS = @('guarda_caminho.py', 'guarda_identidade.py')
$IDENTIFICADOR = '^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$'
$BARRA = [char]92
$DIREITOS_ARQUIVO = [ordered]@{ WRITE_DAC = 0x40000; WRITE_OWNER = 0x80000; DELETE = 0x10000; GENERIC_WRITE = 0x40000000 }
$DIREITOS_PASTA = [ordered]@{ WRITE_DAC = 0x40000; WRITE_OWNER = 0x80000; DELETE = 0x10000; ADD_FILE = 0x2
    ADD_SUBDIRECTORY = 0x4; DELETE_CHILD = 0x40 }
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
    $Titular + ' namespaces="' + $NAMESPACE + '" ' + ((@($LinhaPublica.Trim() -split '\s+')) -join ' ')
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
    # Junta a linha do titular à âncora sem perder as outras linhas e sem trocar chave em silêncio: a mesma chave
    # (comentário à parte) = igual; outra chave do titular = conflito, salvo -Trocar.
    param([string[]] $Linhas = @(), [Parameter(Mandatory = $true)] [string] $Titular,
          [Parameter(Mandatory = $true)] [string] $LinhaNova, [switch] $Trocar)
    $nova = Get-PartesAncora $LinhaNova
    $igual = $false
    $diferente = $false
    foreach ($linha in @($Linhas)) {
        $p = Get-PartesAncora $linha
        if ($null -ne $p -and $p.Principais -contains $Titular) {
            if ($p.Chave -eq $nova.Chave -and $p.Namespaces -eq $nova.Namespaces) { $igual = $true } else { $diferente = $true }
        }
    }
    if ($diferente -and -not $Trocar) { return [pscustomobject]@{ Acao = 'conflito'; Linhas = @($Linhas) } }
    if (-not $diferente -and $igual) { return [pscustomobject]@{ Acao = 'igual'; Linhas = @($Linhas) } }
    if (-not $diferente) { return [pscustomobject]@{ Acao = 'acrescentar'; Linhas = @(@($Linhas) + $LinhaNova) } }
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
    [pscustomobject]@{ Acao = 'trocar'; Linhas = $saida.ToArray() }
}

# ------------------------------------------------------------------ sondagem e permissões da âncora
if (-not ('FundacaoAcesso' -as [type])) {
    Add-Type -TypeDefinition @'
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
    $acl = Get-Acl -LiteralPath $Caminho
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
    (Get-Item -LiteralPath $Pasta -Force).SetAccessControl($sd)
}

function Set-AclArquivoHerdada {
    # Arquivo sem regra própria, herdando da pasta (em 2026-10-20, "(OI)(CI)" aplicado ao arquivo o deixou ilegível
    # para todos). Dono: Administradores.
    param([Parameter(Mandatory = $true)] [string] $Arquivo, [switch] $SemDono)
    $icacls = Join-Path $env:SystemRoot 'System32\icacls.exe'
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

function Get-SshKeygen {
    # O do sistema, por caminho fixo, como a conferência das decisões (um ssh-keygen posto antes no PATH não decide).
    $sistema = Join-Path $env:SystemRoot 'System32\OpenSSH\ssh-keygen.exe'
    if (Test-Path -LiteralPath $sistema -PathType Leaf) { return $sistema }
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
    $r = [ordered]@{ Caminho = $Caminho; Origem = $null; Motivos = $null; Avisos = $null; Assinante = $null; Sha256 = $null }
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
                if ((Get-Item -LiteralPath $p -Force).Attributes -band [IO.FileAttributes]::ReparsePoint) {
                    $motivos.Add("ligação (link simbólico ou junção) no caminho: $p")
                }
                $p = Split-Path -Parent $p
            }
            $a = Get-AuthenticodeSignature -LiteralPath $r.Caminho
            if ($a.SignerCertificate) {
                $r.Assinante = $a.SignerCertificate.GetNameInfo([System.Security.Cryptography.X509Certificates.X509NameType]::SimpleName, $false)
            }
            if ($a.Status -ne 'Valid') {
                $motivos.Add("assinatura Authenticode $($a.Status): o python.exe do instalador oficial (python.org) é assinado pela $ASSINANTE_PYTHON")
            } elseif ($r.Assinante -cne $ASSINANTE_PYTHON) {
                $motivos.Add("assinatura de $($r.Assinante), não da $ASSINANTE_PYTHON")
            }
            $confiaveis = @([Security.Principal.WindowsIdentity]::GetCurrent().User.Value, $SID_ADMINS, $SID_SISTEMA, $SID_INSTALADOR)
            $pasta = Split-Path -Parent $r.Caminho
            foreach ($par in @(@($r.Caminho, $MASCARA_ESCRITA), @($pasta, $MASCARA_ESCRITA), @((Split-Path -Parent $pasta), $MASCARA_TROCA))) {
                $alvo, $mascara = $par
                if (-not $alvo) { continue }
                $acl = Get-Acl -LiteralPath $alvo
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
        $versoes = @(Get-ChildItem -LiteralPath $chave -ErrorAction SilentlyContinue | Sort-Object -Descending -Property {
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
    foreach ($c in @(Get-Command python.exe -CommandType Application -All -ErrorAction SilentlyContinue)) {
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

# ------------------------------------------------------------------ etapa do administrador (depois do UAC)
function Invoke-EtapaAncoraInterna($Acoes) {
    if (-not (Test-Elevado)) { return @{ codigo = 4; erro = 'esta etapa só roda como administrador (confirmação do UAC)' } }
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

# ------------------------------------------------------------------ arquivos em <raiz>\.claude
function Get-ComandosDosHooks([string] $Perfil) {
    # Só leitura, para o relatório: os comandos dos hooks de um perfil existente.
    if (-not (Test-Path -LiteralPath $Perfil -PathType Leaf)) { return @() }
    try {
        $j = [IO.File]::ReadAllText($Perfil) | ConvertFrom-Json
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
    Write-Host ('Resultado (código ' + $Rel.codigo + '): ' + $Rel.mensagem)
}

function Complete-Preparo($Rel, [int] $Codigo, [string] $Mensagem, [bool] $Sim, [string] $Carimbo) {
    $Rel.codigo = $Codigo
    $Rel.mensagem = $Mensagem
    $Rel.fim = (Get-Date).ToString('o')
    $Rel.nada_a_fazer = ($Codigo -eq 0 -and @($Rel.itens | Where-Object { $_.acao -ne 'igual' }).Count -eq 0)
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
        itens = (New-Object System.Collections.ArrayList); pendencias = (New-Object System.Collections.ArrayList)
        nada_a_fazer = $false; codigo = $null; mensagem = $null }
    if (-not $Raiz -or -not $Titular) { return (Complete-Preparo $rel 2 'informe -Raiz e -Titular' $sim $carimbo) }
    if (-not ($Titular -cmatch $IDENTIFICADOR)) {
        return (Complete-Preparo $rel 2 "titular inválido: $Titular (letras minúsculas, dígitos, '.', '_' ou '-')" $sim $carimbo)
    }
    if ($Projeto -and -not ($Projeto -cmatch $IDENTIFICADOR)) { return (Complete-Preparo $rel 2 "projeto inválido: $Projeto" $sim $carimbo) }
    if (-not (Test-Path -LiteralPath $Raiz -PathType Container)) { return (Complete-Preparo $rel 2 "a raiz não existe: $Raiz" $sim $carimbo) }
    $script:Raiz = (Resolve-Path -LiteralPath $Raiz).Path.TrimEnd($BARRA)
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
                                          avisos = @($interp.Avisos) }

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

    # 2. Âncora (a única etapa com administrador)
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
            $codigoEtapa = $null
            try {
                $proc = Start-Process -FilePath (Get-Process -Id $PID).Path -Verb RunAs -Wait -PassThru `
                    -ArgumentList ((@($argumentos) | ForEach-Object { ConvertTo-ArgumentoNativo $_ }) -join ' ')
                $codigoEtapa = $proc.ExitCode
            } catch {
                $item.acao = 'pendente_admin'
                $item.detalhe = 'a confirmação de administrador (UAC) não foi dada: nada mudou na âncora'
                [void]$rel.pendencias.Add('âncora: rode de novo e confirme o UAC')
            }
            if ($null -ne $codigoEtapa) {
                if (Test-Path -LiteralPath $registro -PathType Leaf) {
                    try { $item.etapa_administrador = [IO.File]::ReadAllText($registro) | ConvertFrom-Json } catch { }
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

    # 3. Hooks e perfis em <raiz>\.claude (área do titular; arquivo trocado vai antes para .claude\anteriores)
    $claude = Join-Path $Raiz '.claude'
    $anteriores = Join-Path $claude ('anteriores' + $BARRA + $carimbo)
    $utf8 = New-Object System.Text.UTF8Encoding($false)
    foreach ($nome in $HOOKS) {
        $origem = Join-Path $SKILL ('assets\hooks\' + $nome)
        [void]$rel.itens.Add((Set-ArquivoGerado -Id ('hook:' + $nome) -Destino (Join-Path $claude ('hooks' + $BARRA + $nome)) `
            -Bytes ([IO.File]::ReadAllBytes($origem)) -Anteriores $anteriores -Relativo ('hooks' + $BARRA + $nome) -Sim $sim))
    }
    $negar = @()  # -File entrega "a,b" como um texto só: os nomes vão separados por vírgula
    foreach ($s in @($NegarSkill)) { foreach ($n in ($s -split ',')) { if ($n.Trim()) { $negar += @('--negar-skill', $n.Trim()) } } }
    $perfis = @(@{ id = 'settings.json'; args = (@('perfil-windows', '--raiz', $Raiz, '--python', $py) + $negar) })
    if ($Projeto) {
        $wsl = @('perfil-wsl', '--raiz', $Raiz, '--projeto', $Projeto, '--perfil-windows', $env:USERPROFILE,
                 '--ancora-base', (Split-Path -Parent (Split-Path -Parent $Ancora)))
        foreach ($b in @($Backups)) { if ($b) { $wsl += @('--backups', $b) } }
        foreach ($s in @($SomenteLeitura)) { if ($s) { $wsl += @('--somente-leitura', $s) } }
        $perfis += @{ id = 'settings.wsl.json'; args = ($wsl + $negar) }
    }
    # Só para o relatório: os interpretadores que o perfil anterior chamava nos hooks (nunca escolhidos nem executados).
    $hooksAnteriores = @(Get-ComandosDosHooks (Join-Path $claude 'settings.json') | Where-Object { $_ -ne $py })
    foreach ($perfil in $perfis) {
        $r = Invoke-Ajudante $py $perfil.args
        if ($r.Codigo -ne 0) {
            [void]$rel.itens.Add([pscustomobject][ordered]@{ id = $perfil.id; caminho = (Join-Path $claude $perfil.id); exige_admin = $false
                acao = 'erro'; sha256 = $null; anterior = $null; detalhe = ('o gerador de perfis recusou: ' + ($r.Saida + $r.Erro).Trim()) })
            continue
        }
        $item = Set-ArquivoGerado -Id $perfil.id -Destino (Join-Path $claude $perfil.id) -Bytes $utf8.GetBytes($r.Saida) `
            -Anteriores $anteriores -Relativo $perfil.id -Sim $sim
        if ($perfil.id -eq 'settings.json' -and $hooksAnteriores.Count -gt 0 -and $item.acao -ne 'igual') {
            $item.detalhe = 'o perfil anterior chamava nos hooks outro interpretador (' + ($hooksAnteriores -join ', ') +
                '), que não foi usado nem executado; o novo chama ' + $py
        }
        [void]$rel.itens.Add($item)
    }
    # Identidade das sessões: só acrescenta; outra identidade já gravada é decisão do titular (conflito). Com -Projeto,
    # a sessão de dados reais do WSL carrega o arquivo inteiro: fica só a identidade e o projeto (--estrito; o anterior
    # vai para .claude\anteriores) [auditoria Codex Security da 1.7.6, #5].
    $local = Join-Path $claude 'settings.local.json'
    $argsLocal = @('identidade', '--titular', $Titular)
    if (Test-Path -LiteralPath $local -PathType Leaf) { $argsLocal += @('--atual', $local) }
    if ($Projeto) { $argsLocal += @('--projeto', $Projeto, '--estrito') }  # FUNDACAO_PROJECT: o guarda_caminho.py exige
    $r = Invoke-Ajudante $py $argsLocal
    if ($r.Codigo -eq 0 -and (Test-Path -LiteralPath $local -PathType Leaf) -and
        ((ConvertTo-Json -Compress -Depth 20 -InputObject ([IO.File]::ReadAllText($local) | ConvertFrom-Json)) -eq
         (ConvertTo-Json -Compress -Depth 20 -InputObject ($r.Saida | ConvertFrom-Json)))) {
        [void]$rel.itens.Add([pscustomobject][ordered]@{ id = 'settings.local.json'; caminho = $local; exige_admin = $false; acao = 'igual'
            sha256 = (Get-Sha256Arquivo $local); anterior = $null; detalhe = $null })
    } elseif ($r.Codigo -eq 0) {
        $item = Set-ArquivoGerado -Id 'settings.local.json' -Destino $local -Bytes $utf8.GetBytes($r.Saida) `
            -Anteriores $anteriores -Relativo 'settings.local.json' -Sim $sim
        if ($Projeto -and $item.acao -eq 'atualizar') {
            $item.detalhe = 'só a identidade e o projeto: a sessão de dados reais do WSL carrega este arquivo inteiro'
        }
        [void]$rel.itens.Add($item)
    } else {
        $acao = 'erro'
        if ($r.Codigo -eq 1) { $acao = 'conflito' }
        [void]$rel.itens.Add([pscustomobject][ordered]@{ id = 'settings.local.json'; caminho = $local; exige_admin = $false; acao = $acao
            sha256 = (Get-Sha256Arquivo $local); anterior = $null; detalhe = ($r.Saida + $r.Erro).Trim() })
    }

    $acoes = @($rel.itens | ForEach-Object { $_.acao })
    if ($acoes -contains 'erro' -or $acoes -contains 'conflito') {
        return (Complete-Preparo $rel 1 'há item com erro ou conflito: veja o detalhe de cada item' $sim $carimbo)
    }
    if ($acoes -contains 'pendente_admin') {
        return (Complete-Preparo $rel 3 'tudo feito, menos a âncora, que espera a confirmação de administrador (UAC)' $sim $carimbo)
    }
    if ($sim) {
        if (@($acoes | Where-Object { $_ -ne 'igual' }).Count -eq 0) {
            return (Complete-Preparo $rel 0 'nada a fazer: esta máquina já está preparada' $sim $carimbo)
        }
        return (Complete-Preparo $rel 0 'simulação: o plano acima mostra o que a execução real faria' $sim $carimbo)
    }
    Complete-Preparo $rel 0 'máquina preparada e conferida' $sim $carimbo
}

if ($MyInvocation.InvocationName -ne '.') {
    if ($EtapaAncora) { exit ([int](Invoke-EtapaAncora | Select-Object -Last 1)) }
    exit ([int](Invoke-Preparo | Select-Object -Last 1))
}
