#!/usr/bin/env bash
# ── Luna Bot — Script de inicialização universal ──
# Funciona em Linux (x86/ARM), macOS e WSL.
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Voltar para a raiz do projeto (pasta acima de scripts/)
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

VENV_DIR=".venv"
MIN_PYTHON="3.10"
REQ_FILE="requirements.txt"
if [[ -t 1 ]] && [[ -n "${TERM:-}" ]]; then
    clear || true
fi

# ── Cores (se o terminal suportar) ───────────────────────────
if [[ -t 1 ]]; then
    BOLD="\033[1m"   DIM="\033[2m"   RESET="\033[0m"
    GREEN="\033[32m" RED="\033[31m"  YELLOW="\033[33m" CYAN="\033[36m"
else
    BOLD="" DIM="" RESET="" GREEN="" RED="" YELLOW="" CYAN=""
fi

info()  { echo -e "${CYAN}${BOLD}▸${RESET} $*"; }
ok()    { echo -e "${GREEN}${BOLD}✔${RESET} $*"; }
warn()  { echo -e "${YELLOW}${BOLD}⚠${RESET} $*"; }
fail()  { echo -e "${RED}${BOLD}✖${RESET} $*"; exit 1; }

# ── Banner ────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}  🌙 Luna Bot${RESET}"
echo -e "${DIM}  ────────────────────────────${RESET}"
echo ""

# ── 1. Detectar Python ───────────────────────────────────────
find_python() {
    # Lista prioritária de comandos Python a tentar
    local cmds=("python3" "python" "python3.12" "python3.11" "python3.10" "python3.9")
    
    for cmd in "${cmds[@]}"; do
        if command -v "$cmd" &>/dev/null; then
            # Verificar versão mínima
            if "$cmd" -c "
import sys
min_ver = tuple(int(x) for x in '${MIN_PYTHON}'.split('.'))
sys.exit(0 if sys.version_info[:2] >= min_ver else 1)
" 2>/dev/null; then
                echo "$cmd"
                return 0
            fi
        fi
    done
    
    # Tentar python sem sufixo numérico (algumas distros)
    if command -v python &>/dev/null; then
        if python -c "
import sys
min_ver = tuple(int(x) for x in '${MIN_PYTHON}'.split('.'))
sys.exit(0 if sys.version_info[:2] >= min_ver else 1)
" 2>/dev/null; then
            echo "python"
            return 0
        fi
    fi
    
    return 1
}

PYTHON=$(find_python) || fail "Python ${MIN_PYTHON}+ não encontrado. Instale: https://python.org"
PY_VERSION=$("$PYTHON" -c "import sys; print(f'{sys.version_info.major}.{sys.version_info.minor}.{sys.version_info.micro}')")
ARCH=$(uname -m)
OS=$(uname -s)
info "Sistema: ${BOLD}${OS} ${ARCH}${RESET}"
info "Python:  ${BOLD}${PY_VERSION}${RESET} (${PYTHON})"

# ── 2. Verificar .env ────────────────────────────────────────
if [[ ! -f ".env" ]]; then
    if [[ -f ".env.example" ]]; then
        warn "Arquivo .env não encontrado — criando a partir de .env.example"
        cp .env.example .env
        warn "Edite ${BOLD}.env${RESET}${YELLOW} e coloque seu DISCORD_TOKEN antes de rodar novamente."
        exit 1
    else
        fail "Arquivo .env não encontrado. Crie um com DISCORD_TOKEN=seu_token"
    fi
fi

# ── 3. Criar / reutilizar venv ───────────────────────────────
if [[ ! -d "$VENV_DIR" ]]; then
    info "Criando ambiente virtual..."
    # Tentar venv primeiro, depois virtualenv se falhar
    if ! "$PYTHON" -m venv "$VENV_DIR" 2>/dev/null; then
        warn "Falha com venv — tentando virtualenv..."
        if command -v virtualenv &>/dev/null; then
            virtualenv -p "$PYTHON" "$VENV_DIR" 2>/dev/null || {
                fail "Não foi possível criar o ambiente virtual com venv ou virtualenv."
            }
        else
            # Instalar virtualenv se possível
            warn "Tentando instalar virtualenv..."
            if command -v pip3 &>/dev/null; then
                pip3 install --user virtualenv >/dev/null 2>&1
                export PATH="$HOME/.local/bin:$PATH"
                virtualenv -p "$PYTHON" "$VENV_DIR" 2>/dev/null || fail "Falha ao criar venv."
            else
                fail "Não foi possível criar o ambiente virtual. Instale python3-venv ou virtualenv."
            fi
        fi
    fi
    ok "Ambiente virtual criado em ${BOLD}${VENV_DIR}/${RESET}"
else
    ok "Ambiente virtual existente: ${BOLD}${VENV_DIR}/${RESET}"
fi

# ── 4. Ativar venv ───────────────────────────────────────────
# shellcheck disable=SC1091
source "${VENV_DIR}/bin/activate" 2>/dev/null || source "${VENV_DIR}/Scripts/activate" 2>/dev/null || fail "Não foi possível ativar o venv."
VENV_PY="$(command -v python)"

# ── 5. Instalar / atualizar dependências ─────────────────────
info "Instalando dependências..."
if ! "$VENV_PY" -m pip --version >/dev/null 2>&1; then
    warn "pip da venv parece corrompido — tentando reparar com ensurepip..."
    "$VENV_PY" -m ensurepip --upgrade >/dev/null 2>&1 || true
fi

"$VENV_PY" -m pip --version >/dev/null 2>&1 || fail "pip indisponível na venv. Remova ${VENV_DIR}/ e rode novamente."
"$VENV_PY" -m pip install --upgrade pip --quiet 2>/dev/null
if [[ -f "constraints.txt" ]]; then
    "$VENV_PY" -m pip install -r "$REQ_FILE" -c constraints.txt --quiet || fail "Falha ao instalar dependências."
else
    "$VENV_PY" -m pip install -r "$REQ_FILE" --quiet || fail "Falha ao instalar dependências."
fi
ok "Dependências instaladas."

# ── 6. Garantir diretório de dados ───────────────────────────
mkdir -p data

# ── 7. Iniciar o bot ─────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}  🌙 Luna Bot — Executando...${RESET}"
echo -e "${DIM}  ────────────────────────────${RESET}"
echo ""

exec "$VENV_PY" src/main.py
