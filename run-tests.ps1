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
if (Test-Path $ActivateScript) {
    . $ActivateScript
}

$PYTHON_EXE = ".\$VENV_DIR\Scripts\python.exe"

# 5. Install dependencies strictly inside the venv
Write-Host "Installing requirements and test modules safely inside venv..." -ForegroundColor Cyan
& $PYTHON_EXE -m pip install --upgrade pip --quiet
& $PYTHON_EXE -m pip install -r requirements.txt --quiet
& $PYTHON_EXE -m pip install pytest pytest-cov --quiet

# 6. Run the Test Suite with Coverage Requirements
Write-Host "Running Tests and enforcing 90% coverage..." -ForegroundColor Cyan
& $PYTHON_EXE -m pytest tests/ --cov=scripts/ --cov-report=term-missing --cov-fail-under=90
$PytestExitCode = $LASTEXITCODE

# 7. Teardown
if ($PytestExitCode -eq 0) {
    Write-Host "Tests passed!" -ForegroundColor Green
} else {
    Write-Host "Tests failed with exit code $PytestExitCode!" -ForegroundColor Red
}
Write-Host "Tearing down ephemeral virtual environment to prevent pollution..." -ForegroundColor Green
if (Get-Command deactivate -ErrorAction SilentlyContinue) {
    deactivate
}
Remove-Item -Recurse -Force $VENV_DIR

if ($PytestExitCode -ne 0) {
    exit $PytestExitCode
}

Write-Host "Clean Exit. Host machine is entirely unpolluted." -ForegroundColor Green
