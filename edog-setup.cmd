@echo off
REM ============================================================
REM FLT EDOG DevMode - Setup Script
REM 
REM This script sets up the EDOG DevMode tool for first-time use.
REM Run this once after cloning the repo.
REM
REM Requirements: Python 3.8+, .NET SDK 8.0+
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

REM Check .NET SDK
echo        Checking .NET SDK...
dotnet --version >nul 2>&1
if errorlevel 1 (
    echo.
    echo ERROR: .NET SDK is not installed or not in PATH.
    echo.
    echo Please install .NET SDK 8.0+ from:
    echo   https://dotnet.microsoft.com/download
    echo.
    exit /b 1
)

for /f "tokens=*" %%i in ('dotnet --version 2^>^&1') do set DOTNETVER=%%i
echo        Found .NET SDK %DOTNETVER%

REM Step 2: Install Python dependencies
echo.
echo [2/4] Installing Python dependencies...
pip install rich --quiet --disable-pip-version-check
if errorlevel 1 (
    echo WARNING: Failed to install 'rich' library. CLI will work but without styling.
)
echo        Done.

REM Step 3: Build token-helper (Silent CBA)
echo.
echo [3/4] Building token-helper (Silent CBA authentication)...
if exist "%EDOG_DIR%\scripts\token-helper\bin\Debug\net8.0\token-helper.exe" (
    echo        Already built.
) else (
    dotnet build "%EDOG_DIR%\scripts\token-helper\token-helper.csproj" --nologo -v q
    if errorlevel 1 (
        echo.
        echo WARNING: token-helper build failed.
        echo          You can build it manually:
        echo            dotnet build scripts\token-helper\token-helper.csproj
        echo.
    ) else (
        echo        Build successful.
    )
)

REM Step 4: Add to PATH
echo.
echo [4/4] Adding edog to PATH...

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
echo   edog                  Start DevMode (auto-launches FLT service)
echo   edog --no-launch      Token management only
echo   edog --revert         Revert all EDOG changes
echo   edog --status         Check current status
echo   edog --config         View/update configuration
echo   edog --logs           Open web log viewer
echo.
echo Configure your EDOG environment IDs:
echo   edog --config -w WORKSPACE_ID -a ARTIFACT_ID -c CAPACITY_ID
echo.
echo Then start DevMode:
echo   edog
echo.
