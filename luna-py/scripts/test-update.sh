#!/usr/bin/env bash
# ── Teste do Sistema de Auto-Update ───────────────────────────
# Testa os componentes principais sem executar updates reais
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
# Voltar para a raiz do projeto (pasta acima de scripts/)
PROJECT_ROOT="$(dirname "$SCRIPT_DIR")"
cd "$PROJECT_ROOT"

# Preferir o Python da venv do projeto quando disponível.
if [[ -x ".venv/bin/python" ]]; then
    PYTHON_BIN=".venv/bin/python"
elif command -v python3 >/dev/null 2>&1; then
    PYTHON_BIN="python3"
elif command -v python >/dev/null 2>&1; then
    PYTHON_BIN="python"
else
    echo "✗ Python não encontrado no PATH."
    exit 1
fi

echo "🧪 Testando sistema de auto-update do Luna Bot..."
echo ""

# 1. Verificar se arquivos existem
echo "📁 Verificando arquivos..."
files=(
    "src/features/admin/cogs/update.py"
    "src/features/admin/updater_service.py"
    "src/main.py"
    "requirements.txt"
    "scripts/start.sh"
    "scripts/install.sh"
)

for file in "${files[@]}"; do
    if [[ -f "$file" ]]; then
        echo "  ✔ $file"
    else
        echo "  ✗ $file — ARQUIVO AUSENTE"
        exit 1
    fi
done

echo ""

# 2. Verificar sintaxe Python
echo "🐍 Verificando sintaxe Python..."
python_files=(
    "src/features/admin/cogs/update.py"
    "src/features/admin/updater_service.py"
    "src/main.py"
)

for file in "${python_files[@]}"; do
    if "$PYTHON_BIN" -m py_compile "$file" 2>/dev/null; then
        echo "  ✔ $file"
    else
        echo "  ✗ $file — ERRO DE SINTAXE"
        exit 1
    fi
done

echo ""

# 3. Verificar se requirements.txt tem dependências necessárias
echo "📦 Verificando dependências..."
required_deps=("discord.py" "aiosqlite" "psutil")

for dep in "${required_deps[@]}"; do
    if grep -q "^${dep}" requirements.txt; then
        echo "  ✔ $dep"
    else
        echo "  ✗ $dep — DEPENDÊNCIA AUSENTE"
        exit 1
    fi
done

echo ""

# 4. Verificar se scripts são executáveis
echo "⚙️  Verificando permissões..."
scripts=("start.sh" "install-service.sh")

for script in "${scripts[@]}"; do
    if [[ -x "$script" ]]; then
        echo "  ✔ $script"
    else
        echo "  ⚠ $script — não executável (execute: chmod +x $script)"
    fi
done

echo ""

# 5. Verificar se .env.example existe
echo "🔐 Verificando configuração..."
if [[ -f ".env.example" ]]; then
    echo "  ✔ .env.example encontrado"
else
    echo "  ⚠ .env.example ausente"
fi

echo ""

# 6. Executar Testes Unitários
echo "🧪 Executando testes unitários..."
if PYTHONPATH=./src "$PYTHON_BIN" -m unittest discover tests; then
    echo "  ✔ Todos os testes passaram"
else
    echo "  ✗ FALHA NOS TESTES UNITÁRIOS"
    exit 1
fi

echo ""
echo "✅ Todos os testes básicos e unitários passaram!"
echo ""
echo "🐍 Python usado: $PYTHON_BIN"
echo ""
echo "💡 Para testar completamente:"
echo "   1. Configure .env com DISCORD_TOKEN"
echo "   2. Execute: ./start.sh"
echo "   3. Use !update auto on no Discord"
echo "   4. Monitore logs em data/luna.log"
