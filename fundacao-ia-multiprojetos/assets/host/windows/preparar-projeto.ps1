<#
.SYNOPSIS
Prepara, no Windows, UM projeto da fundação para a sessão dele no Ubuntu (1.7.10): lê as origens só de leitura em
registry\projetos-host.json, roda o preparar-maquina.ps1 com elas e com as cópias de segurança de -Backups (ou de
-BackupsAusente, com o disco delas desligado; repassadas; sem cópias, só com -SemBackups explícito, que uma cópia
registrada recusa) sem trocar o projeto das sessões do Windows, recusa com o Ubuntu ligado e,
com -AssinarFicha, chama a ferramenta fixa do titular para assinar a ficha de aberturas. Rode no PowerShell comum (não
como administrador): o UAC aparece só para a âncora (e, no mesmo UAC, para a cópia protegida da ferramenta do
titular), pelo preparar-maquina.ps1.

.DESCRIPTION
Leva para a skill o que a ferramenta da raiz preparar_sessao_projeto.ps1 fazia, com o registro no lugar dos valores
fixos (DESENHO-1.7.10 §4; contratos do lote 2, §5 e §6). Nesta ordem:
 1. confere -Raiz, -Titular e -Projeto; depois -Backups e -BackupsAusente, pelas mesmas funções e regras do
    preparar-maquina.ps1 (várias pastas separadas por vírgula seguida de unidade, ",D:"; cada uma num disco local, fora
    da raiz e sem conter a raiz, a raiz de um disco valendo como está; as de -Backups existentes; as de
    -BackupsAusente, as cópias num disco desligado agora, só pela forma). Confere o Python pelo mesmo critério do
    preparar-maquina.ps1 (o python.exe do instalador oficial, assinado pela Python Software Foundation; nunca o do perfil
    existente). O .claude\settings.json das sessões do Windows é refeito inteiro a cada preparo: sem as cópias, ele
    perderia o Read e o Edit negados delas, que têm os dados de todos os projetos (folha da integração, I21). Por isso,
    sem -Backups e sem um -SemBackups explícito (ainda não há cópias: ele vai junto para o preparar-maquina.ps1, que tem
    o mesmo portão, pela mesma função), recusa com código 2 antes de gravar qualquer coisa, também na simulação, com o
    motivo e o comando pronto com -Backups; os dois juntos também são recusados, e -Backups só com espaços conta como a
    falta dele (o portão decide pela lista conferida; revisão da terceira rodada da integração, defeitos 1 e 2). Com uma
    cópia registrada em registry\ultima-copia.json, o -SemBackups também é recusado, e o comando pronto traz a pasta de
    cima da última cópia no lugar do texto entre < > (o registro só recusa e sugere, nunca aceita: uma sessão o forja;
    revisão seguinte, defeito 2);
 2. recusa com o Ubuntu ligado (-Distribuicao, padrão Ubuntu; consulta wsl.exe -l --running, que não liga nada): o
    banco não abre pelos dois lados ao mesmo tempo e o perfil não muda com sessão aberta lá. Na simulação, só avisa;
 3. lê registry\projetos-host.json (preparo_host.py ler-projetos-host), que só o titular grava, com
    preparo_host.py registrar-projeto: as origens e as pastas só de leitura de TODOS os projetos registrados vão como
    -SomenteLeitura (o .claude\settings.json é um só para as sessões do Windows: a origem de um projeto não pode
    ficar gravável porque outro foi preparado depois); as skills aninhadas negadas de todos os projetos o ajudante soma
    ao perfil (negação cumulativa). Pasta registrada que não existe agora (disco não montado, pasta movida): a de outro
    projeto vira aviso, com o projeto e a pasta, e segue com o Edit negado (-SomenteLeituraAusente: quando o disco
    voltar, já está protegida); a do próprio projeto para o preparo dele (código 2, nada alterado), com a pasta na
    mensagem. Caminho só do Ubuntu (fora de /mnt/<x>) não cabe no perfil do Windows: aviso;
 3b. confere as skills e os agentes aninhados em projects\<projeto> (preparo_host.py aninhadas-fora-do-registro,
    com os tetos do instrucoes_aninhadas.py) com as negações acumuladas do registro (lote A3, 1.7.11): cada nome que
    falta sai nos avisos com o comando pronto do registrar-projeto; nome fora do padrão vai para a neutralização, com
    o aviso; inventário parcial é aviso, não recusa. Com -RegistrarAninhadas, soma os nomes que faltam ao registro
    na mesma rodada (o registro só cresce; na simulação só diz o que somaria) e o perfil já sai com eles; o projeto
    que ainda não está no registro (sem origem) com nome a negar é recusado (código 2), com o comando pronto do
    registrar-projeto --origem, como no instalar-projeto;
 4. roda o preparar-maquina.ps1 com -SomenteLeitura e com -Backups e -BackupsAusente (as pastas conferidas no passo
    1; ou com -SemBackups) e repassa -Simular, -SemUAC, -TrocarChave, -Python, -Chave, -Ancora e -Ferramentas (a cópia
    protegida da ferramenta do titular, que ele grava no mesmo UAC da âncora quando o Python é instalado para todos os
    usuários; folha da integração, I11). O projeto das sessões do Windows (o do coordenador) não muda: o -Projeto daqui
    é o da sessão do Ubuntu. Para trocar o do Windows de propósito, informe -ProjetoWindows <id> com -TrocarProjeto
    (revisão do lote 2: preparar outro projeto trocava o coordenador ou parava em conflito);
 5. com -AssinarFicha, roda python -I -B -S <ferramenta> assinar-ficha --raiz <raiz> --projeto <projeto>
    [--versao N] (-S: nenhum .pth de site-packages roda antes dela; -I não implica -S): a ferramenta é a da cópia
    protegida do Windows (<Ferramentas>\<versão>\assets\host\fundacao_titular.py, pelo Python que o hashes.json dela
    registra) quando ela está instalada e conferida (igual ao plano desta skill, sem direito desta conta de alterá-la
    e com um Python instalado para todos os usuários: o Get-ItemFerramenta do preparar-maquina.ps1); senão, a da
    skill (<skill>\assets\host\fundacao_titular.py), que avisa na tela que está fora da cópia protegida, e o motivo
    vai nos avisos (revisão da integração, defeito 8). A ferramenta fixa mostra cada abertura em português simples,
    pede que você digite o nome do projeto e a senha da sua chave, no seu terminal (este script não vê nenhuma das
    duas), e grava a ficha e o .sig na caixa de entrada <raiz>\.claude\projetos\<projeto>\ficha. Nenhum valor vindo
    da sessão entra no comando além da raiz, do projeto e da versão;
 6. mostra o comando do Ubuntu (preparar-wsl.sh) que instala a área do titular, de dono root, e o lançador do projeto.
