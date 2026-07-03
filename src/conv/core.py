"""
conv — ядро конвертации медиафайлов.
Лицензия: GPLv3

Архитектура:
  Converter        — главный класс с методом .convert()
  ConvertRequest   — параметры конвертации одного файла
  ConvertResult    — результат конвертации одного файла
"""

from __future__ import annotations

import os
import subprocess
import sys
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import dataclass, field
from pathlib import Path
from typing import Callable, Optional, Protocol

from conv.logger import get_logger

log = get_logger("conv.core")

__version__ = "2.0.0"

# ──────────────────────────────────────────────────────────────────────────────
# Форматы файлов
# ──────────────────────────────────────────────────────────────────────────────

IMAGE_INPUT: set[str] = {
    '.jpg', '.jpeg', '.png', '.bmp', '.gif', '.tiff', '.tif',
    '.webp', '.heic', '.heif', '.ico', '.ppm', '.pgm', '.pbm',
    '.xbm', '.xpm', '.dds', '.icns',
}

SVG_INPUT: set[str] = {'.svg', '.svgz'}

VIDEO_INPUT: set[str] = {
    '.mp4', '.avi', '.mkv', '.mov', '.wmv', '.flv', '.webm',
    '.mpeg', '.mpg', '.ogv', '.m4v', '.3gp', '.3g2', '.m2ts',
    '.mts', '.vob', '.ts', '.rm', '.rmvb', '.asf', '.drc',
    '.gifv', '.mxf', '.nsv', '.svi', '.viv', '.yuv', '.roq',
    '.m2v', '.mpv', '.mpe', '.mng', '.qt', '.f4v', '.f4p',
    '.f4a', '.f4b',
    # raw-потоки (без контейнера)
    '.h264', '.264', '.avc',
    '.h265', '.265', '.hevc',
}

AUDIO_INPUT: set[str] = {
    '.mp3', '.wav', '.flac', '.ogg', '.oga', '.m4a', '.m4b',
    '.opus', '.aac', '.wma', '.aiff', '.alac', '.ape', '.au',
    '.dss', '.gsm', '.mmf', '.ra', '.raw', '.tta', '.voc',
    '.vox', '.wv', '.3gp', '.aa', '.cda', '.pcm',
}

ALL_INPUT: set[str] = IMAGE_INPUT | SVG_INPUT | VIDEO_INPUT | AUDIO_INPUT

OUTPUT_FORMATS: dict[str, dict] = {
    # images
    'jpg':   {'mime': 'image', 'ext': '.jpg',   'desc': 'JPEG'},
    'jpeg':  {'mime': 'image', 'ext': '.jpg',   'desc': 'JPEG'},
    'png':   {'mime': 'image', 'ext': '.png',   'desc': 'PNG'},
    'webp':  {'mime': 'image', 'ext': '.webp',  'desc': 'WebP'},
    'bmp':   {'mime': 'image', 'ext': '.bmp',   'desc': 'BMP'},
    'tiff':  {'mime': 'image', 'ext': '.tiff',  'desc': 'TIFF'},
    # video
    'mp4':   {'mime': 'video', 'ext': '.mp4',   'desc': 'MP4 (H.264)'},
    'mkv':   {'mime': 'video', 'ext': '.mkv',   'desc': 'Matroska'},
    'avi':   {'mime': 'video', 'ext': '.avi',   'desc': 'AVI'},
    'webm':  {'mime': 'video', 'ext': '.webm',  'desc': 'WebM'},
    # audio
    'mp3':   {'mime': 'audio', 'ext': '.mp3',   'desc': 'MP3'},
    'flac':  {'mime': 'audio', 'ext': '.flac',  'desc': 'FLAC'},
    'ogg':   {'mime': 'audio', 'ext': '.ogg',   'desc': 'OGG Vorbis'},
    'wav':   {'mime': 'audio', 'ext': '.wav',   'desc': 'WAV'},
    'aac':   {'mime': 'audio', 'ext': '.m4a',   'desc': 'AAC'},
    'opus':  {'mime': 'audio', 'ext': '.opus',  'desc': 'Opus'},
}

DEFAULT_OUTPUT: dict[str, str] = {
    'image': 'jpg',
    'video': 'mp4',
    'audio': 'mp3',
}


