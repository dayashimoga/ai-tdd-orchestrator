#!/bin/bash
# ============================================================
#  AI TDD Orchestrator - Automated Test Runner
#  Creates a virtual environment, installs dependencies,
#  runs tests with coverage, and cleans up afterward.
# ============================================================

set -e

PROJECT_DIR="$(cd "$(dirname "$0")" && pwd)"
VENV_DIR="$PROJECT_DIR/.test_venv"
COVERAGE_MIN=90

echo ""
echo "============================================"
echo "  AI TDD Orchestrator - Test Runner"
echo "============================================"
echo ""

# Step 1: Create virtual environment
echo "[1/5] Creating virtual environment..."
python3 -m venv "$VENV_DIR"

# Step 2: Activate and install dependencies
echo "[2/5] Installing dependencies..."
source "$VENV_DIR/bin/activate"
pip install --quiet --disable-pip-version-check -r "$PROJECT_DIR/requirements.txt"

# Step 3: Run tests with coverage
echo "[3/5] Running tests with coverage..."
echo ""
TEST_EXIT=0
python -m pytest tests/ --cov=scripts/ --cov-report=term-missing --cov-fail-under=$COVERAGE_MIN -q --tb=short || TEST_EXIT=$?
echo ""

# Step 4: Report results
echo "[4/5] Test Results:"
if [ $TEST_EXIT -eq 0 ]; then
    echo "  Status: ALL TESTS PASSED ✅"
    echo "  Coverage: Above ${COVERAGE_MIN}%"
else
    echo "  Status: TESTS FAILED ❌ (exit code: $TEST_EXIT)"
fi

# Step 5: Cleanup
echo "[5/5] Cleaning up virtual environment..."
deactivate 2>/dev/null || true
rm -rf "$VENV_DIR"
echo "  Virtual environment removed."
echo ""
echo "============================================"
echo "  Done!"
echo "============================================"

exit $TEST_EXIT
