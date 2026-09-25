#!/usr/bin/env bash
# ── Luna Bot — Instalador de Serviço Systemd ──────────────────
# Compatível com: Fedora, Armbian (ARM), Debian, Ubuntu e derivados.
# Configura o bot para iniciar automaticamente com o sistema
# e reiniciar em caso de falhas (queda de internet, crash, etc).
#
# Uso:
#   sudo bash install-service.sh          → instala o serviço
#   sudo bash install-service.sh remove   → remove o serviço
#
set -euo pipefail

# ── Cores ─────────────────────────────────────────────────────
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

# ── Verificações ──────────────────────────────────────────────
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Raiz do projeto (pasta acima de scripts/)
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
SERVICE_NAME="luna-bot"
SERVICE_FILE="/etc/systemd/system/${SERVICE_NAME}.service"

echo ""
echo -e "${CYAN}${BOLD}  🌙 Luna Bot — Instalador de Serviço${RESET}"
echo -e "${DIM}  ──────────────────────────────────────${RESET}"
echo ""

# Precisa ser root
if [[ $EUID -ne 0 ]]; then
    fail "Este script precisa ser executado como root (sudo)."
fi

# Verificar se systemd está disponível
if ! command -v systemctl &>/dev/null; then
    fail "systemd não encontrado. Este script requer um sistema com systemd."
fi

# ── Modo de remoção ───────────────────────────────────────────
if [[ "${1:-}" == "remove" || "${1:-}" == "uninstall" ]]; then
    info "Removendo serviço ${BOLD}${SERVICE_NAME}${RESET}..."

    if [[ -f "$SERVICE_FILE" ]]; then
        systemctl stop "$SERVICE_NAME" 2>/dev/null || true
        systemctl disable "$SERVICE_NAME" 2>/dev/null || true
        rm -f "$SERVICE_FILE"
        systemctl daemon-reload
        ok "Serviço ${BOLD}${SERVICE_NAME}${RESET} removido com sucesso."
    else
        warn "Serviço não encontrado. Nada para remover."
    fi

    echo ""
    exit 0
fi

# ── Detectar usuário real (quem chamou sudo) ──────────────────
if [[ -n "${SUDO_USER:-}" ]]; then
    RUN_USER="$SUDO_USER"
    RUN_GROUP="$(id -gn "$SUDO_USER")"
else
    # Se rodou diretamente como root, usar o dono do diretório do bot
    RUN_USER="$(stat -c '%U' "$PROJECT_ROOT")"
    RUN_GROUP="$(stat -c '%G' "$PROJECT_ROOT")"
fi

info "Usuário do serviço: ${BOLD}${RUN_USER}:${RUN_GROUP}${RESET}"
info "Diretório do bot:   ${BOLD}${PROJECT_ROOT}${RESET}"

# ── Detectar Python e venv ────────────────────────────────────
VENV_DIR="${PROJECT_ROOT}/.venv"
if [[ -f "${VENV_DIR}/bin/python" ]]; then
    PYTHON_BIN="${VENV_DIR}/bin/python"
    ok "venv encontrado: ${BOLD}${VENV_DIR}${RESET}"
else
    warn "venv não encontrado. O serviço usará o start.sh para criá-lo na primeira execução."
    PYTHON_BIN=""
fi

# ── Verificar .env ────────────────────────────────────────────
if [[ ! -f "${PROJECT_ROOT}/.env" ]]; then
    warn "Arquivo .env não encontrado!"
    warn "Crie ${BOLD}${PROJECT_ROOT}/.env${RESET} com seu DISCORD_TOKEN antes de iniciar o serviço."
fi

# ── Detectar sistema ─────────────────────────────────────────
ARCH=$(uname -m)
OS_ID="desconhecido"
PACKAGE_MANAGER="unknown"