# ──────────────────────────────────────────────────────────────────────────────
# Пресеты качества
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class QualityPreset:
    """Пресет качества — именованный набор параметров."""
    name: str
    label: str
    quality: int        # 1–100
    max_size: int       # px, 0 = оригинал
    description: str


QUALITY_PRESETS: dict[str, QualityPreset] = {
    'max': QualityPreset(
        name='max', label='Макс.', quality=95, max_size=0,
        description='Максимальное качество, без сжатия',
    ),
    'web': QualityPreset(
        name='web', label='Для веба', quality=80, max_size=1920,
        description='Оптимизация для веба, до 1920px',
    ),
    'fast': QualityPreset(
        name='fast', label='Быстрый', quality=60, max_size=1024,
        description='Быстрая конвертация, меньший размер',
    ),
}


def detect_mime(ext: str) -> str:
    ext = ext.lower()
    if ext in IMAGE_INPUT | SVG_INPUT:
        return 'image'
    if ext in VIDEO_INPUT:
        return 'video'
    if ext in AUDIO_INPUT:
        return 'audio'
    return ''


def resolve_format(output_format: str, input_ext: str) -> str:
    """Определяет выходной формат."""
    if output_format:
        return output_format
    mime = detect_mime(input_ext)
    return DEFAULT_OUTPUT.get(mime, 'jpg')


# ──────────────────────────────────────────────────────────────────────────────
# Типы данных
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class ConvertRequest:
    """Параметры конвертации одного файла."""
    input_path: Path
    output_dir: Path
    output_format: str = ''          # автоопределение если пусто
    quality: int = 85
    max_size: int = 0                # 0 = оригинал, для изображений
    preserve_structure: bool = False # сохранять подпапки при рекурсии
    dry_run: bool = False

    @property
    def rel_dir(self) -> Path:
        """Относительная подпапка (для preserve_structure)."""
        return Path('')

    def output_name(self) -> str:
        ext = self.input_ext
        fmt = resolve_format(self.output_format, ext)
        out_ext = OUTPUT_FORMATS.get(fmt, {}).get('ext', '.bin')

        # SVG → PNG по умолчанию, иначе в указанный image-формат
        if ext in SVG_INPUT and detect_mime(ext) == 'image' and fmt not in ['png', 'jpg', 'jpeg', 'webp']:
            out_ext = '.png'

        return f"{self.input_path.stem}{out_ext}"

    def output_path(self) -> Path:
        if self.preserve_structure and self.rel_dir:
            return self.output_dir / self.rel_dir / self.output_name()
        return self.output_dir / self.output_name()

    @property
    def input_ext(self) -> str:
        return self.input_path.suffix.lower()


@dataclass
class ConvertResult:
    """Результат конвертации одного файла."""
    request: ConvertRequest
    output_path: Optional[Path] = None
    ok: bool = False
    error: str = ''
    took: float = 0.0
    src_size: int = 0
    dst_size: int = 0

    @property
    def ratio(self) -> float:
        return self.dst_size / self.src_size if self.src_size else 1.0

    @property
    def input_name(self) -> str:
        return self.request.input_path.name

    @property
    def output_name(self) -> str:
        return self.output_path.name if self.output_path else ''

    def fmt_src_size(self) -> str:
        return _fmt_size(self.src_size)

    def fmt_dst_size(self) -> str:
        return _fmt_size(self.dst_size)

    def fmt_took(self) -> str:
        return _fmt_time(self.took)


# Callback для прогресса
ProgressCallback = Callable[[int, int, ConvertResult], None]


# ──────────────────────────────────────────────────────────────────────────────
# Медиа-информация
# ──────────────────────────────────────────────────────────────────────────────

@dataclass
class MediaInfo:
    """Информация о медиафайле (из ffprobe)."""
    duration: float = 0.0       # секунды
    bit_rate: int = 0            # бит/с
    video_codec: str = ''       # h264, hevc, vp9...
    audio_codec: str = ''       # aac, mp3, opus...
    width: int = 0
    height: int = 0
    fps: float = 0.0
    audio_channels: int = 0
    sample_rate: int = 0

    @property
    def has_video(self) -> bool:
        return bool(self.video_codec)

    @property
    def has_audio(self) -> bool:
        return bool(self.audio_codec)

    @property
    def resolution_str(self) -> str:
        if self.width and self.height:
            return f"{self.width}\u00d7{self.height}"
        return ""

    def fmt_duration(self) -> str:
        return _fmt_time(self.duration)

    def fmt_bitrate(self) -> str:
        if self.bit_rate:
            return f"{_fmt_size(self.bit_rate)}/с"
        return ""


