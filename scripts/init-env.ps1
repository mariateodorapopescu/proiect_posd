$ErrorActionPreference = 'Stop'
$projectDirectory = Split-Path -Parent $PSScriptRoot
$environmentFile = Join-Path $projectDirectory '.env'
if (Test-Path -LiteralPath $environmentFile) {
    Write-Host '.env exista deja; nu a fost modificat.'
    exit 0
}

function New-DemoSecret {
    $secretBytes = New-Object byte[] 32
    $generator = [System.Security.Cryptography.RandomNumberGenerator]::Create()
    try { $generator.GetBytes($secretBytes) } finally { $generator.Dispose() }
    return [Convert]::ToBase64String($secretBytes).TrimEnd('=').Replace('+', '-').Replace('/', '_')
}

$environmentLines = @('KEYCLOAK_ADMIN=admin')
foreach ($secretName in @('KEYCLOAK_ADMIN_PASSWORD', 'KEYCLOAK_DB_PASSWORD', 'POSTGRES_PASSWORD',
        'INTROSPECTION_CLIENT_SECRET', 'EXPERIMENT_ADMIN_CLIENT_SECRET', 'MEMBER_ADMIN_CLIENT_SECRET', 'DEMO_USER_PASSWORD')) {
    $environmentLines += "$secretName=$(New-DemoSecret)"
}
$environmentLines += 'TOKEN_VALIDATION_STRATEGY=jwt'
[System.IO.File]::WriteAllLines($environmentFile, $environmentLines, [System.Text.UTF8Encoding]::new($false))
Write-Host '.env creat cu parole locale aleatoare. Parola conturilor demonstrative este DEMO_USER_PASSWORD din .env.'
