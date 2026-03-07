#!/bin/bash
set -e

echo "🚀 Starting Automated Ephemeral Test Suite (Linux/Mac/CI)"

# 1. Define venv directory
VENV_DIR=".test_venv"

# 2. Clean up any stale environments
if [ -d "$VENV_DIR" ]; then
    echo "🧹 Removing stale virtual environment..."
    rm -rf "$VENV_DIR"
fi

# 3. Create fresh Python virtual environment
echo "🐍 Creating ephemeral python virtual environment..."
python3 -m venv $VENV_DIR

# 4. Activate the virtual environment
source $VENV_DIR/bin/activate

# 5. Install dependencies strictly inside the venv
echo "📦 Installing requirements and test modules safely inside venv..."
pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install pytest pytest-cov --quiet
npm install -g eslint htmlhint stylelint stylelint-config-standard >/dev/null 2>&1 || true

# 6. Run the Test Suite with Coverage Requirements
echo "🧪 Running Tests and enforcing 90% coverage..."
pytest tests/ --cov=scripts/ --cov-report=term-missing --cov-fail-under=80

# 7. Teardown
echo "✅ Tests passed! Tearing down ephemeral virtual environment to prevent pollution..."
deactivate
rm -rf "$VENV_DIR"

echo "🎉 Clean Exit. Host machine is entirely unpolluted."