def get_media_info(path: Path) -> MediaInfo:
    """Извлекает информацию о медиафайле.

    Сначала пытается через ffprobe (JSON). Если ffprobe не найден —
    парсит вывод ffmpeg -i (stderr).

    Возвращает MediaInfo с доступными полями. Если ни один инструмент
    не доступен — все поля будут пустыми/нулевыми.
    """
    info = MediaInfo()

    ffprobe = Converter._tool_path('ffprobe')
    ffmpeg = Converter._tool_path('ffmpeg')

    # ── Попытка 1: ffprobe ──
    try:
        r = subprocess.run(
            [ffprobe, '-v', 'error',
             '-of', 'json',
             '-show_entries',
             'stream=codec_type,codec_name,width,height,'
             'r_frame_rate,channels,sample_rate',
             '-show_entries', 'format=duration,bit_rate',
             str(path)],
            capture_output=True, text=True, timeout=30,
        )
        if r.returncode == 0 and r.stdout.strip():
            import json
            data = json.loads(r.stdout)

            # Формат
            fmt = data.get('format', {})
            dur = fmt.get('duration')
            if dur:
                info.duration = float(dur)
            br = fmt.get('bit_rate')
            if br:
                info.bit_rate = int(br)

            # Потоки
            for stream in data.get('streams', []):
                ctype = stream.get('codec_type')
                if ctype == 'video':
                    info.video_codec = stream.get('codec_name', '')
                    info.width = stream.get('width', 0) or 0
                    info.height = stream.get('height', 0) or 0
                    fps_str = stream.get('r_frame_rate', '')
                    if fps_str and '/' in fps_str:
                        try:
                            num, den = fps_str.split('/')
                            info.fps = float(num) / float(den) if float(den) > 0 else 0
                        except (ValueError, ZeroDivisionError):
                            pass
                elif ctype == 'audio':
                    info.audio_codec = stream.get('codec_name', '')
                    info.audio_channels = stream.get('channels', 0) or 0
                    sr = stream.get('sample_rate')
                    if sr:
                        info.sample_rate = int(sr)

            return info  # ffprobe успешно отработал

    except FileNotFoundError:
        log.debug("ffprobe не найден, пробуем ffmpeg -i")
    except Exception as ex:
        log.debug("ffprobe error: %s", ex)

    # ── Попытка 2: ffmpeg -i (парсим stderr) ──
    try:
        r = subprocess.run(
            [ffmpeg, '-i', str(path)],
            capture_output=True, text=True, timeout=30,
        )
        stderr = r.stderr

        # Длительность: Duration: 00:01:30.00
        import re
        m = re.search(r'Duration:\s*(\d+):(\d+):([\d.]+)', stderr)
        if m:
            h, min_, s = float(m.group(1)), float(m.group(2)), float(m.group(3))
            info.duration = h * 3600 + min_ * 60 + s

        # Битрейт: bitrate: 1250 kb/s
        m = re.search(r'bitrate:\s*([\d]+)\s*kb/s', stderr)
        if m:
            info.bit_rate = int(m.group(1)) * 1000

        # Потоки
        for line in stderr.split('\n'):
            # Видео: Stream #0:0: Video: h264 (High), yuv420p, 1920x1080 ...
            m = re.match(
                r'\s*Stream\s+#\d+:\d+.*?:\s*Video:\s*(\S+)',
                line, re.IGNORECASE,
            )
            if m:
                info.video_codec = m.group(1).lower().split('(')[0].strip()
                # Разрешение: 1920x1080
                res_m = re.search(r'(\d+)x(\d+)', line)
                if res_m:
                    info.width = int(res_m.group(1))
                    info.height = int(res_m.group(2))
                # FPS: 25 fps
                fps_m = re.search(r'([\d.]+)\s*fps', line)
                if fps_m:
                    info.fps = float(fps_m.group(1))
                continue

            # Аудио: Stream #0:1: Audio: aac, 48000 Hz, stereo
            m = re.match(
                r'\s*Stream\s+#\d+:\d+.*?:\s*Audio:\s*(\S+)',
                line, re.IGNORECASE,
            )
            if m:
                info.audio_codec = m.group(1).lower()
                sr_m = re.search(r'(\d+)\s*Hz', line)
                if sr_m:
                    info.sample_rate = int(sr_m.group(1))
                if 'mono' in line:
                    info.audio_channels = 1
                elif 'stereo' in line:
                    info.audio_channels = 2
                elif '5.1' in line or '6ch' in line:
                    info.audio_channels = 6
                elif '7.1' in line or '8ch' in line:
                    info.audio_channels = 8

    except FileNotFoundError:
        log.debug("ffmpeg не найден — медиа-инфо недоступна")
    except Exception as ex:
        log.debug("ffmpeg -i error: %s", ex)

    return info


