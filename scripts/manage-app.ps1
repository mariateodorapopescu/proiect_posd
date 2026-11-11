[CmdletBinding()]
param(
    [ValidateSet('menu', 'start', 'stop', 'status')]
    [string]$Action = 'menu',
    [switch]$NoBrowser
)

$ErrorActionPreference = 'Stop'
$script:ProjectDirectory = [System.IO.Path]::GetFullPath((Split-Path -Parent $PSScriptRoot))
$script:ComposeFile = Join-Path $script:ProjectDirectory 'docker-compose.yml'
$script:DockerCommand = $null

function Find-DockerCommand {
    $command = Get-Command docker -CommandType Application -ErrorAction SilentlyContinue | Select-Object -First 1
    if ($null -ne $command) { return $command.Source }
    $installedCli = Join-Path $env:ProgramFiles 'Docker\Docker\resources\bin\docker.exe'
    if (Test-Path -LiteralPath $installedCli -PathType Leaf) { return $installedCli }
    throw 'Docker nu este instalat. Instaleaza Docker Desktop cu Linux containers si Docker Compose.'
}

function Invoke-Docker {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    & $script:DockerCommand @Arguments
    $nativeExitCode = $LASTEXITCODE
    if ($nativeExitCode -ne 0) {
        $failure = [System.InvalidOperationException]::new("Comanda Docker a esuat (cod $nativeExitCode).")
        $failure.Data['ExitCode'] = $nativeExitCode
        throw $failure
    }
}

function Invoke-Compose {
    param([Parameter(Mandatory = $true)][string[]]$Arguments)
    $composeArguments = @('compose', '--project-directory', $script:ProjectDirectory,
        '--file', $script:ComposeFile, '--project-name', 'securesync') + $Arguments
    Invoke-Docker -Arguments $composeArguments
}

function Test-DockerEngine {
    # Windows PowerShell may turn redirected native stderr into error records.
    # An unavailable engine is an expected state here, so inspect its exit code.
    $previousErrorPreference = $ErrorActionPreference
    try {
        $ErrorActionPreference = 'Continue'
        & $script:DockerCommand info --format '{{.ServerVersion}}' *> $null
        return $LASTEXITCODE -eq 0
    } finally {
        $ErrorActionPreference = $previousErrorPreference
    }
}

function Wait-DockerEngine {
    if (Test-DockerEngine) { return }
    $dockerDesktop = Join-Path $env:ProgramFiles 'Docker\Docker\Docker Desktop.exe'
    if (-not (Test-Path -LiteralPath $dockerDesktop -PathType Leaf)) {
        throw 'Docker Engine nu raspunde. Porneste Docker Desktop in modul Linux containers si incearca din nou.'
    }
    Write-Host 'Pornesc Docker Desktop. Astept motorul Docker (maximum 180 secunde)...'
    Start-Process -FilePath $dockerDesktop -WindowStyle Hidden | Out-Null
    $deadline = [DateTime]::UtcNow.AddSeconds(180)
    do {
        Start-Sleep -Seconds 3
        if (Test-DockerEngine) { return }
        Write-Host 'Docker Desktop se initializeaza...'
    } while ([DateTime]::UtcNow -lt $deadline)
    throw 'Docker Engine nu a pornit in 180 secunde. Verifica Docker Desktop/WSL si modul Linux containers.'
}

function Test-HttpEndpoint {
    param([Parameter(Mandatory = $true)][string]$Url)
    $response = $null
    try {
        $request = [System.Net.HttpWebRequest]::Create($Url)
        $request.Proxy = $null
        $request.Timeout = 2000
        $request.ReadWriteTimeout = 2000
        $response = $request.GetResponse()
        return [int]$response.StatusCode -eq 200
    } catch {
        return $false
    } finally {
        if ($null -ne $response) { $response.Dispose() }
    }
}

function Wait-SecureSync {
    $endpoints = [ordered]@{
        'Keycloak' = 'http://127.0.0.1:8080/realms/securesync/.well-known/openid-configuration'
        'API' = 'http://127.0.0.1:8081/api/health'
        'Documente' = 'http://127.0.0.1:3001/'
        'Portal' = 'http://127.0.0.1:3002/'
    }
    $deadline = [DateTime]::UtcNow.AddSeconds(120)
    do {
        $pending = @($endpoints.Keys | Where-Object { -not (Test-HttpEndpoint -Url $endpoints[$_]) })
        if ($pending.Count -eq 0) { return }
        Write-Host ('Astept serviciile: ' + ($pending -join ', ') + '...')
        Start-Sleep -Seconds 2
    } while ([DateTime]::UtcNow -lt $deadline)
    Invoke-Compose -Arguments @('ps')
    throw 'Serviciile nu sunt pregatite in 120 secunde. Verifica mesajele Docker sau ruleaza docker compose logs.'
}

