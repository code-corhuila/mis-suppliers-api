param([Parameter(Mandatory)][string]$InfraRoot,[Parameter(Mandatory)][string]$MongoInfraRoot,[Parameter(Mandatory)][string]$SuppliersDbRoot)
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7) { throw 'Se requiere PowerShell 7.' }
$repo=Split-Path $PSScriptRoot; $infra=(Resolve-Path -LiteralPath $InfraRoot).Path
$db=(Resolve-Path -LiteralPath $SuppliersDbRoot).Path
$settings=@{}
Get-Content -LiteralPath (Join-Path $infra 'env/dev.env') | ForEach-Object { if($_ -match '^([A-Z_]+)=(.*)$') { $settings[$matches[1]]=$matches[2] } }
if(-not $settings.MONGO_SUPPLIERS_PASSWORD) { throw 'Falta password de dominio.' }
$previous=@{}
foreach($key in @('MONGO_HOST_PORT','MIS_INFRA_MONGO_PATH','MONGO_TEST_PASSWORD')) { $previous[$key]=[Environment]::GetEnvironmentVariable($key,'Process') }
$env:MIS_INFRA_MONGO_PATH=(Resolve-Path -LiteralPath $MongoInfraRoot).Path.Replace('\','/')
$env:MONGO_HOST_PORT='0'; $env:MONGO_TEST_PASSWORD=$settings.MONGO_SUPPLIERS_PASSWORD
$project='mis-prv-api-check-'+[guid]::NewGuid().ToString('N').Substring(0,8)
$options=@('--env-file',(Join-Path $infra 'env/dev.env'),'-p',$project,'-f',(Join-Path $db 'deploy/compose.test.yml'))
try {
    docker compose @options up -d --wait --wait-timeout 120 mongo
    if($LASTEXITCODE -ne 0) { throw 'No inicio Mongo desechable.' }
    docker compose @options run --rm mongo-init
    if($LASTEXITCODE -ne 0) { throw 'No inicio replica set.' }
    docker compose @options build suppliers-db-migrate
    if($LASTEXITCODE -ne 0) { throw 'No compilo migrador.' }
    docker compose @options run --rm suppliers-db-migrate
    if($LASTEXITCODE -ne 0) { throw 'Migraciones fallaron.' }
    docker build -f (Join-Path $repo 'tests/Dockerfile.persistence') -t "$project-tests" $repo
    if($LASTEXITCODE -ne 0) { throw 'No compilo imagen de pruebas.' }
    docker run --rm --network "${project}_platform" --env MONGO_TEST_PASSWORD --env PYTHONDONTWRITEBYTECODE=1 --mount "type=bind,source=$repo,target=/workspace,readonly" --workdir /workspace "$project-tests" python -m pytest -q -p no:cacheprovider
    if($LASTEXITCODE -ne 0) { throw 'Pruebas de persistencia fallaron.' }
    Write-Output 'PASS: nucleo, adaptador y transacciones nativas en replica set desechable.'
} finally {
    # Solo el proyecto aleatorio creado aqui; nunca mis-dev, qa o main.
    docker compose @options down -v
    foreach($key in $previous.Keys) { [Environment]::SetEnvironmentVariable($key,$previous[$key],'Process') }
}