# ──────────────────────────────────────────────────────────────────────────────
# Ядро конвертации
# ──────────────────────────────────────────────────────────────────────────────

class Converter:
    """
    Главный класс конвертации.

    Пример:
        c = Converter(workers=4)
        req = ConvertRequest(Path('video.mp4'), Path('out'), output_format='mp4')
        result = c.convert_one(req)
        print(result.ok, result.fmt_took())
    """

    def __init__(self, workers: int = 0):
        self.workers = workers or min(os.cpu_count() or 4, 8)
        self._pil_available: Optional[bool] = None
        self._heif_available: Optional[bool] = None
        log.info("Converter инициализирован, workers=%d", self.workers)

    # ── Проверка инструментов ────────────────────────────────────────────────

    @property
    def has_pil(self) -> bool:
        if self._pil_available is None:
            try:
                from PIL import Image  # noqa
                self._pil_available = True
            except ImportError:
                self._pil_available = False
        return self._pil_available

    @property
    def has_heif(self) -> bool:
        if self._heif_available is None:
            try:
                from pillow_heif import register_heif_opener  # noqa
                register_heif_opener()
                self._heif_available = True
            except ImportError:
                self._heif_available = False
        return self._heif_available

    def check_tools(self) -> dict[str, bool]:
        """Проверка доступности инструментов.

        Ищет исполняемые файлы в PATH и в директории рядом с приложением
        (для поддержки bundled-версий в PyInstaller).
        """
        tools = {
            'ffmpeg':      self._which('ffmpeg'),
            'ffprobe':     self._which('ffprobe'),
            'rsvg_convert': self._which('rsvg-convert'),
            'pil':          self.has_pil,
            'pillow_heif':  self.has_heif,
        }

        # Если не нашли в PATH — проверяем рядом с exe (PyInstaller bundle)
        if not tools['ffmpeg']:
            tools['ffmpeg'] = self._which_bundled('ffmpeg')
        if not tools['ffprobe']:
            tools['ffprobe'] = self._which_bundled('ffprobe')
        if not tools['rsvg_convert']:
            tools['rsvg_convert'] = self._which_bundled('rsvg-convert')

        log.info("Проверка инструментов: %s", tools)
        return tools

    @staticmethod
    def _which(name: str) -> bool:
        try:
            subprocess.run([name, '-version'], capture_output=True, timeout=5)
            return True
        except (FileNotFoundError, subprocess.TimeoutExpired):
            return False

    @staticmethod
    def _which_bundled(name: str) -> bool:
        """Ищет bundled-инструмент рядом с exe / в корне проекта."""
        dirs = []
        # PyInstaller: все файлы в sys._MEIPASS
        if getattr(sys, 'frozen', False):
            dirs.append(Path(sys._MEIPASS))
        else:
            # Рядом с запускаемым скриптом
            dirs.append(Path(sys.argv[0]).parent)
            # Корень проекта (родитель src/conv/)
            script_dir = Path(__file__).resolve().parent.parent.parent
            if script_dir not in dirs:
                dirs.append(script_dir)

        for base in dirs:
            for candidate in [
                base / name,
                base / f"{name}.exe",
                base / 'bin' / name,
                base / 'bin' / f"{name}.exe",
            ]:
                if candidate.exists():
                    try:
                        subprocess.run([str(candidate), '-version'],
                                       capture_output=True, timeout=5)
                        return True
                    except (FileNotFoundError, subprocess.TimeoutExpired):
                        continue
        return False

    # ── Одиночная конвертация ────────────────────────────────────────────────

    def convert_one(self, req: ConvertRequest) -> ConvertResult:
        """Конвертирует один файл."""
        start = time.time()
        res = ConvertResult(request=req, src_size=_try_size(req.input_path))

        # Dry-run
        if req.dry_run:
            res.ok = True
            res.took = time.time() - start
            res.output_path = req.output_path()
            log.debug("Dry-run: %s → %s", req.input_path.name, res.output_path)
            return res

        # Проверка существования входного файла
        if not req.input_path.exists():
            res.error = f"Файл не найден: {req.input_path}"
            res.took = time.time() - start
            log.warning("Файл не найден: %s", req.input_path)
            return res

        out_path = req.output_path()
        if out_path.resolve() == req.input_path.resolve():
            res.error = "Входной и выходной файл совпадают"
            res.took = time.time() - start
            log.warning("Source == destination: %s", out_path)
            return res

        # Создаём родительскую директорию
        out_path.parent.mkdir(parents=True, exist_ok=True)

        ext = req.input_ext
        fmt = resolve_format(req.output_format, ext)
        mime = detect_mime(ext)

        log.info("Конвертация: %s (%s) → %s [fmt=%s, q=%d, max=%d]",
                 req.input_path.name, ext, out_path.name, fmt, req.quality, req.max_size)

        err: Optional[str] = None

        try:
            if ext in SVG_INPUT and mime == 'image':
                log.debug("Конвертер: SVG → PNG")
                err = self._convert_svg(req.input_path, out_path, req.max_size)
            elif mime == 'image':
                log.debug("Конвертер: PIL изображение")
                err = self._convert_image(req.input_path, out_path, fmt, req.quality, req.max_size)
            elif mime == 'video':
                log.debug("Конвертер: ffmpeg видео")
                err = self._convert_video(req.input_path, out_path, fmt, req.quality)
            elif mime == 'audio':
                log.debug("Конвертер: ffmpeg аудио")
                err = self._convert_audio(req.input_path, out_path, fmt, req.quality)
            else:
                err = f"Неподдерживаемый тип: {ext}"
        except Exception as e:
            err = str(e)
            log.exception("Исключение при конвертации %s", req.input_path.name)

        if err:
            res.error = err
            res.ok = False
            log.error("Ошибка конвертации %s: %s", req.input_path.name, err)
        else:
            res.ok = True
            res.output_path = out_path
            res.dst_size = _try_size(out_path)
            ratio = res.dst_size / res.src_size * 100 if res.src_size > 0 else 0
            log.info("✅ %s → %s (%.1f%%, %.1fс)",
                     req.input_path.name, out_path.name, ratio, res.took)

        res.took = time.time() - start
        return res

    # ── Пакетная конвертация ─────────────────────────────────────────────────

    def convert_many(
        self,
        requests: list[ConvertRequest],
        on_progress: Optional[ProgressCallback] = None,
    ) -> list[ConvertResult]:
        """Конвертирует список файлов параллельно."""
        results: list[ConvertResult] = []
        total = len(requests)

        log.info("Пакетная конвертация: %d файлов, workers=%d", total, self.workers)

        with ThreadPoolExecutor(max_workers=self.workers) as pool:
            fut_map = {}
            for req in requests:
                fut = pool.submit(self.convert_one, req)
                fut_map[fut] = req

            completed = 0
            for fut in as_completed(fut_map):
                res = fut.result()
                results.append(res)
                completed += 1
                if on_progress:
                    on_progress(completed, total, res)

        ok = sum(1 for r in results if r.ok)
        log.info("Пакетная конвертация завершена: %d/%d успешно", ok, total)
        return results

    # ── Сбор файлов ──────────────────────────────────────────────────────────

    def collect(
        self,
        paths: list[Path],
        recursive: bool = False,
        allowed_extensions: Optional[set[str]] = None,
    ) -> list[Path]:
        """Собирает все конвертируемые файлы из списка путей/папок/glob."""
        if allowed_extensions is None:
            allowed_extensions = ALL_INPUT

        collected: set[Path] = set()
        import glob as glob_mod

        for p in paths:
            if p.is_dir():
                pattern = '**/*' if recursive else '*'
                for f in sorted(p.glob(pattern)):
                    if f.is_file() and f.suffix.lower() in allowed_extensions:
                        collected.add(f.resolve())
            elif p.is_file():
                if p.suffix.lower() in allowed_extensions:
                    collected.add(p.resolve())
            else:
                # glob-маска
                matches = glob_mod.glob(str(p), recursive=recursive)
                for m in sorted(matches):
                    mp = Path(m)
                    if mp.is_file() and mp.suffix.lower() in allowed_extensions:
                        collected.add(mp.resolve())

        return sorted(collected)  # type: ignore[return-value]

    # ── Внутренние конвертеры ────────────────────────────────────────────────

    @staticmethod
    def _convert_image(
        src: Path, dst: Path, fmt_out: str, quality: int, max_size: int,
    ) -> Optional[str]:
        """PIL: конвертация изображения. Возвращает None или строку ошибки."""
        try:
            from PIL import Image
        except ImportError:
            return "PIL не установлен: pip install Pillow"

        try:
            img = Image.open(src)
        except Exception as e:
            return f"Не удалось открыть: {e}"

        # HEIC/HEIF
        if hasattr(img, 'format') and img.format in ('HEIF', 'HEIC'):
            pass  # pillow-heif уже зарегистрирован

        # Resize
        if max_size > 0:
            w, h = img.size
            if w > max_size or h > max_size:
                ratio = min(max_size / w, max_size / h)
                new_size = (int(w * ratio), int(h * ratio))
                img = img.resize(new_size, Image.LANCZOS)

        save_as_jpeg = fmt_out in ('jpg', 'jpeg')
        kwargs: dict = {}

        if fmt_out == 'png':
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
        elif fmt_out == 'webp':
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGBA')
            kwargs['quality'] = quality
            kwargs['method'] = 6
        elif save_as_jpeg:
            if img.mode in ('RGBA', 'LA', 'P'):
                bg = Image.new('RGB', img.size, (255, 255, 255))
                if img.mode == 'P':
                    img = img.convert('RGBA')
                mask = img.split()[-1] if img.mode == 'RGBA' else None
                bg.paste(img, mask=mask)
                img = bg
            elif img.mode != 'RGB':
                img = img.convert('RGB')
            kwargs['quality'] = quality
            kwargs['optimize'] = True
        elif fmt_out == 'bmp':
            if img.mode not in ('RGB', 'RGBA'):
                img = img.convert('RGB')
        elif fmt_out == 'tiff':
            kwargs['compression'] = 'tiff_lzw'

        try:
            fmt_desc = OUTPUT_FORMATS.get(fmt_out, {}).get('desc', 'JPEG')
            img.save(dst, format=fmt_desc, **kwargs)
        except Exception as e:
            return f"Ошибка сохранения: {e}"

        return None

    @staticmethod
    def _convert_svg(src: Path, dst: Path, max_size: int) -> Optional[str]:
        """SVG → PNG через rsvg-convert."""
        size = max_size if max_size > 0 else 1024
        try:
            r = subprocess.run(
                ['rsvg-convert', '-w', str(size), '-h', str(size),
                 '--keep-aspect-ratio', str(src), '-o', str(dst)],
                capture_output=True, text=True, timeout=60,
            )
            if r.returncode != 0:
                return r.stderr.strip()
        except FileNotFoundError:
            return "rsvg-convert не найден: apt install librsvg2-bin"
        except subprocess.TimeoutExpired:
            return "Таймаут rsvg-convert"
        return None

    @staticmethod
    def _tool_path(name: str) -> str:
        """Ищет инструмент: рядом с exe / в корне проекта / в PATH."""
        dirs = []
        if getattr(sys, 'frozen', False):
            dirs.append(Path(sys._MEIPASS))
        else:
            dirs.append(Path(sys.argv[0]).parent)
            script_dir = Path(__file__).resolve().parent.parent.parent
            if script_dir not in dirs:
                dirs.append(script_dir)

        exts = ['', '.exe']
        for base in dirs:
            for ext in exts:
                p = base / f"{name}{ext}"
                if p.exists():
                    return str(p)
                bin_p = base / 'bin' / f"{name}{ext}"
                if bin_p.exists():
                    return str(bin_p)
        return name

    @staticmethod
    def _ffmpeg_path() -> str:
        """Путь к ffmpeg (bundled / системный)."""
        return Converter._tool_path('ffmpeg')

    @staticmethod
    def _ffprobe_path() -> str:
        """Путь к ffprobe (bundled / системный)."""
        return Converter._tool_path('ffprobe')

    @staticmethod
    def _rsvg_path() -> str:
        """Путь к rsvg-convert (bundled / системный)."""
        return Converter._tool_path('rsvg-convert')

    def _convert_video(self, src: Path, dst: Path, fmt_out: str, quality: int) -> Optional[str]:
        """Видео → ffmpeg."""
        crf = max(18, min(28, 28 - int((quality - 50) / 50 * 10)))
        ffmpeg = self._ffmpeg_path()

        vcodec = 'libx264'
        acodec = 'aac'
        extra: list[str] = []

        if fmt_out == 'mkv':
            vcodec, acodec = 'libx264', 'aac'
        elif fmt_out == 'avi':
            vcodec, acodec = 'libx264', 'mp3'
        elif fmt_out == 'webm':
            vcodec, acodec = 'libvpx', 'libvorbis'
            extra = ['-b:v', '0', '-b:a', '128k']

        cmd = [
            ffmpeg, '-i', str(src),
            '-c:v', vcodec, '-preset', 'medium', '-crf', str(crf),
            '-c:a', acodec,
        ] + extra + ['-b:a', '128k', '-y', str(dst)]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            if r.returncode != 0:
                err_lines = [l for l in r.stderr.split('\n')
                             if 'error' in l.lower() or 'Error' in l]
                return err_lines[-1] if err_lines else f"код {r.returncode}"
        except FileNotFoundError:
            return f"ffmpeg не найден: установите ffmpeg или положите рядом с {sys.argv[0]}"
        except subprocess.TimeoutExpired:
            return "Таймаут ffmpeg (>2ч)"
        return None

    def _convert_audio(self, src: Path, dst: Path, fmt_out: str, quality: int) -> Optional[str]:
        """Аудио → ffmpeg."""
        lame_q = max(0, min(9, 9 - int(quality / 100 * 9)))
        ffmpeg = self._ffmpeg_path()
        params: list[str] = []

        if fmt_out == 'mp3':
            params = ['-codec:a', 'libmp3lame', '-qscale:a', str(lame_q)]
        elif fmt_out == 'flac':
            params = ['-codec:a', 'flac']
        elif fmt_out == 'ogg':
            params = ['-codec:a', 'libvorbis', '-qscale:a', str(lame_q)]
        elif fmt_out == 'wav':
            params = ['-codec:a', 'pcm_s16le']
        elif fmt_out == 'aac':
            params = ['-codec:a', 'aac', '-b:a', '192k']
        elif fmt_out == 'opus':
            params = ['-codec:a', 'libopus', '-b:a', '128k']

        cmd = [ffmpeg, '-i', str(src)] + params + ['-y', str(dst)]

        try:
            r = subprocess.run(cmd, capture_output=True, text=True, timeout=7200)
            if r.returncode != 0:
                err_lines = [l for l in r.stderr.split('\n')
                             if 'error' in l.lower() or 'Error' in l]
                return err_lines[-1] if err_lines else f"код {r.returncode}"
        except FileNotFoundError:
            return f"ffmpeg не найден: установите ffmpeg или положите рядом с {sys.argv[0]}"
        except subprocess.TimeoutExpired:
            return "Таймаут ffmpeg (>2ч)"
        return None


