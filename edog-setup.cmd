@echo off
REM ============================================================
REM FLT EDOG DevMode - Setup Script
REM 
REM This script sets up the EDOG DevMode tool for first-time use.
REM Run this once after cloning the repo.
REM ============================================================

echo.
echo ============================================================
echo   FLT EDOG DevMode - Setup
echo ============================================================
echo.

REM Check if running from repo root
if not exist "%~dp0edog.py" (
    echo ERROR: Please run this script from the flt-edog-devmode directory.
    echo        Could not find edog.py
    exit /b 1
)

cd /d "%~dp0"

REM Step 1: Check Python
echo [1/4] Checking Python installation...
python --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: Python is not installed or not in PATH.
    echo.
    echo Please install Python 3.8+ from:
    echo   https://www.python.org/downloads/
    echo.
    echo Make sure to check "Add Python to PATH" during installation.
    echo.
    exit /b 1
)

for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo        Found Python %PYVER%

REM Step 2: Install Python dependencies
echo.
echo [2/4] Installing Python dependencies...
pip install playwright asyncio --quiet --disable-pip-version-check
if errorlevel 1 (
    echo ERROR: Failed to install Python packages.
    exit /b 1
)
echo        Done.

REM Step 3: Install Playwright browsers
echo.
echo [3/4] Installing Playwright browser (Chromium)...
echo        This may take a few minutes on first run...
python -m playwright install chromium --quiet 2>nul
if errorlevel 1 (
    python -m playwright install chromium
)
echo        Done.

REM Step 4: Configure
echo.
echo [4/4] Configuration...

if exist "%USERPROFILE%\.edog-config.json" (
    echo        Config file already exists at: %USERPROFILE%\.edog-config.json
    echo        Run "edog --config" to view or update settings.
) else (
    echo        No config file found. Creating default config...
    python edog.py --config >nul 2>&1
    echo        Config created at: %USERPROFILE%\.edog-config.json
    echo.
    echo        IMPORTANT: You need to set your workspace/lakehouse/capacity IDs:
    echo          edog --config -w YOUR_WORKSPACE_ID -l YOUR_LAKEHOUSE_ID -c YOUR_CAPACITY_ID
)

echo.
echo ============================================================
echo   Setup Complete!
echo ============================================================
echo.
echo Usage:
echo   edog                  Start DevMode (fetch token, apply changes, auto-refresh)
echo   edog --revert         Revert all EDOG changes
echo   edog --status         Check current status
echo   edog --config         View/update configuration
echo.
echo First time? Configure your IDs:
echo   edog --config -w WORKSPACE_ID -l LAKEHOUSE_ID -c CAPACITY_ID
echo.
echo Then start DevMode:
echo   edog
echo.
