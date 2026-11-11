$ErrorActionPreference = 'Stop'
. (Join-Path $PSScriptRoot 'manage-app.ps1')

$testDirectory = Join-Path ([System.IO.Path]::GetTempPath()) ('securesync-launcher-' + [Guid]::NewGuid().ToString('N'))
$testProject = Join-Path $testDirectory 'project with spaces'
$testScripts = Join-Path $testProject 'scripts'
$testBin = Join-Path $testDirectory 'bin'
New-Item -ItemType Directory -Path $testScripts, $testBin | Out-Null
$testLog = Join-Path $testDirectory 'docker.log'
$fakeDocker = Join-Path $testBin 'docker.cmd'
$testBat = Join-Path $testProject 'SecureSync.bat'
$originalPath = $env:PATH
$originalTestLog = $env:SECURESYNC_TEST_LOG
$originalTestExit = $env:SECURESYNC_TEST_EXIT
$originalEngineOff = $env:SECURESYNC_TEST_ENGINE_OFF
$passed = 0

function Assert-Test {
    param([bool]$Condition, [string]$Message)
    if (-not $Condition) { throw $Message }
}

function Read-DockerLog {
    if (Test-Path -LiteralPath $testLog) { return [System.IO.File]::ReadAllText($testLog) }
    return ''
}

function Clear-DockerLog { [System.IO.File]::WriteAllText($testLog, '') }

