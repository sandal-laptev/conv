@echo off
chcp 65001 >nul

REM Build MO Kolomyagi Media Converter (Qt6 GUI) for Windows
REM Requires: Python 3.10+, pip install -e .[gui-qt,heif] pyinstaller

echo.
echo 🖧 Building MO Kolomyagi Media Converter (Qt6)
echo.

cd /d "%~dp0.."

REM ── ffmpeg / ffprobe (опционально) ──
set EXTRA_DATA=

if exist "ffmpeg.exe" (
    echo ✅ ffmpeg.exe found
    set EXTRA_DATA=--add-data "ffmpeg.exe;."
) else (
    echo ⚠ ffmpeg.exe not found in project root.
    echo    Download: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z
    echo    (извлеките ffmpeg.exe в корень проекта)
    echo.
)

if exist "ffprobe.exe" (
    echo ✅ ffprobe.exe found
    set EXTRA_DATA=%EXTRA_DATA% --add-data "ffprobe.exe;."
) else (
    echo ℹ ffprobe.exe not found — медиа-инфо будет через ffmpeg -i
    echo.
)

REM ── pillow-heif ──
pip show pillow-heif >nul 2>&1
if %errorlevel% neq 0 (
    echo 📦 Installing pillow-heif...
    pip install pillow-heif>=1.0.0
) else (
    echo ✅ pillow-heif already installed
)

REM ── Сборка Qt6 GUI ──
echo.
echo 🖥️ Building Qt6 GUI version...
echo.

python -m PyInstaller --onefile --windowed ^
    --name "MO-Kolomyagi-Media-Converter" ^
    --icon "src\conv\gui\resources\icon.ico" ^
    --add-data "src/conv;conv" ^
    --add-data "src\conv\gui\resources\icon.ico;conv\gui\resources" ^
    %EXTRA_DATA% ^
    --hidden-import conv.core ^
    --hidden-import conv.cli ^
    --hidden-import conv.logger ^
    --hidden-import conv.history ^
    --hidden-import conv.gui ^
    --hidden-import conv.gui.app ^
    --hidden-import conv.gui.theme ^
    --hidden-import conv.gui.i18n ^
    --hidden-import conv.gui.about ^
    --hidden-import conv.gui.controllers.conversion ^
    --hidden-import conv.gui.widgets.file_table ^
    --hidden-import conv.gui.widgets.params ^
    --hidden-import conv.gui.widgets.preview ^
    --hidden-import conv.gui.widgets.timeline ^
    --hidden-import PySide6.QtMultimedia ^
    --hidden-import PySide6.QtMultimediaWidgets ^
    --collect-data PySide6 ^
    --collect-binaries PySide6 ^
    --collect-all pillow_heif ^
    scripts\entry_gui.py

REM ── CLI версия ──
echo.
echo ⌨️ Building CLI version...
echo.

python -m PyInstaller --onefile ^
    --name "conv-cli" ^
    --add-data "src/conv;conv" ^
    %EXTRA_DATA% ^
    --hidden-import conv.core ^
    --hidden-import conv.cli ^
    --hidden-import conv.logger ^
    --hidden-import conv.history ^
    scripts\entry_gui.py

echo.
echo ✅ Done!
echo.
echo Files in dist\:
echo   dist\MO-Kolomyagi-Media-Converter.exe — Qt6 GUI
echo   dist\conv-cli.exe                     — CLI
echo.

pause
