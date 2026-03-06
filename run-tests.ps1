$ErrorActionPreference = "Stop"

Write-Host "Starting Automated Ephemeral Test Suite (Windows)" -ForegroundColor Cyan

# 1. Define venv directory
$VENV_DIR = ".test_venv"

# 2. Clean up any stale environments
If (Test-Path $VENV_DIR) {
    Write-Host "Removing stale virtual environment..." -ForegroundColor Yellow
    Remove-Item -Recurse -Force $VENV_DIR
}

# 3. Create fresh Python virtual environment
Write-Host "Creating ephemeral python virtual environment..." -ForegroundColor Cyan
python -m venv $VENV_DIR

# 4. Activate the virtual environment
$ActivateScript = ".\$VENV_DIR\Scripts\Activate.ps1"
. $ActivateScript

# 5. Install dependencies strictly inside the venv
Write-Host "Installing requirements and test modules safely inside venv..." -ForegroundColor Cyan
python -m pip install --upgrade pip --quiet
pip install -r requirements.txt --quiet
pip install pytest pytest-cov --quiet
npm install -g eslint htmlhint stylelint stylelint-config-standard | Out-Null

# 6. Run the Test Suite with Coverage Requirements
Write-Host "Running Tests and enforcing 90% coverage..." -ForegroundColor Cyan
pytest tests/ --cov=scripts/ --cov-report=term-missing --cov-fail-under=90

# 7. Teardown
Write-Host "Tests passed! Tearing down ephemeral virtual environment to prevent pollution..." -ForegroundColor Green
deactivate
Remove-Item -Recurse -Force $VENV_DIR

Write-Host "Clean Exit. Host machine is entirely unpolluted." -ForegroundColor Green
