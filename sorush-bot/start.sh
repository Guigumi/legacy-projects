#!/bin/bash

# ================================================
# Script de inicialização do Bot SDN
# ================================================

cd "$(dirname "$0")"

# Cores para output
RED='\033[0;31m'
GREEN='\033[0;32m'
YELLOW='\033[1;33m'
BLUE='\033[0;34m'
NC='\033[0m' # No Color

echo -e "${BLUE}========================================${NC}"
echo -e "${BLUE}        🤖 Bot SDN - Iniciando         ${NC}"
echo -e "${BLUE}========================================${NC}"

# Verificar se Python existe
if ! command -v python3 &> /dev/null; then
    echo -e "${RED}❌ Python3 não encontrado!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ Python3 encontrado${NC}"

# Verificar se o arquivo main.py existe
if [ ! -f "main.py" ]; then
    echo -e "${RED}❌ Arquivo main.py não encontrado!${NC}"
    exit 1
fi

echo -e "${GREEN}✓ main.py encontrado${NC}"

# Verificar se o venv existe, senão criar
if [ ! -d "venv" ]; then
    echo -e "${YELLOW}⚠ Virtual environment não encontrado. Criando...${NC}"
    python3 -m venv venv
    echo -e "${GREEN}✓ Virtual environment criado${NC}"
fi

# Ativar venv
source venv/bin/activate
echo -e "${GREEN}✓ Virtual environment ativado${NC}"

# Instalar dependências se necessário
if [ -f "requirements.txt" ]; then
    echo -e "${YELLOW}📦 Verificando dependências...${NC}"
    pip install -q -r requirements.txt
    echo -e "${GREEN}✓ Dependências verificadas${NC}"
fi

# Criar diretórios necessários
mkdir -p data/database
mkdir -p data/backups
echo -e "${GREEN}✓ Diretórios criados${NC}"

echo -e "${BLUE}========================================${NC}"
echo -e "${GREEN}🚀 Iniciando o bot...${NC}"
echo -e "${BLUE}========================================${NC}"
echo ""

# Iniciar o bot
python3 main.py

# Se o bot parar
echo ""
echo -e "${YELLOW}⚠ Bot encerrado.${NC}"
