$ErrorActionPreference = "Stop"

Write-Host "Starting Automated Ephemeral Test Suite (Windows)" -ForegroundColor Cyan

$VENV_DIR = ".test_venv"

# Preserve cached venv if it exists and is healthy
If (Test-Path ".\$VENV_DIR\Scripts\python.exe") {
    Write-Host "Reusing cached virtual environment..." -ForegroundColor Yellow
} Else {
    If (Test-Path $VENV_DIR) {
        Remove-Item -Recurse -Force $VENV_DIR
    }
    Write-Host "Creating ephemeral python virtual environment..." -ForegroundColor Cyan
    python -m venv $VENV_DIR
}

$ActivateScript = ".\$VENV_DIR\Scripts\Activate.ps1"
if (Test-Path $ActivateScript) {
    . $ActivateScript
}

$PYTHON_EXE = ".\$VENV_DIR\Scripts\python.exe"

Write-Host "Installing requirements and test modules safely inside venv..." -ForegroundColor Cyan
& $PYTHON_EXE -m pip install --upgrade pip --quiet
& $PYTHON_EXE -m pip install -r requirements.txt --quiet
& $PYTHON_EXE -m pip install pytest pytest-cov --quiet

Write-Host "Running Tests and enforcing 90% coverage..." -ForegroundColor Cyan
& $PYTHON_EXE -m pytest tests/ --cov=scripts/ --cov-report=term-missing --cov-fail-under=90
$PytestExitCode = $LASTEXITCODE

if ($PytestExitCode -eq 0) {
    Write-Host "Tests passed! coverage of 90% reached. Total coverage shown above." -ForegroundColor Green
} else {
    Write-Host "Tests failed with exit code $PytestExitCode!" -ForegroundColor Red
}
Write-Host "Virtual environment preserved for CI cache reuse." -ForegroundColor Green
if (Get-Command deactivate -ErrorAction SilentlyContinue) {
    deactivate
}

if ($PytestExitCode -ne 0) {
    exit $PytestExitCode
}

Write-Host "Clean Exit." -ForegroundColor Green
