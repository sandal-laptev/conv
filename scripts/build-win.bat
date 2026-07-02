@echo off
chcp 65001 >nul

REM Build conv for Windows using PyInstaller
REM Requires: Python 3.10+, pip install -e .[gui] pyinstaller

echo.
echo 🖧 Building conv for Windows
echo.

REM Check for ffmpeg.exe
if not exist "%~dp0..\ffmpeg.exe" (
    echo ⚠ ffmpeg.exe not found in project root.
    echo    Download from: https://www.gyan.dev/ffmpeg/builds/ffmpeg-release-essentials.7z
    echo    Extract ffmpeg.exe to project root folder.
    echo.
    echo NOTE: Without ffmpeg, video and audio conversion will NOT work.
    echo       Image/SVG conversion will work fine.
    echo.
    set /p INCLUDE_FFMPEG="Include ffmpeg? (y/N): "
    if /i "!INCLUDE_FFMPEG!"=="y" (
        echo ❌ Please download ffmpeg.exe first, then re-run.
        pause
        exit /b 1
    ) else (
        echo ⏭ Skipping ffmpeg
        set FFMPEG_ARG=
    )
) else (
    echo ✅ ffmpeg.exe found
    set FFMPEG_ARG=--add-data "%~dp0..\ffmpeg.exe;."
)

cd /d "%~dp0.."

REM GUI version
echo.
echo 🖥️ Building GUI version...
pyinstaller --onefile --windowed ^
    --name "conv" ^
    --add-data "src/conv;conv" ^
    %FFMPEG_ARG% ^
    --hidden-import conv.core ^
    --hidden-import conv.cli ^
    --hidden-import conv.gui ^
    --hidden-import conv.logger ^
    --collect-all customtkinter ^
    src/conv/__init__.py

REM CLI version
echo.
echo ⌨️ Building CLI version...
pyinstaller --onefile ^
    --name "conv-cli" ^
    --add-data "src/conv;conv" ^
    %FFMPEG_ARG% ^
    --hidden-import conv.core ^
    --hidden-import conv.cli ^
    --hidden-import conv.logger ^
    src/conv/cli.py

echo.
echo ✅ Done! Files in dist/ folder:
echo   dist\conv.exe     — GUI version
echo   dist\conv-cli.exe — CLI version
pause
