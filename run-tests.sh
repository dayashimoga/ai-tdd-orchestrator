#!/bin/bash
set -e

echo "🚀 Starting Automated Ephemeral Test Suite (Linux/Mac/CI)"

VENV_DIR=".test_venv"

# Preserve cached venv if it exists and is healthy
if [ -f "$VENV_DIR/bin/activate" ]; then
    echo "♻️ Reusing cached virtual environment..."
else
    echo "🐍 Creating ephemeral python virtual environment..."
    rm -rf "$VENV_DIR" 2>/dev/null || true
    python3 -m venv $VENV_DIR
fi

source $VENV_DIR/bin/activate

echo "📦 Installing requirements and test modules safely inside venv..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install pytest pytest-cov --quiet
npm install -g eslint htmlhint stylelint stylelint-config-standard >/dev/null 2>&1 || true

echo "🧪 Running Tests and enforcing 90% coverage..."
pytest tests/ --cov=scripts/ --cov-report=term-missing --cov-fail-under=90

echo "✅ Tests passed! Virtual environment preserved for CI cache reuse."
deactivate
echo "🎉 Clean Exit."