function Show-SecureSyncUrls {
    Write-Host ''
    Write-Host 'Documente: http://localhost:3001/'
    Write-Host 'Portal:    http://localhost:3002/'
    Write-Host 'Keycloak:  http://localhost:8080/admin'
}

function Invoke-SecureSyncAction {
    param([ValidateSet('start', 'stop', 'status')][string]$SelectedAction, [switch]$SkipBrowser)
    $script:DockerCommand = Find-DockerCommand
    if ($SelectedAction -eq 'start') {
        Wait-DockerEngine
        $environmentFile = Join-Path $script:ProjectDirectory '.env'
        if (-not (Test-Path -LiteralPath $environmentFile -PathType Leaf)) {
            # Invoke in a child process: init-env.ps1 may call exit when .env already exists.
            & powershell.exe -NoLogo -NoProfile -ExecutionPolicy Bypass -File (Join-Path $script:ProjectDirectory 'scripts\init-env.ps1')
            if ($LASTEXITCODE -ne 0) { throw 'Nu am putut genera configuratia .env.' }
        }
        Invoke-Compose -Arguments @('config', '--quiet')
        Write-Host 'Pornesc toate serviciile SecureSync. Prima construire poate dura cateva minute...'
        Invoke-Compose -Arguments @('up', '-d', '--build')
        Wait-SecureSync
        Write-Host 'SecureSync este pornit complet.' -ForegroundColor Green
        Show-SecureSyncUrls
        if (-not $SkipBrowser) {
            Start-Process 'http://localhost:3001/' | Out-Null
            Start-Process 'http://localhost:3002/' | Out-Null
        }
        return
    }

    if (-not (Test-DockerEngine)) {
        Write-Host 'Docker Engine nu ruleaza; serviciile SecureSync nu sunt accesibile.'
        if ($SelectedAction -eq 'status') { Show-SecureSyncUrls }
        return
    }
    if ($SelectedAction -eq 'stop') {
        Write-Host 'Opresc toate serviciile SecureSync...'
        Invoke-Compose -Arguments @('down', '--remove-orphans')
        Write-Host 'SecureSync este oprit. Bazele de date, PDF-urile si .env au fost pastrate.' -ForegroundColor Green
    } else {
        Invoke-Compose -Arguments @('ps', '--all')
        Show-SecureSyncUrls
    }
}

function Get-FailureExitCode {
    param([System.Exception]$Failure)
    if ($Failure.Data.Contains('ExitCode')) { return [int]$Failure.Data['ExitCode'] }
    return 1
}

function Start-SecureSyncMenu {
    while ($true) {
        Write-Host ''
        Write-Host '========== SecureSync =========='
        Write-Host '1. Porneste complet si deschide aplicatiile'
        Write-Host '2. Opreste complet (pastreaza datele)'
        Write-Host '3. Verifica starea serviciilor'
        Write-Host '0. Iesire'
        $selection = Read-Host 'Alege 1, 2, 3 sau 0'
        if ($selection -eq '0') { return }
        $selectedAction = switch ($selection) { '1' { 'start' }; '2' { 'stop' }; '3' { 'status' }; default { $null } }
        if ($null -eq $selectedAction) {
            Write-Host 'Optiune invalida.' -ForegroundColor Yellow
            continue
        }
        try { Invoke-SecureSyncAction -SelectedAction $selectedAction -SkipBrowser:$NoBrowser }
        catch { Write-Host ('Eroare: ' + $_.Exception.Message) -ForegroundColor Red }
    }
}

# Dot-sourcing loads functions for isolated regression tests without touching Docker.
if ($MyInvocation.InvocationName -eq '.') { return }
try {
    if ($Action -eq 'menu') { Start-SecureSyncMenu }
    else { Invoke-SecureSyncAction -SelectedAction $Action -SkipBrowser:$NoBrowser }
    exit 0
} catch {
    [Console]::Error.WriteLine('Eroare SecureSync: ' + $_.Exception.Message)
    exit (Get-FailureExitCode -Failure $_.Exception)
}