if [[ -f /etc/os-release ]]; then
    # shellcheck disable=SC1091
    source /etc/os-release
    OS_ID="${ID:-desconhecido}"
    
    # Detectar gerenciador de pacotes
    case "$OS_ID" in
        fedora|rhel|centos|rocky|alma|ol)
            PACKAGE_MANAGER="dnf"
            ;;
        debian|ubuntu|armbian|raspbian|linuxmint|pop|elementary)
            PACKAGE_MANAGER="apt"
            ;;
        arch|manjaro|endeavouros|garuda)
            PACKAGE_MANAGER="pacman"
            ;;
        opensuse*|sles)
            PACKAGE_MANAGER="zypper"
            ;;
        alpine)
            PACKAGE_MANAGER="apk"
            ;;
        *)
            PACKAGE_MANAGER="unknown"
            ;;
    esac
fi

info "Sistema detectado:  ${BOLD}${OS_ID}${RESET} (${ARCH}) [${PACKAGE_MANAGER}]"

# ── Instalar dependências do sistema se necessário ────────────
install_sys_deps() {
    local need_install=false

    # Verificar se python3 existe
    if ! command -v python3 &>/dev/null && ! command -v python &>/dev/null; then
        need_install=true
    fi

    # Verificar git
    if ! command -v git &>/dev/null; then
        need_install=true
    fi

    if $need_install; then
        info "Instalando dependências do sistema..."
        case "$PACKAGE_MANAGER" in
            dnf)
                dnf install -y python3 python3-pip python3-virtualenv git 2>/dev/null || true
                ;;
            apt)
                apt-get update -qq 2>/dev/null
                apt-get install -y -qq python3 python3-pip python3-venv git 2>/dev/null || true
                ;;
            pacman)
                pacman -S --noconfirm python python-pip python-virtualenv git 2>/dev/null || true
                ;;
            zypper)
                zypper install -y python3 python3-pip python3-virtualenv git 2>/dev/null || true
                ;;
            apk)
                apk add python3 py3-pip py3-virtualenv git 2>/dev/null || true
                ;;
            *)
                warn "Gerenciador de pacotes '${PACKAGE_MANAGER}' não reconhecido."
                warn "Instale manualmente: Python 3.10+, git, pip, virtualenv"
                ;;
        esac
    fi
}

install_sys_deps

# ── Construir ExecStart ──────────────────────────────────────
# Se a venv já existe, rodar direto o src/main.py com o python da venv.
# Senão, usar o start.sh que cuida de criar a venv e instalar deps.
if [[ -n "$PYTHON_BIN" ]]; then
    EXEC_START="${PYTHON_BIN} ${PROJECT_ROOT}/src/main.py"
else
    EXEC_START="/usr/bin/env bash ${SCRIPT_DIR}/start.sh"
fi

# ── Criar o arquivo do serviço systemd ────────────────────────
info "Criando serviço systemd..."

RUN_HOME="$(eval echo ~${RUN_USER})"

cat > "$SERVICE_FILE" <<UNIT
[Unit]
Description=🌙 Luna Bot — Discord Bot
Documentation=https://github.com/yLectez/Luna-Bot
# Esperar rede estar configurada (importante para após queda de luz)
After=network-online.target
Wants=network-online.target
# Esperar DNS estar funcional
After=nss-lookup.target

[Service]
Type=simple
User=${RUN_USER}
Group=${RUN_GROUP}
WorkingDirectory=${PROJECT_ROOT}

# Carregar variáveis do .env automaticamente
EnvironmentFile=-${PROJECT_ROOT}/.env

# Garantir que Python não bufferize stdout/stderr (importante para journald)
Environment=PYTHONUNBUFFERED=1
Environment=PYTHONDONTWRITEBYTECODE=1

# Comando de execução
ExecStart=${EXEC_START}

# ── Política de Reinício (resiliência) ────────────────────────
# Reinicia SEMPRE que o processo morrer (crash, OOM, kill, update, etc.)
# O sistema de auto-update faz os._exit(0) após git pull — o systemd
# detecta e reinicia o processo com o código novo do disco.
Restart=always

# Esperar 10s antes de reiniciar (evita spam de reconexão)
RestartSec=10

# Se falhar 5 vezes em 120s, parar de tentar por um tempo
StartLimitIntervalSec=120
StartLimitBurst=5

# Após esgotar as tentativas, resetar o contador
# Isso permite que o bot volte mesmo após múltiplas falhas seguidas
StartLimitAction=none

