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
set "EDOG_DIR=%~dp0"
REM Remove trailing backslash
if "%EDOG_DIR:~-1%"=="\" set "EDOG_DIR=%EDOG_DIR:~0,-1%"

REM Step 1: Check Python
echo [1/5] Checking Python installation...
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
echo [2/5] Installing Python dependencies...
pip install playwright pywinauto --quiet --disable-pip-version-check
if errorlevel 1 (
    echo ERROR: Failed to install Python packages.
    exit /b 1
)
echo        Done.

REM Step 3: Install Playwright browsers
echo.
echo [3/5] Installing Playwright browser (Edge)...
echo        This may take a few minutes on first run...
python -m playwright install msedge --quiet 2>nul
if errorlevel 1 (
    python -m playwright install msedge
)
echo        Done.

REM Step 4: Auto-detect FLT repo and configure
echo.
echo [4/5] Auto-detecting FabricLiveTable repo...
python -c "from edog import find_flt_repo, load_config, save_config; repo = find_flt_repo(); config = load_config(); config['flt_repo_path'] = str(repo) if repo else ''; save_config(config) if repo else None; print(f'       Found: {repo}' if repo else '       Could not auto-detect.')"
if errorlevel 1 (
    echo        Could not auto-detect. You can set it later with:
    echo          edog --config -r C:\path\to\workload-fabriclivetable
)

REM Step 5: Add to PATH
echo.
echo [5/5] Adding edog to PATH...

REM Check if already in PATH
echo %PATH% | findstr /i /c:"%EDOG_DIR%" >nul
if %errorlevel%==0 (
    echo        Already in PATH.
) else (
    REM Use PowerShell to safely append to PATH without corrupting it
    powershell -NoProfile -Command "$userPath = [Environment]::GetEnvironmentVariable('Path', 'User'); if (-not $userPath -or $userPath -notlike '*%EDOG_DIR%*') { $newPath = if ($userPath) { \"$userPath;%EDOG_DIR%\" } else { '%EDOG_DIR%' }; [Environment]::SetEnvironmentVariable('Path', $newPath, 'User'); Write-Host '       Added to PATH. Restart terminal to use edog globally.' } else { Write-Host '       Already in PATH.' }"
    if errorlevel 1 (
        echo        Could not add to PATH automatically.
        echo        Add this directory to your PATH manually: %EDOG_DIR%
    )
)

echo.
echo ============================================================
echo   Setup Complete!
echo ============================================================
echo.
echo Usage:
echo   edog                  Start DevMode
echo   edog --revert         Revert all EDOG changes
echo   edog --status         Check current status
echo   edog --config         View/update configuration
echo.
echo Configure your EDOG environment IDs:
echo   edog --config -w WORKSPACE_ID -a ARTIFACT_ID -c CAPACITY_ID
echo.
echo Then start DevMode:
echo   edog
echo.
