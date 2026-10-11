param([Parameter(Mandatory)][string]$BaseUrl,[Parameter(Mandatory)][string]$SecurityUrl,[Parameter(Mandatory)][string]$SecurityEnv,[Parameter(Mandatory)][string]$ServiceTokenPath,[string]$ContractsImage='mis-suppliers-contracts')
$ErrorActionPreference='Stop'
if($PSVersionTable.PSVersion.Major -lt 7) { throw 'Se requiere PowerShell 7.' }
$settings=@{}; $samples=[Collections.Generic.List[object]]::new()
Get-Content -LiteralPath $SecurityEnv | ForEach-Object { if($_ -match '^([A-Z_]+)=(.*)$') { $settings[$matches[1]]=$matches[2] } }
$service=[IO.File]::ReadAllText((Resolve-Path -LiteralPath $ServiceTokenPath)).Trim()
function Check($value,$message) { if(-not $value) { throw $message } }
function Send($method,$path,$body,$token,$key,$expected) {
    $trace=[guid]::NewGuid().ToString(); $headers=@{'X-Correlation-Id'=$trace;'X-Service'='mis-workflow';'X-User-Role'='INVENTORY'}
    if($token) { $headers.Authorization='Bearer '+$token }
    if($key) { $headers['Idempotency-Key']=$key }
    $options=@{Uri=$BaseUrl.TrimEnd('/')+$path;Method=$method;Headers=$headers;SkipHttpErrorCheck=$true;TimeoutSec=20}
    if($null -ne $body) { $options.Body=($body | ConvertTo-Json -Compress); $options.ContentType='application/json' }
    $response=Invoke-WebRequest @options; $data=$response.Content | ConvertFrom-Json
    Check ($response.StatusCode -eq $expected) "HTTP $method ${path}: $($response.StatusCode), esperado $expected"
    Check ($response.Headers['X-Correlation-Id'][0] -eq $trace) 'Correlacion perdida.'
    if($expected -ge 400) { Check ($data.traceId -eq $trace -and $data.error) 'Error fuera de contrato.' }
    $contract=if($path.StartsWith('/api/v1/receipts')) { 'receipts' } else { 'suppliers' }
    $schema=if($expected -ge 400) { 'Error' } elseif($contract -eq 'receipts') { 'Receipt' } elseif($path -eq '/health') { 'Health' } elseif($data.PSObject.Properties.Name -contains 'data') { 'Page' } else { 'Supplier' }
    $samples.Add(@{contract=$contract;schema=$schema;body=$data})
    return @{Data=$data;Headers=$response.Headers;Trace=$trace}
}
[void](Send GET '/health' $null $null $null 200)
[void](Send GET '/api/v1/suppliers' $null $null $null 401)
[void](Send GET '/api/v1/suppliers' $null 'invalid' $null 401)
$tokens=@{}
foreach($entry in @(@('admin','ADMIN'),@('inventario','INVENTORY'),@('supervisor','SUPERVISOR'),@('consulta','CONSULTATION'))) {
    $password=$settings['BOOTSTRAP_'+$entry[1]+'_PASSWORD']; Check ($password) 'Falta password bootstrap.'
    $login=Invoke-RestMethod -Uri ($SecurityUrl.TrimEnd('/')+'/api/v1/auth/login') -Method Post -ContentType 'application/json' -Body (@{username=$entry[0];password=$password} | ConvertTo-Json -Compress)
    $tokens[$entry[1]]=$login.accessToken
}
$suffix=[guid]::NewGuid().ToString('N').ToUpperInvariant()
$body=@{documentNumber="P-$suffix";name='Proveedor sintetico oficial'}; $key="supplier-$suffix"
$created=Send POST '/api/v1/suppliers' $body $tokens.ADMIN $key 201
Check ($created.Headers.Location[0] -eq '/api/v1/suppliers/'+$created.Data.id) 'Location incorrecto.'
Check ((Send POST '/api/v1/suppliers' $body $tokens.ADMIN $key 200).Data.id -eq $created.Data.id) 'Replay duplicado.'
[void](Send POST '/api/v1/suppliers' @{documentNumber=$body.documentNumber;name='Otro'} $tokens.ADMIN $key 409)
[void](Send POST '/api/v1/suppliers' $body $tokens.ADMIN "duplicate-$suffix" 422)
foreach($role in $tokens.Keys) {
    [void](Send GET '/api/v1/suppliers?page=1&limit=20' $null $tokens[$role] $null 200)
    if($role -ne 'ADMIN') { [void](Send POST '/api/v1/suppliers' $body $tokens[$role] $key 403) }
}
$human=(Invoke-RestMethod -Uri ($SecurityUrl.TrimEnd('/')+'/api/v1/auth/me') -Headers @{Authorization='Bearer '+$tokens.INVENTORY}).id
$receipt=@{supplierId=$created.Data.id;medicationId=[guid]::NewGuid().ToString();reference="R-$suffix";lotNumber='LOT-1';expiresOn='2099-01-01';quantity=10;workflowId=[guid]::NewGuid().ToString();initiatedBy=$human}
foreach($role in $tokens.Keys) { [void](Send POST '/api/v1/receipts' $receipt $tokens[$role] "prepare-$suffix" 403) }
$pending=Send POST '/api/v1/receipts' $receipt $service "prepare-$suffix" 201
$path='/api/v1/receipts/'+$pending.Data.id
Check ($pending.Headers.Location[0] -eq $path -and $pending.Data.traceId -eq $pending.Trace -and $pending.Data.status -eq 'PENDING') 'Preparacion incorrecta.'
foreach($role in @('ADMIN','INVENTORY','SUPERVISOR')) { [void](Send GET $path $null $tokens[$role] $null 200) }
[void](Send GET $path $null $tokens.CONSULTATION $null 403)
[void](Send POST "$path/confirm" @{} $tokens.ADMIN "confirm-$suffix" 403)
[void](Send POST "$path/confirm" @{status='CONFIRMED'} $service "confirm-$suffix" 400)
$confirmed=Send POST "$path/confirm" @{} $service "confirm-$suffix" 200
Check ($confirmed.Data.status -eq 'CONFIRMED' -and $confirmed.Data.changedBy -eq $pending.Data.createdBy) 'Confirmacion/auditoria incorrectas.'
$replay=Send POST '/api/v1/receipts' $receipt $service "prepare-$suffix" 200
Check ($replay.Data.status -eq 'PENDING' -and $replay.Data.traceId -eq $pending.Trace) 'Snapshot alterado.'
$voided=Send POST "$path/void" @{} $service "void-$suffix" 200
Check ($voided.Data.status -eq 'VOIDED') 'Anulacion incorrecta.'
[void](Send POST "$path/confirm" @{} $service "new-confirm-$suffix" 422)
Check ((Send POST "$path/confirm" @{} $service "confirm-$suffix" 200).Data.status -eq 'CONFIRMED') 'Replay de confirmacion alterado.'
Check ((Send GET $path $null $tokens.ADMIN $null 200).Data.status -eq 'VOIDED') 'Replay reactivo documento.'
$temp=[IO.Path]::GetTempFileName(); $repo=Split-Path $PSScriptRoot
try {
    [IO.File]::WriteAllText($temp,($samples | ConvertTo-Json -Depth 20),[Text.UTF8Encoding]::new($false))
    docker run --rm --entrypoint python --env PYTHONPATH=/deps --env PYTHONDONTWRITEBYTECODE=1 --mount "type=bind,source=$repo,target=/workspace,readonly" --mount "type=bind,source=$temp,target=/samples.json,readonly" --workdir /workspace $ContractsImage tests/check_contracts.py /samples.json
    if($LASTEXITCODE -ne 0) { throw 'Contrato real invalido.' }
} finally { Remove-Item -LiteralPath $temp -ErrorAction SilentlyContinue }
Write-Output "PASS: permisos/JWT, proveedor $($created.Data.id), recepcion VOIDED $($pending.Data.id), snapshots y contratos reales."
