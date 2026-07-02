@echo off
REM Сборка conv под Windows через PyInstaller
REM Требования: Python 3.10+, pip install -e .[gui] pyinstaller

echo 🖧 Сборка conv для Windows
echo.

REM Проверяем наличие ffmpeg
if not exist ffmpeg.exe (
    echo ⚠ ffmpeg.exe не найден рядом со скриптом.
    echo    Скачайте с https://www.gyan.dev/ffmpeg/builds/ (ffmpeg-release-essentials.7z)
    echo    Или соберите без ffmpeg (будет работать только ядро, ffmpeg нужен для видео/аудио)
    echo.
    set /p INCLUDE_FFMPEG=Включить ffmpeg? (y/n):
    if /i "!INCLUDE_FFMPEG!"=="n" (
        echo ❌ ffmpeg исключён из сборки
        set FFMPEG_ARG=
    ) else (
        echo ❌ скачайте ffmpeg.exe и запустите снова
        pause
        exit /b 1
    )
) else (
    echo ✅ ffmpeg.exe найден
    set FFMPEG_ARG=--add-data "ffmpeg.exe;."
)

REM GUI-версия
echo.
echo 🖥️ Сборка GUI версии...
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

REM CLI-версия
echo.
echo ⌨️ Сборка CLI версии...
pyinstaller --onefile ^
    --name "conv-cli" ^
    --add-data "src/conv;conv" ^
    %FFMPEG_ARG% ^
    --hidden-import conv.core ^
    --hidden-import conv.cli ^
    --hidden-import conv.logger ^
    src/conv/cli.py

echo.
echo ✅ Готово! Файлы в папке dist/
echo   dist/conv.exe     — GUI версия
echo   dist/conv-cli.exe — CLI версия
pause
