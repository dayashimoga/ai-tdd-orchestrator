@echo off
REM ============================================================
REM  AI TDD Orchestrator - Automated Test Runner
REM  Creates a virtual environment, installs dependencies,
REM  runs tests with coverage, and cleans up afterward.
REM ============================================================

setlocal enabledelayedexpansion

set "PROJECT_DIR=%~dp0"
set "VENV_DIR=%PROJECT_DIR%.test_venv"
set "COVERAGE_MIN=90"

echo.
echo ============================================
echo   AI TDD Orchestrator - Test Runner
echo ============================================
echo.

REM Step 1: Create virtual environment
echo [1/5] Creating virtual environment...
python -m venv "%VENV_DIR%"
if errorlevel 1 (
    echo ERROR: Failed to create virtual environment
    exit /b 1
)

REM Step 2: Activate and install dependencies
echo [2/5] Installing dependencies...
call "%VENV_DIR%\Scripts\activate.bat"
pip install --quiet --disable-pip-version-check -r "%PROJECT_DIR%requirements.txt"
if errorlevel 1 (
    echo ERROR: Failed to install dependencies
    goto :cleanup
)

REM Step 3: Run tests with coverage
echo [3/5] Running tests with coverage...
echo.
python -m pytest tests/ --cov=scripts/ --cov-report=term-missing --cov-fail-under=%COVERAGE_MIN% -q --tb=short
set "TEST_EXIT=%errorlevel%"
echo.

REM Step 4: Report results
echo [4/5] Test Results:
if %TEST_EXIT% equ 0 (
    echo   Status: ALL TESTS PASSED
    echo   Coverage: Above %COVERAGE_MIN%%
) else (
    echo   Status: TESTS FAILED (exit code: %TEST_EXIT%)
)

REM Step 5: Cleanup
:cleanup
echo [5/5] Cleaning up virtual environment...
call deactivate 2>nul
rmdir /s /q "%VENV_DIR%" 2>nul
echo   Virtual environment removed.
echo.
echo ============================================
echo   Done!
echo ============================================

exit /b %TEST_EXIT%
