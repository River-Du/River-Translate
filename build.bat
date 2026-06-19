@echo off
setlocal EnableExtensions EnableDelayedExpansion

cd /d "%~dp0"

set "APP_NAME=River Translate"
set "DEFAULT_MODE=onedir"
set "PROJECT_DIR=%CD%"
set "ICON_PATH=%PROJECT_DIR%\assets\app.ico"
set "ENTRY_PATH=%PROJECT_DIR%\src\main.py"
set "VENV_PY=%PROJECT_DIR%\.venv\Scripts\python.exe"
set "DIST_ROOT=%PROJECT_DIR%\dist"
set "RELEASE_DIR=%DIST_ROOT%\%APP_NAME%"
set "BUILD_DIR=%PROJECT_DIR%\build"
set "PY_CMD="
set "BUILD_MODE=%~1"

if "%BUILD_MODE%"=="" set "BUILD_MODE=%DEFAULT_MODE%"

if /I "%BUILD_MODE%"=="onefile" (
    set "BUILD_MODE=onefile"
    set "PYINSTALLER_MODE=--onefile"
    set "DIST_PATH=%RELEASE_DIR%"
) else if /I "%BUILD_MODE%"=="onedir" (
    set "BUILD_MODE=onedir"
    set "PYINSTALLER_MODE=--onedir"
    set "DIST_PATH=%DIST_ROOT%"
) else (
    echo [ERROR] Unknown build mode: %BUILD_MODE%
    echo Usage: build.bat [onefile^|onedir]
    echo Default mode: %DEFAULT_MODE%
    exit /b 1
)

set "OUTPUT_EXE=%RELEASE_DIR%\%APP_NAME%.exe"
set "OUTPUT_INTERNAL=%RELEASE_DIR%\_internal"

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

echo [INFO] Cleaning previous build and release output...
if exist "%BUILD_DIR%" rmdir /s /q "%BUILD_DIR%"

if exist "%DIST_ROOT%" rmdir /s /q "%DIST_ROOT%"

echo [INFO] Building %BUILD_MODE% executable...
"%VENV_PY%" -m PyInstaller ^
    --noconfirm ^
    --clean ^
    --windowed ^
    %PYINSTALLER_MODE% ^
    --name "%APP_NAME%" ^
    --icon "%ICON_PATH%" ^
    --add-data "%ICON_PATH%;assets" ^
    --distpath "%DIST_PATH%" ^
    --workpath "%BUILD_DIR%" ^
    --specpath "%BUILD_DIR%" ^
    "%ENTRY_PATH%"
if errorlevel 1 exit /b 1

if not exist "%OUTPUT_EXE%" (
    echo [ERROR] Build output was not found: %OUTPUT_EXE%
    exit /b 1
)

if /I "%BUILD_MODE%"=="onedir" (
    if not exist "%OUTPUT_INTERNAL%" (
        echo [ERROR] onedir runtime folder was not found: %OUTPUT_INTERNAL%
        exit /b 1
    )
)

echo.
echo [OK] Build finished: %OUTPUT_EXE%
if /I "%BUILD_MODE%"=="onedir" echo Runtime files are in: %OUTPUT_INTERNAL%
echo App data will be created on launch: %RELEASE_DIR%\user_data\config.json and history.json
echo.
pause
