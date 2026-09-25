# Luna Bot - Windows Stop Script (PowerShell)
# Procura e encerra qualquer instancia do bot em execucao.

$ScriptPath = $MyInvocation.MyCommand.Definition
$ScriptDir = Split-Path -Path $ScriptPath -Parent
$ProjectRoot = Split-Path -Path $ScriptDir -Parent
Set-Location -Path $ProjectRoot

Write-Host "Procurando Luna Bot em execucao..."
$oldProcesses = Get-CimInstance Win32_Process -Filter "name = 'python.exe' OR name = 'python3.exe' OR name = 'py.exe'" | 
                Where-Object { $_.CommandLine -like "*src\main.py*" }

if ($oldProcesses) {
    Write-Host "Instancia encontrada. Finalizando..." -ForegroundColor Yellow
    foreach ($proc in $oldProcesses) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
            Write-Host "Bot (PID: $($proc.ProcessId)) interrompido com sucesso." -ForegroundColor Green
        } catch { }
    }
} else {
    Write-Host "Nenhuma instancia do bot em execucao." -ForegroundColor Cyan
}
