param([int]$FrontendPort = 3100)
$ErrorActionPreference = 'Stop'
$backend = Split-Path $PSScriptRoot -Parent
$project = Split-Path $backend -Parent
$frontend = Join-Path $project 'classroom_ai_frontend'
$pythonProject = Join-Path $project 'ClassroomAI'
$runtimeDir = Join-Path $backend '.local'
New-Item -ItemType Directory -Path $runtimeDir -Force | Out-Null
$config = @{}
Get-Content -LiteralPath (Join-Path $backend '.env') | ForEach-Object {
    if ($_ -match '^([A-Z_]+)=(.*)$') { $config[$Matches[1]] = $Matches[2] }
}
function Test-Endpoint([string]$Uri) {
    try { return (Invoke-WebRequest -Uri $Uri -UseBasicParsing -TimeoutSec 3).StatusCode -eq 200 } catch { return $false }
}
$pgBin = 'C:\Program Files\PostgreSQL\18\bin'
$pgData = $config['LOCAL_PGDATA']
if ($pgData) {
    & (Join-Path $pgBin 'pg_isready.exe') -h 127.0.0.1 -p 55432 -q
    if ($LASTEXITCODE -ne 0) {
        & (Join-Path $pgBin 'pg_ctl.exe') -D $pgData -l (Join-Path $runtimeDir 'postgres.log') -o '-p 55432 -h 127.0.0.1' start
        if ($LASTEXITCODE -ne 0) { throw 'PostgreSQL could not start. Check .local/postgres.log.' }
    }
}
$started = @()
if (!(Test-Endpoint 'http://127.0.0.1:8001/health')) {
    $pythonExe = Join-Path $pythonProject '.venv\Scripts\python.exe'
    $process = Start-Process -FilePath $pythonExe -WorkingDirectory $pythonProject -ArgumentList '-m','recognition_service.run','--env-file','..\classroom_ai_backend\.env' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'recognition.log') -RedirectStandardError (Join-Path $runtimeDir 'recognition-error.log')
    $started += @{ id = $process.Id; name = 'recognition'; executable = $pythonExe }
}
if (!(Test-Endpoint 'http://127.0.0.1:4000/health')) {
    $node = (Get-Command node.exe).Source
    $process = Start-Process -FilePath $node -WorkingDirectory $backend -ArgumentList '--env-file=.env','src/server.js' -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'api.log') -RedirectStandardError (Join-Path $runtimeDir 'api-error.log')
    $started += @{ id = $process.Id; name = 'api'; executable = $node }
}
if (!(Test-Endpoint "http://localhost:$FrontendPort/login")) {
    if (!(Test-Path -LiteralPath (Join-Path $frontend '.next\BUILD_ID'))) { throw 'Build the frontend first: npm run build in classroom_ai_frontend.' }
    $node = (Get-Command node.exe).Source
    $process = Start-Process -FilePath $node -WorkingDirectory $frontend -ArgumentList 'node_modules/next/dist/bin/next','start','--hostname','127.0.0.1','--port',"$FrontendPort" -WindowStyle Hidden -PassThru -RedirectStandardOutput (Join-Path $runtimeDir 'frontend.log') -RedirectStandardError (Join-Path $runtimeDir 'frontend-error.log')
    $started += @{ id = $process.Id; name = 'frontend'; executable = $node }
}
$stateFile = Join-Path $runtimeDir 'processes.json'
$previous = @()
if (Test-Path -LiteralPath $stateFile) { $previous = @(Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json) }
@($previous + $started) | ConvertTo-Json | Set-Content -LiteralPath $stateFile
Write-Host "Classroom AI: http://localhost:$FrontendPort/login"
Write-Host 'Login credentials: ADMIN_USERNAME and ADMIN_PASSWORD in the backend .env. Startup logs: .local/.'
