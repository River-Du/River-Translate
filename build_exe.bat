@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "APP_NAME=RiverTranslate"
set "PROJECT_DIR=%CD%"
set "ICON_PATH=%PROJECT_DIR%\assets\app.ico"
set "ENTRY_PATH=%PROJECT_DIR%\src\main.py"
set "VENV_PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "DIST_DIR=%PROJECT_DIR%\dist\%APP_NAME%"
set "BUILD_DIR=%PROJECT_DIR%\build"
set "PY_CMD="

if not exist "%ICON_PATH%" (
    echo [ERROR] Missing icon file: %ICON_PATH%
    echo Put a multi-size Windows .ico file at assets\app.ico, then run this script again.
    exit /b 1
)

if not exist "%ENTRY_PATH%" (
    echo [ERROR] Missing entry file: %ENTRY_PATH%
    exit /b 1
)

if exist "%VENV_PY%" (
    "%VENV_PY%" -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if errorlevel 1 (
        echo [ERROR] Existing .venv Python is older than 3.8 or broken. Delete .venv and install Python 3.8+.
        exit /b 1
    )
) else (
    py -3 -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
    if not errorlevel 1 set "PY_CMD=py -3"

    if not defined PY_CMD (
        python -c "import sys; raise SystemExit(0 if sys.version_info >= (3, 8) else 1)" >nul 2>nul
        if not errorlevel 1 set "PY_CMD=python"
    )

    if not defined PY_CMD (
        echo [ERROR] Python 3.8+ was not found.
        echo Please install Python 3.8+ from https://www.python.org/ and enable Add python.exe to PATH.
        exit /b 1
    )

    echo [INFO] Creating virtual environment with !PY_CMD!...
    !PY_CMD! -m venv .venv
    if errorlevel 1 (
        echo [ERROR] Failed to create .venv.
        exit /b 1
    )
)

"%VENV_PY%" -m pip --version >nul 2>nul
if errorlevel 1 (
    echo [INFO] Bootstrapping pip...
    "%VENV_PY%" -m ensurepip --upgrade
    if errorlevel 1 exit /b 1
)

"%VENV_PY%" -m PyInstaller --version >nul 2>nul
if errorlevel 1 (
    echo [INFO] Installing PyInstaller...
    "%VENV_PY%" -m pip install -U pip pyinstaller
    if errorlevel 1 exit /b 1
) else (
    echo [INFO] PyInstaller already installed in .venv.
)

if not exist "%DIST_DIR%" mkdir "%DIST_DIR%"
if exist "%DIST_DIR%\%APP_NAME%.exe" (
    del /f /q "%DIST_DIR%\%APP_NAME%.exe"
    if exist "%DIST_DIR%\%APP_NAME%.exe" (
        echo [ERROR] Cannot replace %DIST_DIR%\%APP_NAME%.exe
        echo Close the running app or any program using the exe, then run this script again.
        exit /b 1
    )
)
if exist "%BUILD_DIR%\%APP_NAME%" rmdir /s /q "%BUILD_DIR%\%APP_NAME%"

echo [INFO] Building one-file executable...
"%VENV_PY%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    --onefile ^
    --name "%APP_NAME%" ^
    --icon "%ICON_PATH%" ^
    --add-data "%ICON_PATH%;assets" ^
    --distpath "%DIST_DIR%" ^
    --workpath "%BUILD_DIR%" ^
    --specpath "%BUILD_DIR%" ^
    "%ENTRY_PATH%"
if errorlevel 1 exit /b 1

echo.
echo [OK] Build finished: %DIST_DIR%\%APP_NAME%.exe
echo First run will create: %DIST_DIR%\user_data\config.json and history.json
echo.
pause