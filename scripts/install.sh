#!/bin/bash
# Bot SMC/ICT v2 — Installation
# Usage: chmod +x scripts/install.sh && ./scripts/install.sh

set -e

echo "=================================================="
echo "  Bot SMC/ICT v2 — Installation"
echo "=================================================="
echo ""

# Project root
PROJECT_ROOT="$(cd "$(dirname "$0")/.." && pwd)"
cd "$PROJECT_ROOT"

echo "📁 Project root: $PROJECT_ROOT"

# 1. Check Python version
echo ""
echo "1. Vérification Python..."
python3 --version || { echo "❌ Python3 non trouvé. Installe Python 3.11+"; exit 1; }

# 2. Créer un virtualenv
echo ""
echo "2. Création du virtualenv..."
python3 -m venv .venv || { echo "⚠️  venv non créé — installation système"; }

if [ -d ".venv" ]; then
    echo "✅ Virtualenv créé — activation..."
    source .venv/bin/activate
else
    echo "⚠️  Installation en système — pip install --break-system-packages"
fi

# 3. Installer les dépendances
echo ""
echo "3. Installation des dépendances..."
pip install -r requirements.txt

# 4. Installer MetaTrader5 (Windows only)
echo ""
echo "4. MetaTrader5 (Windows uniquement)..."
if [[ "$OSTYPE" == "msys" || "$OSTYPE" == "win32" ]]; then
    pip install MetaTrader5
    echo "✅ MetaTrader5 installé"
else
    echo "⚠️  Linux/Mac — MetaTrader5 non disponible. Utilise OANDA ou CCXT."
fi

# 5. Configurer .env
echo ""
echo "5. Configuration .env..."
if [ ! -f ".env" ]; then
    cp .env.example .env
    echo "✅ .env créé depuis .env.example"
    echo "⚠️  REMPLIS tes valeurs dans .env avant de lancer le bot !"
    echo "   Ouvrir: nano .env"
else
    echo "✅ .env existe déjà"
fi

# 6. Créer les dossiers nécessaires
echo ""
echo "6. Création des dossiers..."
mkdir -p logs
echo "✅ logs/ créé"

# 7. Tester les modules
echo ""
echo "7. Test des modules..."
python -m pytest tests/ -v --tb=short || { echo "⚠️  Certains tests échouent — vérifie les modules"; }

echo ""
echo "=================================================="
echo "  ✅ Installation terminée !"
echo "=================================================="
echo ""
echo "Pour lancer le bot:"
echo "  Demo:   python scripts/start_bot.py --demo --dashboard"
echo "  Live:   python scripts/start_bot.py --live --dashboard"
echo ""
echo "⚠️  Avant de lancer, configure .env avec tes clés API !"
echo ""