# ──────────────────────────────────────────────────────────────────────────────
# Утилиты
# ──────────────────────────────────────────────────────────────────────────────

def _try_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except (OSError, FileNotFoundError):
        return 0


def _fmt_size(b: int) -> str:
    for unit in ('B', 'KB', 'MB', 'GB'):
        if b < 1024:
            return f"{b:.1f} {unit}"
        b /= 1024
    return f"{b:.2f} TB"


def _fmt_time(s: float) -> str:
    if s < 60:
        return f"{s:.1f}с"
    m, s_rem = divmod(s, 60)
    if m < 60:
        return f"{int(m)}м {s_rem:.0f}с"
    h, m_rem = divmod(m, 60)
    return f"{int(h)}ч {int(m_rem)}м"


__all__ = [
    'Converter', 'ConvertRequest', 'ConvertResult',
    'ProgressCallback',
    'OUTPUT_FORMATS', 'ALL_INPUT',
    'IMAGE_INPUT', 'SVG_INPUT', 'VIDEO_INPUT', 'AUDIO_INPUT',
    'detect_mime', 'resolve_format',
    'QualityPreset', 'QUALITY_PRESETS',
    'MediaInfo', 'get_media_info',
    'get_tool_path',
]


def get_tool_path(name: str) -> str:
    """Возвращает путь к инструменту (ffmpeg, ffprobe, rsvg-convert).
    Учитывает bundled-версию в PyInstaller и корень проекта.
    """
    return Converter._tool_path(name)