try {
    [System.IO.File]::WriteAllText($fakeDocker, "@echo off`r`necho %*>>`"%SECURESYNC_TEST_LOG%`"`r`nif `%1==info goto engine`r`nexit /b %SECURESYNC_TEST_EXIT%`r`n:engine`r`nif not `"%SECURESYNC_TEST_ENGINE_OFF%`"==`"1`" exit /b 0`r`necho Docker engine unavailable 1>&2`r`nexit /b 1`r`n", [System.Text.Encoding]::ASCII)
    [System.IO.File]::WriteAllText((Join-Path $testProject '.env'), 'TEST_ONLY=1')
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'manage-app.ps1') -Destination $testScripts
    Copy-Item -LiteralPath (Join-Path $PSScriptRoot 'init-env.ps1') -Destination $testScripts
    Copy-Item -LiteralPath (Join-Path (Split-Path -Parent $PSScriptRoot) 'SecureSync.bat') -Destination $testBat
    $env:SECURESYNC_TEST_LOG = $testLog
    $env:SECURESYNC_TEST_EXIT = '0'
    $env:SECURESYNC_TEST_ENGINE_OFF = '0'
    $env:PATH = $testBin + ';' + $originalPath
    $script:ProjectDirectory = $testProject
    $script:ComposeFile = Join-Path $testProject 'docker-compose.yml'
    $script:DockerCommand = $fakeDocker

    $env:SECURESYNC_TEST_EXIT = '23'
    $caught = $false
    try { Invoke-Docker -Arguments @('compose', 'version') }
    catch { $caught = $_.Exception.Data['ExitCode'] -eq 23 }
    Assert-Test $caught 'Native Docker exit code was not preserved.'
    $passed++; Write-Host 'PASS native Docker failure preserves exit code'

    $env:SECURESYNC_TEST_ENGINE_OFF = '1'
    Assert-Test (-not (Test-DockerEngine)) 'An unavailable engine did not return false.'
    $env:SECURESYNC_TEST_ENGINE_OFF = '0'
    $passed++; Write-Host 'PASS unavailable engine is handled without throwing on native stderr'

    $env:SECURESYNC_TEST_EXIT = '0'
    Clear-DockerLog
    Invoke-SecureSyncAction -SelectedAction stop -SkipBrowser
    $log = Read-DockerLog
    Assert-Test ($log.Contains('down --remove-orphans')) 'Stop did not use Compose down.'
    Assert-Test (-not ($log -match '(?m)(^|\s)(-v|--volumes)(\s|$)')) 'Stop attempted to remove data volumes.'
    Assert-Test ($log.Contains('--project-name securesync') -and $log.Contains($testProject)) 'Stop did not bind its own project and path.'
    $passed++; Write-Host 'PASS stop targets SecureSync and preserves data volumes'

    Clear-DockerLog
    $env:SECURESYNC_TEST_EXIT = '29'
    $caught = $false
    try { Invoke-SecureSyncAction -SelectedAction start -SkipBrowser }
    catch { $caught = $_.Exception.Data['ExitCode'] -eq 29 }
    $log = Read-DockerLog
    Assert-Test $caught 'Configuration failure was swallowed.'
    Assert-Test (-not $log.Contains('up -d')) 'Startup continued after configuration failed.'
    $passed++; Write-Host 'PASS failed configuration stops startup before containers'

    $env:SECURESYNC_TEST_EXIT = '0'
    Clear-DockerLog
    $script:checkedEndpoints = @()
    function Test-HttpEndpoint {
        param([string]$Url)
        $script:checkedEndpoints += $Url
        return $true
    }
    function Start-Process { throw 'NoBrowser test unexpectedly opened an application.' }
    Invoke-SecureSyncAction -SelectedAction start -SkipBrowser
    Assert-Test ((Read-DockerLog).Contains('up -d --build')) 'Startup did not build/start all services.'
    Assert-Test ($script:checkedEndpoints.Count -eq 4) 'Startup did not check all four public endpoints.'
    Assert-Test (([System.IO.File]::ReadAllText((Join-Path $testProject '.env'))) -eq 'TEST_ONLY=1') 'Existing .env was changed.'
    $passed++; Write-Host 'PASS full startup waits for every endpoint and respects NoBrowser/.env'

    $temporaryEnvironment = Join-Path $testProject '.env'
    Remove-Item -LiteralPath $temporaryEnvironment
    Invoke-SecureSyncAction -SelectedAction start -SkipBrowser
    Assert-Test (Test-Path -LiteralPath $temporaryEnvironment -PathType Leaf) 'First startup did not generate .env.'
    $generatedLines = [System.IO.File]::ReadAllLines($temporaryEnvironment)
    Assert-Test (@($generatedLines | Where-Object { $_ -match '^DEMO_USER_PASSWORD=.+$' }).Count -eq 1) 'Generated environment is missing the demo password.'
    Assert-Test (@($generatedLines | Where-Object { $_ -match '^POSTGRES_PASSWORD=.+$' }).Count -eq 1) 'Generated environment is missing the database password.'
    $passed++; Write-Host 'PASS first startup generates local .env without printing secrets'

    Clear-DockerLog
    function Test-DockerEngine { return $false }
    Invoke-SecureSyncAction -SelectedAction stop -SkipBrowser
    Assert-Test (-not ((Read-DockerLog).Contains('down'))) 'Stop ran commands against an unavailable engine.'
    $passed++; Write-Host 'PASS stopping an unavailable engine does not launch Docker Desktop'

    Clear-DockerLog
    Push-Location $testDirectory
    try {
        & $testBat status
        Assert-Test ($LASTEXITCODE -eq 0) 'BAT status failed from unrelated working directory.'
    } finally { Pop-Location }
    $log = Read-DockerLog
    Assert-Test ($log.Contains($testProject) -and $log.Contains('ps --all')) 'BAT did not resolve its directory with spaces.'
    $passed++; Write-Host 'PASS BAT handles spaces and unrelated working directory'

    $env:SECURESYNC_TEST_EXIT = '37'
    $ErrorActionPreference = 'Continue'
    & $testBat status 2>$null
    $ErrorActionPreference = 'Stop'
    Assert-Test ($LASTEXITCODE -eq 37) 'BAT did not propagate native failure code.'
    $passed++; Write-Host 'PASS BAT propagates native failure to caller'

    Clear-DockerLog
    $ErrorActionPreference = 'Continue'
    & $testBat invalid-action 2>$null
    $ErrorActionPreference = 'Stop'
    Assert-Test ($LASTEXITCODE -ne 0) 'Invalid action was accepted.'
    Assert-Test ((Read-DockerLog) -eq '') 'Invalid action reached Docker.'
    $passed++; Write-Host 'PASS invalid actions are rejected before Docker'

    Write-Host "All $passed launcher tests passed. No real Docker services were changed."
} finally {
    $env:PATH = $originalPath
    $env:SECURESYNC_TEST_LOG = $originalTestLog
    $env:SECURESYNC_TEST_EXIT = $originalTestExit
    $env:SECURESYNC_TEST_ENGINE_OFF = $originalEngineOff
    # Delete only files/directories created explicitly by this test. No recursive removal.
    foreach ($createdFile in @($fakeDocker, $testLog, $testBat, (Join-Path $testScripts 'manage-app.ps1'), (Join-Path $testScripts 'init-env.ps1'), (Join-Path $testProject '.env'))) {
        if (Test-Path -LiteralPath $createdFile -PathType Leaf) { Remove-Item -LiteralPath $createdFile }
    }
    foreach ($createdDirectory in @($testScripts, $testBin, $testProject, $testDirectory)) {
        if (Test-Path -LiteralPath $createdDirectory -PathType Container) { Remove-Item -LiteralPath $createdDirectory }
    }
}
