@echo off
setlocal EnableDelayedExpansion

REM Enable ANSI escape codes (Windows 10+)
for /f %%a in ('echo prompt $E ^| cmd') do set "ESC=%%a"

REM Colors
set "RESET=%ESC%[0m"
set "BOLD=%ESC%[1m"
set "DIM=%ESC%[90m"
set "GREEN=%ESC%[32m"
set "CYAN=%ESC%[36m"
set "YELLOW=%ESC%[33m"
set "RED=%ESC%[31m"
set "BGREEN=%ESC%[1;32m"
set "BCYAN=%ESC%[1;36m"
set "BYELLOW=%ESC%[1;33m"
set "BRED=%ESC%[1;31m"
set "BG_CYAN=%ESC%[46;30m"

REM Check if running from repo root
if not exist "%~dp0edog.py" (
    echo %BRED%  ERROR%RESET%  Run this from the flt-edog-devmode directory.
    exit /b 1
)

cd /d "%~dp0"
set "EDOG_DIR=%~dp0"
if "%EDOG_DIR:~-1%"=="\" set "EDOG_DIR=%EDOG_DIR:~0,-1%"

echo.
echo   %BCYAN%+----------------------------------------------+%RESET%
echo   %BCYAN%^|%RESET%  %BOLD%=F  EDOG DevMode  %DIM%Setup%RESET%                    %BCYAN%^|%RESET%
echo   %BCYAN%^|%RESET%  %DIM%FabricLiveTable Development Tool%RESET%            %BCYAN%^|%RESET%
echo   %BCYAN%+----------------------------------------------+%RESET%
echo.

set "STEP=0"
set "TOTAL=4"
set "ERRORS=0"

REM ── Step 1: Prerequisites ──────────────────────────────────
set /a STEP+=1
echo   %BCYAN%[%STEP%/%TOTAL%]%RESET% %BOLD%Checking prerequisites%RESET%
echo.

REM Python
python --version >nul 2>&1
if errorlevel 1 (
    echo     %BRED%✘%RESET%  Python not found
    echo.
    echo     %DIM%Install Python 3.8+ from:%RESET%
    echo     %CYAN%https://www.python.org/downloads/%RESET%
    echo     %DIM%Make sure to check "Add Python to PATH"%RESET%
    echo.
    exit /b 1
)
for /f "tokens=2" %%i in ('python --version 2^>^&1') do set PYVER=%%i
echo     %BGREEN%✔%RESET%  Python %GREEN%%PYVER%%RESET%

REM .NET SDK
dotnet --version >nul 2>&1
if errorlevel 1 (
    echo     %BRED%✘%RESET%  .NET SDK not found
    echo.
    echo     %DIM%Install .NET SDK 8.0+ from:%RESET%
    echo     %CYAN%https://dotnet.microsoft.com/download%RESET%
    echo.
    exit /b 1
)
for /f "tokens=*" %%i in ('dotnet --version 2^>^&1') do set DOTNETVER=%%i
echo     %BGREEN%✔%RESET%  .NET SDK %GREEN%%DOTNETVER%%RESET%
echo.

REM ── Step 2: Python deps ────────────────────────────────────
set /a STEP+=1
echo   %BCYAN%[%STEP%/%TOTAL%]%RESET% %BOLD%Installing Python dependencies%RESET%

pip install rich --quiet --disable-pip-version-check 2>nul
if errorlevel 1 (
    echo     %BYELLOW%⚠%RESET%  %YELLOW%rich%RESET% install failed %DIM%(CLI will work without styling)%RESET%
    set /a ERRORS+=1
) else (
    echo     %BGREEN%✔%RESET%  %GREEN%rich%RESET% %DIM%installed%RESET%
)
echo.

REM ── Step 3: Build token-helper ─────────────────────────────
set /a STEP+=1
echo   %BCYAN%[%STEP%/%TOTAL%]%RESET% %BOLD%Building token-helper%RESET% %DIM%(Silent CBA auth)%RESET%

if exist "%EDOG_DIR%\scripts\token-helper\bin\Debug\net8.0\token-helper.exe" (
    echo     %BGREEN%✔%RESET%  Already built %DIM%(skipping)%RESET%
) else (
    dotnet build "%EDOG_DIR%\scripts\token-helper\token-helper.csproj" --nologo -v q >nul 2>&1
    if errorlevel 1 (
        echo     %BRED%✘%RESET%  Build failed
        echo     %DIM%  Try manually: dotnet build scripts\token-helper\token-helper.csproj%RESET%
        set /a ERRORS+=1
    ) else (
        echo     %BGREEN%✔%RESET%  Build %GREEN%successful%RESET%
    )
)
echo.

REM ── Step 4: PATH ───────────────────────────────────────────
set /a STEP+=1
echo   %BCYAN%[%STEP%/%TOTAL%]%RESET% %BOLD%Adding edog to PATH%RESET%

echo %PATH% | findstr /i /c:"%EDOG_DIR%" >nul
if %errorlevel%==0 (
    echo     %BGREEN%✔%RESET%  Already in PATH
) else (
    powershell -NoProfile -Command "$userPath = [Environment]::GetEnvironmentVariable('Path', 'User'); if (-not $userPath -or $userPath -notlike '*%EDOG_DIR%*') { $newPath = if ($userPath) { \"$userPath;%EDOG_DIR%\" } else { '%EDOG_DIR%' }; [Environment]::SetEnvironmentVariable('Path', $newPath, 'User') }" >nul 2>&1
    if errorlevel 1 (
        echo     %BYELLOW%⚠%RESET%  Could not add automatically
        echo     %DIM%  Add this to PATH manually: %EDOG_DIR%%RESET%
    ) else (
        echo     %BGREEN%✔%RESET%  Added to PATH %DIM%(restart terminal to use globally)%RESET%
    )
)
echo.

REM ── Result ─────────────────────────────────────────────────
if %ERRORS%==0 (
    echo   %BGREEN%+----------------------------------------------+%RESET%
    echo   %BGREEN%^|%RESET%  %BGREEN%✔  Setup complete!%RESET%                         %BGREEN%^|%RESET%
    echo   %BGREEN%+----------------------------------------------+%RESET%
) else (
    echo   %BYELLOW%+----------------------------------------------+%RESET%
    echo   %BYELLOW%^|%RESET%  %BYELLOW%⚠  Setup complete with %ERRORS% warning(s)%RESET%          %BYELLOW%^|%RESET%
    echo   %BYELLOW%+----------------------------------------------+%RESET%
)
echo.
echo   %BOLD%Quick Start%RESET%
echo   %DIM%─────────────────────────────────────────────%RESET%
echo   %CYAN%edog --config%RESET%      %DIM%Set workspace, artifact, capacity%RESET%
echo   %CYAN%edog%RESET%              %DIM%Start DevMode (launches FLT service)%RESET%
echo   %CYAN%edog --no-launch%RESET%   %DIM%Token management only%RESET%
echo   %CYAN%edog --revert%RESET%      %DIM%Undo all EDOG changes%RESET%
echo.

endlocal