# ── Timeouts ─────────────────────────────────────────────────
# Tempo máximo para o bot iniciar (inclui instalação de deps na 1ª vez)
TimeoutStartSec=120

# Tempo para shutdown gracioso
TimeoutStopSec=15

# ── Resiliência pós queda de energia ─────────────────────────
# Atraso inicial para dar tempo à rede estabilizar após boot
# (especialmente útil em Armbian/Orange Pi onde WiFi demora)
ExecStartPre=/bin/sleep 5

# ── Segurança ────────────────────────────────────────────────
# Impedir escalação de privilégios
NoNewPrivileges=true

# Diretório /tmp privado
PrivateTmp=true

# Sistema de arquivos root como read-only (exceto WorkingDirectory)
ProtectSystem=strict

# ProtectHome=tmpfs esconde o /home real e monta um vazio.
# Usamos BindPaths para expor apenas o necessário dentro dele:
#   - Diretório do bot (leitura/escrita — código, data/, .venv/)
#   - ~/.ssh do usuário (somente leitura — necessário para git via SSH)
ProtectHome=tmpfs
BindPaths=${PROJECT_ROOT}
BindReadOnlyPaths=${RUN_HOME}/.ssh

# Permite escrita no diretório de dados e na venv
ReadWritePaths=${PROJECT_ROOT}/data ${PROJECT_ROOT}/.venv ${PROJECT_ROOT}/src

# ── Logs ─────────────────────────────────────────────────────
# Redirecionar stdout/stderr para o journald
StandardOutput=journal
StandardError=journal
SyslogIdentifier=${SERVICE_NAME}

[Install]
# Iniciar junto com o sistema (multi-user = boot normal)
WantedBy=multi-user.target
UNIT

ok "Serviço criado em ${BOLD}${SERVICE_FILE}${RESET}"

# ── Garantir permissões e estrutura de diretórios ─────────────
info "Configurando permissões..."

# Diretório de dados (banco SQLite, logs)
mkdir -p "${PROJECT_ROOT}/data"
chown -R "${RUN_USER}:${RUN_GROUP}" "${PROJECT_ROOT}/data"
chmod 750 "${PROJECT_ROOT}/data"
ok "Diretório ${BOLD}data/${RESET} pronto."

# Evitar alterar ownership do repositório inteiro (pode impactar dev local).
# Ajustamos apenas diretórios/arquivos necessários para execução.
if [[ ! -r "${PROJECT_ROOT}/src/main.py" ]]; then
    fail "Usuário ${RUN_USER} não consegue ler ${PROJECT_ROOT}/src/main.py."
fi
ok "Ownership global do repositório preservado."

# Scripts executáveis
chmod +x "${SCRIPT_DIR}/start.sh" 2>/dev/null || true
chmod +x "${SCRIPT_DIR}/install-service.sh" 2>/dev/null || true
ok "Scripts marcados como executáveis."

# Venv — garantir que pertence ao usuário correto
if [[ -d "${VENV_DIR}" ]]; then
    chown -R "${RUN_USER}:${RUN_GROUP}" "${VENV_DIR}"
    ok "Permissões da venv ajustadas."
fi

# ── Configurar SSH para Git (acesso ao repositório) ──────────
info "Configurando SSH para Git..."

SSH_DIR="${RUN_HOME}/.ssh"
KNOWN_HOSTS="${SSH_DIR}/known_hosts"

# Criar ~/.ssh se não existir (com permissões corretas)
if [[ ! -d "${SSH_DIR}" ]]; then
    mkdir -p "${SSH_DIR}"
    chmod 700 "${SSH_DIR}"
    chown "${RUN_USER}:${RUN_GROUP}" "${SSH_DIR}"
    ok "Diretório ${BOLD}~/.ssh${RESET} criado."
else
    # Garantir permissões mesmo se já existir
    chmod 700 "${SSH_DIR}"
    chown "${RUN_USER}:${RUN_GROUP}" "${SSH_DIR}"
fi

