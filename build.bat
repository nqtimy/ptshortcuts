@echo off
echo ============================================
echo  PT Shortcuts - Build .exe with PyInstaller
echo ============================================
echo.

REM Detect Python command
where python >nul 2>nul
if %errorlevel%==0 (
    set PYTHON=python
) else (
    where py >nul 2>nul
    if %errorlevel%==0 (
        set PYTHON=py
    ) else (
        echo ERREUR: Python introuvable. Installez Python et ajoutez-le au PATH.
        pause
        exit /b 1
    )
)

echo Utilisation de: %PYTHON%
echo.

REM Check if the exe is already running
tasklist /FI "IMAGENAME eq PTShortcuts.exe" 2>nul | find /I "PTShortcuts.exe" >nul
if %errorlevel%==0 (
    echo ERREUR: PTShortcuts.exe est en cours d'execution.
    echo Fermez-le avant de lancer le build.
    echo.
    pause
    exit /b 1
)

REM Install dependencies
echo Installation des dependances...
%PYTHON% -m pip install -r requirements.txt
if %errorlevel% neq 0 (
    echo ERREUR: Impossible d'installer les dependances.
    pause
    exit /b 1
)

REM Install PyInstaller if needed
%PYTHON% -m pip install pyinstaller
if %errorlevel% neq 0 (
    echo ERREUR: Impossible d'installer PyInstaller.
    pause
    exit /b 1
)

echo.
echo Building standalone .exe ...
echo.

REM Include Supabase config if present (embeds the anon key in the exe)
set SUPABASE_DATA=
if exist supabase_config.json (
    set SUPABASE_DATA=--add-data "supabase_config.json;."
)

%PYTHON% -m PyInstaller ^
    --onefile ^
    --windowed ^
    --name "PTShortcuts" ^
    --manifest ptshortcuts.manifest ^
    --add-data "shortcuts;shortcuts" ^
    --add-data "assets;assets" ^
    %SUPABASE_DATA% ^
    --hidden-import pynput.keyboard._win32 ^
    --hidden-import pynput.mouse._win32 ^
    main.py

if %errorlevel% neq 0 (
    echo.
    echo ============================================
    echo  ERREUR de build. Verifiez les logs ci-dessus.
    echo ============================================
    pause
    exit /b 1
)

echo.
echo ============================================
echo  Build OK! Executable: dist\PTShortcuts.exe
echo ============================================
pause