Honestidade (contratos do lote 2, §0): com a raiz em /mnt/<x>, o isolamento entre projetos no Ubuntu é lógico até o
canário passar; nenhuma abertura vale sem o canário no checklist do projeto e sem a ficha assinada.

Códigos: 0 pronto · 1 parou ou há conflito (veja o relatório) · 2 uso incorreto (nada alterado; também sem -Backups
nem -SemBackups, ou com -SemBackups e uma cópia registrada, com o comando pronto; e rodado de dentro de
<raiz>\projects\, como o preparar-maquina.ps1: revisão de segurança da 1.7.10, CI-F1) · 3 falta um passo do titular (o
UAC da âncora) · 4 o Ubuntu está ligado (nada alterado).

.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-projeto.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Projeto juridico-lab -Backups "E:\Backups-IA" -Simular
.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-projeto.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Projeto juridico-lab -Backups "E:\Backups-IA" -AssinarFicha
.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-projeto.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Projeto juridico-lab -Backups "E:\Backups-IA" -ProjetoWindows juridico-lab -TrocarProjeto
.EXAMPLE
powershell -ExecutionPolicy Bypass -File preparar-projeto.ps1 -Raiz "D:\IA\fundacao" -Titular titular -Projeto juridico-lab -SemBackups
#>
[CmdletBinding(SupportsShouldProcess = $true)]
param(
    [string] $Raiz,
    [string] $Titular,
    [string] $Projeto,
    [string] $ProjetoWindows,
    [string] $Python,
    [string] $Chave,
    [string] $Ancora,
    [string] $Ferramentas,
    # As cópias de segurança (I21): conferidas como no preparar-maquina.ps1 e repassadas a ele. Sem elas, só com
    # -SemBackups explícito. -BackupsAusente: as cópias num disco desligado agora (revisão seguinte da terceira rodada da
    # integração, defeito 2), conferidas só pela forma.
    [string[]] $Backups = @(),
    [string[]] $BackupsAusente = @(),
    [switch] $SemBackups,
    [string] $Distribuicao = 'Ubuntu',
    [string] $ClaudeVersao,
    [string] $ClaudeSha256,
    [int] $Versao = 0,
    [switch] $AssinarFicha,
    [switch] $RegistrarAninhadas,
    [switch] $Simular,
    [switch] $SemUAC,
    [switch] $TrocarProjeto,
    [switch] $TrocarChave,
    [string] $Relatorio
)

