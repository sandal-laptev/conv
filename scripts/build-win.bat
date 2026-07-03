@echo off
chcp 65001 >nul

REM Build conv for Windows using PyInstaller
REM Requires: Python 3.10+, pip install -e .[gui] pyinstaller

echo.
echo 🖧 Building conv for Windows
echo.

cd /d "%~dp0.."
set EXTRA_DATA=

REM Check for ffmpeg.exe
if exist "%~dp0..\ffmpeg.exe" (
    echo ✅ ffmpeg.exe found — будет включён в сборку
    set EXTRA_DATA=--add-data "ffmpeg.exe;."
) else (
    echo ⚠ ffmpeg.exe not found in project root.
    echo    Download: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z
    echo    (извлеките ffmpeg.exe в корень проекта)
    echo.
)

REM Check for ffprobe.exe
if exist "%~dp0..\ffprobe.exe" (
    echo ✅ ffprobe.exe found — будет включён в сборку
    set EXTRA_DATA=%EXTRA_DATA% --add-data "ffprobe.exe;."
) else (
    echo ℹ ffprobe.exe not found — медиа-инфо будет через ffmpeg -i
    echo    (можно положить ffprobe.exe рядом с ffmpeg.exe)
    echo.
)

REM GUI version
echo.
echo 🖥️ Building GUI version...
pyinstaller --onefile --windowed ^
    --name "conv" ^
    --add-data "src/conv;conv" ^
    %EXTRA_DATA% ^
    --hidden-import conv.core ^
    --hidden-import conv.cli ^
    --hidden-import conv.gui ^
    --hidden-import conv.gui.app ^
    --hidden-import conv.gui.theme ^
    --hidden-import conv.gui.controllers.conversion ^
    --hidden-import conv.gui.widgets.drop_zone ^
    --hidden-import conv.gui.widgets.params ^
    --hidden-import conv.gui.widgets.file_list ^
    --hidden-import conv.gui.widgets.preview ^
    --hidden-import conv.logger ^
    --collect-all customtkinter ^
    scripts\entry_gui.py

REM CLI version
echo.
echo ⌨️ Building CLI version...
pyinstaller --onefile ^
    --name "conv-cli" ^
    --add-data "src/conv;conv" ^
    %EXTRA_DATA% ^
    --hidden-import conv.core ^
    --hidden-import conv.cli ^
    --hidden-import conv.logger ^
    src/conv/cli.py

echo.
echo ✅ Done! Files in dist/ folder:
echo   dist\conv.exe     — GUI version
echo   dist\conv-cli.exe — CLI version
pause