# Adicionar host key do GitHub ao known_hosts (se ainda não estiver)
if ! grep -q "github.com" "${KNOWN_HOSTS}" 2>/dev/null; then
    if command -v ssh-keyscan &>/dev/null; then
        ssh-keyscan -t ed25519 github.com >> "${KNOWN_HOSTS}" 2>/dev/null
        chmod 644 "${KNOWN_HOSTS}"
        chown "${RUN_USER}:${RUN_GROUP}" "${KNOWN_HOSTS}"
        ok "Host key do GitHub adicionada ao ${BOLD}known_hosts${RESET}."
    else
        warn "ssh-keyscan não encontrado — instale openssh-client para auto-update via SSH."
    fi
else
    ok "GitHub já está no ${BOLD}known_hosts${RESET}."
fi

# Verificar se existe chave SSH para o usuário (apenas aviso)
if [[ ! -f "${SSH_DIR}/id_ed25519" && ! -f "${SSH_DIR}/id_rsa" ]]; then
    warn "Nenhuma chave SSH encontrada em ${BOLD}${SSH_DIR}${RESET}."
    warn "Se o remote usa SSH (git@github.com:...), gere uma chave:"
    warn "  ${BOLD}sudo -u ${RUN_USER} ssh-keygen -t ed25519 -C \"luna-bot\"${RESET}"
    warn "  E adicione a chave pública no GitHub → Settings → SSH Keys."
fi

# ── Ativar e iniciar ─────────────────────────────────────────
info "Recarregando systemd..."
systemctl daemon-reload

info "Ativando serviço para iniciar no boot..."
systemctl enable "$SERVICE_NAME"

# Perguntar se quer iniciar agora
echo ""
echo -e "${YELLOW}${BOLD}  Deseja iniciar o Luna Bot agora? [S/n]${RESET}"
read -r -n 1 REPLY </dev/tty 2>/dev/null || REPLY="s"
echo ""

if [[ "${REPLY,,}" != "n" ]]; then
    info "Iniciando ${BOLD}${SERVICE_NAME}${RESET}..."
    systemctl restart "$SERVICE_NAME"
    sleep 2

    if systemctl is-active --quiet "$SERVICE_NAME"; then
        ok "Luna Bot está ${GREEN}${BOLD}rodando${RESET}!"
    else
        warn "O serviço pode estar iniciando. Verifique com os comandos abaixo."
    fi
else
    ok "Serviço instalado mas ${YELLOW}não iniciado${RESET}. Use os comandos abaixo para iniciar."
fi

# ── Resumo ────────────────────────────────────────────────────
echo ""
echo -e "${CYAN}${BOLD}  🌙 Instalação Concluída!${RESET}"
echo -e "${DIM}  ──────────────────────────────────────${RESET}"
echo ""
echo -e "  ${BOLD}Comandos úteis:${RESET}"
echo ""
echo -e "    ${GREEN}▸${RESET} Ver status:        ${BOLD}sudo systemctl status ${SERVICE_NAME}${RESET}"
echo -e "    ${GREEN}▸${RESET} Ver logs (live):    ${BOLD}sudo journalctl -u ${SERVICE_NAME} -f${RESET}"
echo -e "    ${GREEN}▸${RESET} Ver logs (últimos): ${BOLD}sudo journalctl -u ${SERVICE_NAME} -n 50${RESET}"
echo -e "    ${GREEN}▸${RESET} Reiniciar:          ${BOLD}sudo systemctl restart ${SERVICE_NAME}${RESET}"
echo -e "    ${GREEN}▸${RESET} Parar:              ${BOLD}sudo systemctl stop ${SERVICE_NAME}${RESET}"
echo -e "    ${GREEN}▸${RESET} Desinstalar:        ${BOLD}sudo bash ${SCRIPT_DIR}/install-service.sh remove${RESET}"
echo ""
echo -e "  ${DIM}O bot irá:${RESET}"
echo -e "    ${CYAN}✦${RESET} Iniciar automaticamente quando o sistema ligar"
echo -e "    ${CYAN}✦${RESET} Reiniciar sozinho após crash ou queda de conexão"
echo -e "    ${CYAN}✦${RESET} Esperar a rede estar disponível antes de conectar"
echo ""
