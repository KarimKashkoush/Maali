$ErrorActionPreference = 'Stop'
$backend = Split-Path $PSScriptRoot -Parent
$stateFile = Join-Path $backend '.local\processes.json'
if (!(Test-Path -LiteralPath $stateFile)) { Write-Host 'No processes recorded by start-local.ps1.'; exit }
$recorded = @(Get-Content -LiteralPath $stateFile -Raw | ConvertFrom-Json)
foreach ($item in $recorded) {
    $process = Get-CimInstance Win32_Process -Filter "ProcessId=$([int]$item.id)" -ErrorAction SilentlyContinue
    if (!$process) { continue }
    if ($process.ExecutablePath -ne $item.executable) { continue }
    $expected = switch ($item.name) { 'api' { 'src/server.js' } 'frontend' { 'next/dist/bin/next' } 'recognition' { 'recognition_service.run' } }
    if (!$expected -or !$process.CommandLine.Contains($expected)) { continue }
    # Stop only the recorded task process and verified direct recognition child.
    if ($item.name -eq 'recognition') {
        Get-CimInstance Win32_Process -Filter "ParentProcessId=$([int]$item.id)" | Where-Object { $_.CommandLine -like '*recognition_service.run*' } | ForEach-Object { Stop-Process -Id $_.ProcessId -ErrorAction SilentlyContinue }
    }
    Stop-Process -Id $process.ProcessId -ErrorAction SilentlyContinue
}
Set-Content -LiteralPath $stateFile -Value '[]'
Write-Host 'Recorded application processes stopped. PostgreSQL remains running.'