Set-StrictMode -Version 2.0
$ErrorActionPreference = 'Stop'
$PARAMETROS_DADOS = $PSBoundParameters  # para o comando pronto da recusa sem -Backups nem -SemBackups (I21)
$MAQUINA = Join-Path $PSScriptRoot 'preparar-maquina.ps1'
$SKILL_PROJETO = [IO.Path]::GetFullPath((Join-Path $PSScriptRoot '..\..\..'))
$FERRAMENTA_TITULAR = Join-Path $SKILL_PROJETO 'assets\host\fundacao_titular.py'
$ID_TITULAR = '^[a-z0-9](?:[a-z0-9._-]{0,62}[a-z0-9])?$'
# Projeto: a forma do kit e do porteiro ([a-z0-9-], 1 a 40, sem '--'), a mesma do preparo_host.py.
$ID_PROJETO = '^[a-z0-9](?:[a-z0-9-]{0,38}[a-z0-9])?$'

function Test-Projeto([string] $Valor) {
    ($Valor -cmatch $ID_PROJETO) -and ($Valor -notlike '*--*')
}

function Test-NaLista([string[]] $Linhas, [string] $Nome) {
    # A saída do wsl.exe vem em UTF-16; lida como texto comum, sobra NUL entre as letras: limpa e compara sem caixa.
    foreach ($l in @($Linhas)) { if ((([string]$l) -replace "`0", '').Trim() -ieq $Nome) { return $true } }
    $false
}

function Get-DistribuicoesLigadas {
    # Só consulta (wsl.exe -l --running -q não liga a distribuição); sem wsl.exe ou com erro, nenhuma ligada. A pasta do
    # sistema pela API, não pelo $env:SystemRoot, que um perfil do PowerShell troca (revisão de segurança da 1.7.10,
    # CI-F3).
    $wsl = [IO.Path]::Combine([Environment]::SystemDirectory, 'wsl.exe')
    if (-not [IO.File]::Exists($wsl)) { return @() }
    try {
        $psi = New-Object System.Diagnostics.ProcessStartInfo
        $psi.FileName = $wsl
        $psi.Arguments = '-l --running -q'
        $psi.UseShellExecute = $false
        $psi.CreateNoWindow = $true
        $psi.RedirectStandardOutput = $true
        $psi.RedirectStandardError = $true
        $psi.StandardOutputEncoding = [Text.Encoding]::Unicode
        $p = [System.Diagnostics.Process]::Start($psi)
        $saida = $p.StandardOutput.ReadToEnd()
        [void]$p.StandardError.ReadToEnd()
        $p.WaitForExit()
        if ($p.ExitCode -ne 0) { return @() }
        return @($saida -split "`r?`n" | Where-Object { $_.Trim() })
    } catch { return @() }
}

function ConvertTo-CaminhoWsl([string] $Caminho) {
    $m = [regex]::Match($Caminho, '^([A-Za-z]):[\\/]?(.*)$')
    if (-not $m.Success) { return $Caminho }
    $resto = ($m.Groups[2].Value -replace '[\\/]+', '/').Trim('/')
    $saida = '/mnt/' + $m.Groups[1].Value.ToLowerInvariant()
    if ($resto) { $saida += '/' + $resto }
    $saida
}

function ConvertTo-CaminhoWindows([string] $Caminho) {
    $m = [regex]::Match($Caminho, '^/mnt/([a-z])(?:/(.*))?$')
    if (-not $m.Success) { return $Caminho }
    $m.Groups[1].Value.ToUpperInvariant() + ':\' + ($m.Groups[2].Value -replace '/', '\')
}

