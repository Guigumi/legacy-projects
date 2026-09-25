# Luna Bot - Windows Initialization Script (PowerShell)
# Provides the same logic as scripts/start.sh for Windows environments.

$ErrorActionPreference = "Continue" # Change to continue to allow manual error handling
$MIN_PYTHON = [version]"3.10"
$VENV_DIR = ".venv"
$REQ_FILE = "requirements.txt"

# Set Project Root (parent of scripts/)
$ScriptPath = $MyInvocation.MyCommand.Definition
$ScriptDir = Split-Path -Path $ScriptPath -Parent
$ProjectRoot = Split-Path -Path $ScriptDir -Parent
Set-Location -Path $ProjectRoot

# ANSI Colors
$ESC = [char]27
$BOLD = "$ESC[1m"
$DIM = "$ESC[2m"
$RESET = "$ESC[0m"
$GREEN = "$ESC[32m"
$RED = "$ESC[31m"
$YELLOW = "$ESC[33m"
$CYAN = "$ESC[36m"

function Write-LunaInfo($msg) { Write-Host "$CYAN$BOLD* $RESET$msg" }
function Write-LunaOk($msg)   { Write-Host "$GREEN$BOLD+ $RESET$msg" }
function Write-LunaWarn($msg) { Write-Host "$YELLOW$BOLD! $RESET$msg" }
function Write-LunaFail($msg) { Write-Host "$RED$BOLD- $RESET$msg"; exit 1 }

try { Clear-Host } catch { }

# Banner
Write-Host ""
Write-Host "$CYAN$BOLD  Luna Bot$RESET"
Write-Host "$DIM  ----------------------------$RESET"
Write-Host ""

# 1. Detect Python
$python = $null
$cmds = @("python", "python3", "py")

foreach ($cmd in $cmds) {
    if (Get-Command $cmd -ErrorAction SilentlyContinue) {
        try {
            $verOutput = & $cmd -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}')"
            if ([version]$verOutput -ge $MIN_PYTHON) {
                $python = $cmd
                break
            }
        } catch { }
    }
}

if (-not $python) {
    Write-LunaFail "Python $MIN_PYTHON+ nao encontrado. Instale em https://python.org"
}

$pyFullVersion = & $python -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')"
Write-LunaInfo "Sistema: Windows"
Write-LunaInfo "Python:  $BOLD$pyFullVersion$RESET ($python)"

# 2. Check .env
if (-not (Test-Path ".env")) {
    if (Test-Path ".env.example") {
        Write-LunaWarn "Arquivo .env nao encontrado - criando a partir de .env.example"
        Copy-Item ".env.example" ".env"
        Write-LunaWarn "Edite .env e coloque seu DISCORD_TOKEN antes de rodar novamente."
        exit 1
    } else {
        Write-LunaFail "Arquivo .env nao encontrado. Crie um com DISCORD_TOKEN=seu_token"
    }
}

# 3. Handle Venv
if (Test-Path "venv") { $VENV_DIR = "venv" }

if (-not (Test-Path $VENV_DIR)) {
    Write-LunaInfo "Criando ambiente virtual em $VENV_DIR..."
    & $python -m venv $VENV_DIR
    if (-not $?) { Write-LunaFail "Falha ao criar venv." }
    Write-LunaOk "Ambiente virtual criado."
} else {
    Write-LunaOk "Ambiente virtual existente: $BOLD$VENV_DIR\$RESET"
}

# 4. Locate Venv Python
$venvPy = Join-Path $VENV_DIR "Scripts\python.exe"
if (-not (Test-Path $venvPy)) {
    Write-LunaFail "Python do venv nao encontrado em $VENV_DIR\Scripts. Remova a pasta e tente novamente."
}

# 5. Install Dependencies
Write-LunaInfo "Instalando dependencias..."
& $venvPy -m pip install --upgrade pip --quiet
if (Test-Path "constraints.txt") {
    & $venvPy -m pip install -r $REQ_FILE -c constraints.txt --quiet
} else {
    & $venvPy -m pip install -r $REQ_FILE --quiet
}

if (-not $?) { Write-LunaFail "Falha ao instalar dependencias." }
Write-LunaOk "Dependencias instaladas."

# 6. Ensure data directory
if (-not (Test-Path "data")) {
    New-Item -ItemType Directory -Path "data" | Out-Null
}

# 7. Interrupt existing instances (Interromper funcionamento anterior)
Write-LunaInfo "Verificando se o bot ja esta rodando..."
$oldProcesses = Get-CimInstance Win32_Process -Filter "name = 'python.exe' OR name = 'python3.exe' OR name = 'py.exe'" | 
                Where-Object { $_.CommandLine -like "*src\main.py*" }

if ($oldProcesses) {
    Write-LunaWarn "Instancia anterior detectada. Finalizando para evitar conflitos..."
    foreach ($proc in $oldProcesses) {
        try {
            Stop-Process -Id $proc.ProcessId -Force -ErrorAction SilentlyContinue
        } catch { }
    }
    Start-Sleep -Seconds 1
}

# 8. Start the Bot
Write-Host ""
Write-Host "$CYAN$BOLD  Luna Bot - Executando...$RESET"
Write-Host "$DIM  ----------------------------$RESET"
Write-Host ""

& $venvPy src\main.py