function Get-FerramentaDaFicha($ItemFerramenta) {
    # Qual ferramenta do titular o -AssinarFicha chama (revisão da integração, defeito 8). A da cópia protegida do
    # Windows só quando o Get-ItemFerramenta do preparar-maquina.ps1 a dá por igual ao plano desta skill e protegida
    # contra esta conta, com o Python instalado para todos os usuários: aí o hashes.json de lá é o do plano byte a byte,
    # que registra este mesmo Python (plano-ferramenta --python), e a ferramenta confere tudo de novo antes de importar
    # o kit (fundacao_titular.conferir_copia). Senão, a da skill, com o motivo.
    if ($ItemFerramenta -and [string]$ItemFerramenta.acao -ceq 'igual' -and $ItemFerramenta.protegida -and
        $ItemFerramenta.python_todos -and $ItemFerramenta.caminho) {
        return [pscustomobject]@{ caminho = (Join-Path ([string]$ItemFerramenta.caminho) 'assets\host\fundacao_titular.py')
                                  copia = 'protegida'; motivo = $null }
    }
    $motivo = 'a cópia protegida da ferramenta do titular no Windows não foi conferida'
    if ($ItemFerramenta -and $ItemFerramenta.detalhe) { $motivo = [string]$ItemFerramenta.detalhe }
    elseif ($ItemFerramenta -and [string]$ItemFerramenta.acao -ceq 'criar') {
        $motivo = 'a cópia protegida da ferramenta do titular no Windows ainda não foi instalada (o preparar-maquina.ps1 a grava no UAC da âncora)'
    } elseif ($ItemFerramenta -and [string]$ItemFerramenta.acao -ceq 'atualizar') {
        $motivo = 'a cópia protegida da ferramenta do titular no Windows difere desta skill ou não está protegida contra esta conta (o preparar-maquina.ps1 a regrava no UAC da âncora)'
    }
    [pscustomobject]@{ caminho = $FERRAMENTA_TITULAR; copia = 'skill'; motivo = $motivo }
}

function Complete-Projeto($Rel, [int] $Codigo, [string] $Mensagem) {
    $Rel.codigo = $Codigo
    $Rel.mensagem = $Mensagem
    $Rel.fim = (Get-Date).ToString('o')
    if ($Relatorio) {
        New-Item -ItemType Directory -Force -Path (Split-Path -Parent $Relatorio) | Out-Null
        [IO.File]::WriteAllText($Relatorio, (ConvertTo-Json -InputObject $Rel -Depth 12), (New-Object System.Text.UTF8Encoding($false)))
    }
    $titulo = 'Fundação de IA: preparo do projeto ' + $Rel.projeto + ' (Windows)'
    if ($Rel.simulacao) { $titulo += '   [SIMULAÇÃO: nada foi alterado]' }
    Write-Host $titulo
    foreach ($a in @($Rel.avisos)) { Write-Host ('Aviso: ' + $a) }
    if ($Rel.comando_pronto) {
        Write-Host (& { param($m, $s) . $m; Get-TituloDoComandoPronto $s } $MAQUINA $Rel.pasta_sugerida)
        Write-Host ('  ' + $Rel.comando_pronto)
    }
    if ($Rel.proximo_passo) {
        Write-Host 'Depois, no terminal do Ubuntu (o sudo pede a sua senha do Linux para a área do titular):'
        Write-Host ('  ' + $Rel.proximo_passo)
    }
    Write-Host ('Resultado (código ' + $Codigo + '): ' + $Mensagem)
    if ($Relatorio) { Write-Host ('Relatório: ' + $Relatorio) }
    $Codigo
}

function Invoke-PrepararProjeto {
    $sim = [bool]$Simular -or [bool]$WhatIfPreference
    $carimbo = Get-Date -Format 'yyyyMMddTHHmmss'
    $rel = [ordered]@{ script = 'preparar-projeto.ps1'; simulacao = $sim; inicio = (Get-Date).ToString('o'); raiz = $Raiz
        titular = $Titular; projeto = $Projeto; projeto_windows = $ProjetoWindows; ubuntu = $null; registro = $null
        somente_leitura = @(); somente_leitura_ausente = @(); backups = @(); backups_ausentes = @()
        sem_backups = [bool]$SemBackups; ultima_copia = $null; preparar_maquina = $null; assinatura = $null
        proximo_passo = $null; comando_pronto = $null; pasta_sugerida = $null; aninhadas = $null
        avisos = (New-Object System.Collections.ArrayList); codigo = $null; mensagem = $null }
    # Revisão de segurança da 1.7.10, CI-F1: como o preparar-maquina.ps1 (as funções dele, num escopo próprio), este
    # script não roda de dentro de <raiz>\projects\: no modo real, de projects\ de qualquer fundação; na simulação,
    # contra a fundação que o contém. Antes de tudo: nada é lido nem gravado.
    $recusa = & { param($m, $pasta, $r, $s) . $m
        $f = Get-FundacaoQueContem $pasta
        if ($f -and (-not $s -or (Test-MesmaPasta $f $r))) { Get-RecusaDeProjects $f 'preparar-projeto.ps1' } } $MAQUINA $PSScriptRoot $Raiz $sim
    if ($recusa) { return (Complete-Projeto $rel 2 ([string]$recusa)) }
    if (-not $Raiz -or -not $Titular -or -not $Projeto) { return (Complete-Projeto $rel 2 'informe -Raiz, -Titular e -Projeto') }
    if (-not ($Titular -cmatch $ID_TITULAR)) { return (Complete-Projeto $rel 2 "titular inválido: $Titular") }
    if (-not (Test-Projeto $Projeto)) { return (Complete-Projeto $rel 2 "projeto inválido: $Projeto (1 a 40 letras minúsculas, dígitos ou -, sem - nas pontas nem --)") }
    if ($ProjetoWindows -and -not (Test-Projeto $ProjetoWindows)) { return (Complete-Projeto $rel 2 "projeto das sessões do Windows inválido: $ProjetoWindows") }
    if ($TrocarProjeto -and -not $ProjetoWindows) {
        return (Complete-Projeto $rel 2 '-TrocarProjeto troca o projeto das sessões do Windows: informe junto -ProjetoWindows <id> (o -Projeto daqui é o da sessão do Ubuntu)')
    }
    if ($Versao -lt 0) { return (Complete-Projeto $rel 2 "versão inválida: $Versao") }
    if (-not (Test-Path -LiteralPath $Raiz -PathType Container)) { return (Complete-Projeto $rel 2 "a raiz não existe: $Raiz") }
    $raizCheia = (Microsoft.PowerShell.Management\Resolve-Path -LiteralPath $Raiz).Path.TrimEnd([char]92)
    $rel.raiz = $raizCheia
    if (-not (Test-Path -LiteralPath (Join-Path $raizCheia ('projects\' + $Projeto)) -PathType Container)) {
        return (Complete-Projeto $rel 2 "o projeto $Projeto não existe em $raizCheia")
    }
    # As cópias de segurança (folha da integração, I21): o .claude\settings.json das sessões do Windows é refeito inteiro
    # pelo preparar-maquina.ps1, só com o que recebe. Sem as cópias, ele perderia o Read e o Edit negados delas, que
    # têm os dados de todos os projetos: sem -Backups e sem um -SemBackups explícito, recusa antes de gravar qualquer
    # coisa (também na simulação). As pastas de -Backups e de -BackupsAusente passam pela mesma função do
    # preparar-maquina.ps1 (Get-PastasConferidas, num escopo próprio, com a raiz conferida), que as confere de novo ao
    # recebê-las, e o portão é o dele (Get-PortaoDasCopias): decide pelas listas conferidas, não pelo valor cru (revisão
    # da terceira rodada da integração, defeito 2), e pelo registro da última cópia, que recusa o -SemBackups e sugere a
    # pasta no comando pronto (revisão seguinte, defeito 2).
    $copias = & { param($m, $r, $v) . $m; $Raiz = $r
        Get-PastasConferidas -Valores $v -Rotulo '-Backups' -SeAusente ('; com o disco das cópias desligado agora, use -BackupsAusente com a mesma pasta (a negação vale quando ele voltar)')
    } $MAQUINA $raizCheia $Backups
    if ($copias.Erro) { return (Complete-Projeto $rel 2 ($copias.Erro + ': nada foi alterado')) }
    $copiasAusentes = & { param($m, $r, $v) . $m; $Raiz = $r
        Get-PastasConferidas -Valores $v -Rotulo '-BackupsAusente' -AceitarAusente } $MAQUINA $raizCheia $BackupsAusente
    if ($copiasAusentes.Erro) { return (Complete-Projeto $rel 2 ($copiasAusentes.Erro + ': nada foi alterado')) }
    # O Python, pelo critério do preparar-maquina.ps1 (carregado num escopo próprio: só as funções dele são usadas). Vem
    # antes do portão: o registro da última cópia é lido pelo ajudante.
    $interp = & { param($m, $p) . $m; Find-Python $p } $MAQUINA $Python
    if (-not $interp -or -not $interp.Caminho -or @($interp.Motivos).Count -gt 0) {
        $motivos = ''
        if ($interp) { $motivos = (@($interp.Motivos) -join '; ') }
        return (Complete-Projeto $rel 2 ('Python não confiável ou ausente (' + $motivos + '): informe -Python com o python.exe do instalador oficial (python.org)'))
    }
    $py = $interp.Caminho
    $portao = & { param($m, $r, $exe, $c, $a, $sem, $s, $d) . $m; $Raiz = $r
        $u = Get-UltimaCopia $exe
        [pscustomobject]@{ Ultima = $u; Portao = (Get-PortaoDasCopias -Copias $c -Ausentes $a -SemBackups $sem -Ultima $u `
            -Script $s -Dados $d -Quem 'este preparo') }
    } $MAQUINA $raizCheia $py @($copias.Lista) @($copiasAusentes.Lista) ([bool]$SemBackups) $PSCommandPath $PARAMETROS_DADOS
    $rel.ultima_copia = $portao.Ultima
    $rel.comando_pronto = $portao.Portao.ComandoPronto
    $rel.pasta_sugerida = $portao.Portao.PastaSugerida
    if ($portao.Portao.Codigo -ne 0) { return (Complete-Projeto $rel $portao.Portao.Codigo $portao.Portao.Mensagem) }
    $rel.backups = @($copias.Lista)
    $rel.backups_ausentes = @($copiasAusentes.Lista)
    if ($SemBackups) {
        [void]$rel.avisos.Add('-SemBackups: o perfil das sessões do Windows sai sem o Read e o Edit negados das cópias de segurança; rode o preparar-maquina.ps1 com -Backups por último, para devolvê-los')
    }
    foreach ($pendencia in @($portao.Portao.Pendencias)) { [void]$rel.avisos.Add($pendencia) }
    $ligadas = Get-DistribuicoesLigadas
    $rel.ubuntu = [ordered]@{ distribuicao = $Distribuicao; ligado = (Test-NaLista $ligadas $Distribuicao) }
    if ($rel.ubuntu.ligado) {
        $msg = "o Ubuntu ($Distribuicao) está ligado: feche as janelas dele e, no PowerShell, rode: wsl --terminate $Distribuicao"
        if (-not $sim) { return (Complete-Projeto $rel 4 ($msg + ' (nada foi alterado)')) }
        [void]$rel.avisos.Add($msg)
    }
    # As skills e os agentes aninhados do projeto que o registro não nega (lote A3): antes de ler o registro, para que o
    # -RegistrarAninhadas já conte na leitura abaixo. Falha ou resposta estranha é aviso (a conferência é do titular).
    $argsAninhadas = @('aninhadas-fora-do-registro', '--raiz', $raizCheia, '--projeto', $Projeto)
    if ($RegistrarAninhadas) { $argsAninhadas += '--registrar'; if ($sim) { $argsAninhadas += '--simular' } }
    $rAn = & { param($m, $exe, $a) . $m; Invoke-Ajudante $exe $a } $MAQUINA $py $argsAninhadas
    if ($rAn.Codigo -eq 0) {
        try {
            $an = $rAn.Saida | Microsoft.PowerShell.Utility\ConvertFrom-Json
            $rel.aninhadas = $an
            foreach ($aviso in @($an.avisos)) { [void]$rel.avisos.Add([string]$aviso) }
        } catch { [void]$rel.avisos.Add('skills e agentes aninhados NÃO conferidos: resposta do ajudante fora da forma') }
    } elseif ($RegistrarAninhadas -and (($rAn.Saida + $rAn.Erro) -match 'registrar-projeto')) {
        # Lote S2 (A3): como o instalar-projeto, o projeto fora do registro com nome a negar não entra só com os nomes
        $motivo = ($rAn.Saida + $rAn.Erro).Trim()
        try { $motivo = [string]($rAn.Saida | Microsoft.PowerShell.Utility\ConvertFrom-Json).erro } catch { }
        return (Complete-Projeto $rel 2 ($motivo + ' (nada foi alterado)'))
    } else {
        [void]$rel.avisos.Add('skills e agentes aninhados do projeto NÃO conferidos: ' + ($rAn.Saida + $rAn.Erro).Trim())
    }
    $r = & { param($m, $exe, $a) . $m; Invoke-Ajudante $exe $a } $MAQUINA $py @('ler-projetos-host', '--raiz', $raizCheia)
    if ($r.Codigo -ne 0) {
        return (Complete-Projeto $rel 2 ('registry\projetos-host.json ilegível ou fora do esquema: ' + ($r.Saida + $r.Erro).Trim()))
    }
    $reg = $r.Saida | Microsoft.PowerShell.Utility\ConvertFrom-Json  # CI-F3: o cmdlet, não uma função do perfil
    $projetos = @()
    if ($reg.projetos) { $projetos = @($reg.projetos.PSObject.Properties) }
    $doProjeto = @($projetos | Where-Object { $_.Name -ceq $Projeto })
    $rel.registro = [ordered]@{ projeto = $Projeto; registrado = ($doProjeto.Count -gt 0); projetos = @($projetos | ForEach-Object { $_.Name }) }
    if ($doProjeto.Count -eq 0) {
        [void]$rel.avisos.Add("o projeto $Projeto não está em registry\projetos-host.json: sem origens só de leitura dele (o titular registra com preparo_host.py registrar-projeto)")
    }
    # As origens e as pastas só de leitura de TODOS os projetos: o settings.json do Windows é um só, e a origem de um
    # projeto não pode voltar a ser gravável porque outro foi preparado depois (revisão do lote 2). Cada pasta com o
    # projeto que a registrou (reconferência do lote 2: uma pasta sumida de um projeto parava o preparo de todos, com
    # "veja o relatório"): a que não existe agora segue negada por -SomenteLeituraAusente; a de outro projeto só avisa,
    # a do próprio projeto para o preparo dele.
    $leitura = New-Object System.Collections.Generic.List[string]
    $ausentes = New-Object System.Collections.Generic.List[string]
    foreach ($p in $projetos) {
        foreach ($c in @(@($p.Value.origens) + @($p.Value.somente_leitura) | Where-Object { $_ })) {
            $pasta = ConvertTo-CaminhoWindows ([string]$c)
            if ($pasta -notmatch '^[A-Za-z]:[\\/]') {
                [void]$rel.avisos.Add("o projeto $($p.Name) registrou $c, caminho só do Ubuntu: o perfil do Windows não o alcança (fica de fora daqui)")
                continue
            }
            if (Test-Path -LiteralPath $pasta -PathType Container) {
                if (-not ($leitura | Where-Object { $_ -ieq $pasta })) { $leitura.Add($pasta) }
                continue
            }
            if ($p.Name -ceq $Projeto) {
                return (Complete-Projeto $rel 2 "o projeto $Projeto registrou $pasta, que não existe (disco não montado?): monte o disco e rode de novo; se a pasta mudou de lugar, registre a nova (preparo_host.py registrar-projeto) e tire a antiga de registry\projetos-host.json. Nada foi alterado")
            }
            [void]$rel.avisos.Add("o projeto $($p.Name) registrou $pasta, que não existe agora (disco não montado?): segue com a escrita negada no perfil do Windows, e o preparo de $Projeto continua")
            if (-not ($ausentes | Where-Object { $_ -ieq $pasta })) { $ausentes.Add($pasta) }
        }
    }
    $rel.somente_leitura = $leitura.ToArray()
    $rel.somente_leitura_ausente = $ausentes.ToArray()
    # O preparar-maquina.ps1 no mesmo processo (a lista de pastas chega inteira, sem passar por texto), com as cópias de
    # -Backups (I21; com -SemBackups, sem elas) e sem -Projeto: o projeto das sessões do Windows (o do coordenador) fica
    # o que já está gravado.
    $relMaquina = $null
    if ($Relatorio) { $relMaquina = [IO.Path]::ChangeExtension($Relatorio, '.maquina.json') }
    elseif ($sim) { $relMaquina = Join-Path $env:TEMP ('preparar-maquina-' + $Projeto + '-' + $carimbo + '.json') }
    else { $relMaquina = Join-Path $raizCheia ('evidence\host\preparar-maquina-' + $Projeto + '-' + $carimbo + '.json') }
    $parametros = @{ Raiz = $raizCheia; Titular = $Titular; Python = $py; Relatorio = $relMaquina }
    if ($ProjetoWindows) { $parametros.Projeto = $ProjetoWindows }
    if ($leitura.Count -gt 0) { $parametros.SomenteLeitura = [string[]]$leitura.ToArray() }
    if ($ausentes.Count -gt 0) { $parametros.SomenteLeituraAusente = [string[]]$ausentes.ToArray() }
    if (@($rel.backups).Count -gt 0) { $parametros.Backups = [string[]]@($rel.backups) }
    if (@($rel.backups_ausentes).Count -gt 0) { $parametros.BackupsAusente = [string[]]@($rel.backups_ausentes) }
    # O preparar-maquina.ps1 tem o mesmo portão (revisão da terceira rodada da integração, defeito 1): sem cópias, o
    # -SemBackups explícito do titular vai junto.
    if ($SemBackups) { $parametros.SemBackups = $true }
    if ($Chave) { $parametros.Chave = $Chave }
    if ($Ancora) { $parametros.Ancora = $Ancora }
    if ($Ferramentas) { $parametros.Ferramentas = $Ferramentas }  # a cópia protegida da ferramenta do titular (I11)
    if ($sim) { $parametros.Simular = $true }
    if ($SemUAC) { $parametros.SemUAC = $true }
    if ($TrocarProjeto) { $parametros.TrocarProjeto = $true }
    if ($TrocarChave) { $parametros.TrocarChave = $true }
    $null = & $MAQUINA @parametros
    $codigoMaquina = $LASTEXITCODE
    $rel.preparar_maquina = [ordered]@{ codigo = $codigoMaquina; relatorio = $relMaquina }
    if ($codigoMaquina -ne 0 -and $codigoMaquina -ne 3) {
        return (Complete-Projeto $rel $codigoMaquina "o preparar-maquina.ps1 parou (código $codigoMaquina): veja o relatório dele, $relMaquina")
    }
    if ($AssinarFicha) {
        # A cópia protegida, conferida agora (depois do UAC do preparar-maquina.ps1, se houve), pelas funções dele num
        # escopo próprio, com a mesma -Ferramentas (revisão da integração, defeito 8).
        try {
            $itemF = & { param($m, $p, $f) . $m; if ($f) { $Ferramentas = $f }; Get-ItemFerramenta $p } $MAQUINA $py $Ferramentas |
                Select-Object -Last 1
        } catch {
            $itemF = [pscustomobject]@{ acao = 'erro'; protegida = $false; python_todos = $false; caminho = $null
                                        detalhe = ('a conferência da cópia protegida falhou: ' + $_.Exception.Message) }
        }
        $ferramenta = Get-FerramentaDaFicha $itemF
        if (-not (Test-Path -LiteralPath $ferramenta.caminho -PathType Leaf)) {
            return (Complete-Projeto $rel 1 "a ferramenta do titular não está em $($ferramenta.caminho) (pacote ABERTURAS da 1.7.10)")
        }
        if ($ferramenta.motivo) {
            [void]$rel.avisos.Add('a ficha é assinada pela ferramenta da skill, fora da cópia protegida (ela avisa na tela): ' + $ferramenta.motivo)
        }
        $argsFicha = @('-I', '-B', '-S', $ferramenta.caminho, 'assinar-ficha', '--raiz', $raizCheia, '--projeto', $Projeto)
        if ($Versao -gt 0) { $argsFicha += @('--versao', [string]$Versao) }
        $rel.assinatura = [ordered]@{ comando = ($py + ' ' + ($argsFicha -join ' ')); copia = $ferramenta.copia
                                      motivo = $ferramenta.motivo; codigo = $null }
        if (-not $sim) {
            Write-Host 'Assinatura da ficha de aberturas: a ferramenta mostra cada abertura e pede o nome do projeto e a senha da sua chave.'
            & $py @argsFicha
            $rel.assinatura.codigo = $LASTEXITCODE
            if ($LASTEXITCODE -ne 0) {
                return (Complete-Projeto $rel 1 "a assinatura da ficha não terminou (código $($rel.assinatura.codigo)): nada mudou na área do Ubuntu")
            }
        }
    }
    $versaoClaude = '<versão>'
    if ($ClaudeVersao) { $versaoClaude = $ClaudeVersao }
    $hashClaude = '<hash do manifesto assinado>'
    if ($ClaudeSha256) { $hashClaude = $ClaudeSha256 }
    # O bash do passo do Ubuntu sem o ambiente do terminal (funções exportadas, BASH_ENV, PATH): revisão de segurança da
    # 1.7.10, CI-F3 (o preparar-wsl.sh também recusa as funções exportadas e o BASH_ENV que vir).
    $rel.proximo_passo = '/usr/bin/env -i HOME="$HOME" PATH=/usr/bin:/bin /usr/bin/bash --noprofile --norc "' +
        (ConvertTo-CaminhoWsl $SKILL_PROJETO) + '/assets/host/wsl/preparar-wsl.sh" --raiz "' +
        (ConvertTo-CaminhoWsl $raizCheia) + '" --projeto ' + $Projeto + ' --titular ' + $Titular + ' --perfil-windows "' +
        (ConvertTo-CaminhoWsl ([Environment]::GetFolderPath('UserProfile'))) + '" --claude-versao ' + $versaoClaude +
        ' --claude-sha256 ' + $hashClaude
    if ($codigoMaquina -eq 3) {
        return (Complete-Projeto $rel 3 'tudo feito no Windows, menos a âncora, que espera a confirmação de administrador (UAC); depois, o passo do Ubuntu')
    }
    if ($sim) { return (Complete-Projeto $rel 0 'simulação: o plano acima mostra o que a execução real faria') }
    Complete-Projeto $rel 0 'projeto preparado no Windows; falta o passo do Ubuntu (acima)'
}

if ($MyInvocation.InvocationName -ne '.') {
    exit ([int](Invoke-PrepararProjeto | Select-Object -Last 1))
}
