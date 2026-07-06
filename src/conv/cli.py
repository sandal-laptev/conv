"""CLI-интерфейс для conv."""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from conv.core import (
    Converter,
    ConvertRequest,
    OUTPUT_FORMATS,
    ALL_INPUT,
    VIDEO_INPUT,
    AUDIO_INPUT,
    SVG_INPUT,
    QUALITY_PRESETS,
    MediaInfo,
    get_media_info,
    resolve_format as resolve_fmt,
    _fmt_size,
    _fmt_time,
)
from conv.logger import get_logger, tail as log_tail

log = get_logger("conv.cli")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog='conv',
        description='🖧 Иохим Кузьмич — Медиа-конвертер',
        epilog='Без аргументов — конвертирует всю текущую папку в ./CONVERTED',
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    p.add_argument('input', nargs='*', help='Файлы, папки или glob-маски')
    p.add_argument('-o', '--output', default='',
                   help='Выходная папка (по умолчанию ./CONVERTED)')
    p.add_argument('-f', '--format', default='',
                   choices=list(OUTPUT_FORMATS.keys()),
                   help='Выходной формат (по умолч.: jpg/img → jpg, видео → mp4, аудио → mp3)')
    p.add_argument('-q', '--quality', type=int, default=85,
                   help='Качество 1-100', metavar='N')
    p.add_argument('-s', '--size', type=int, default=0,
                   help='Макс. ширина/высота для изображений (0 = оригинал)', metavar='PX')
    p.add_argument('--preset', default='',
                   choices=list(QUALITY_PRESETS.keys()),
                   help='Пресет качества (переопределяет -q и -s)')
    p.add_argument('-r', '--recursive', action='store_true',
                   help='Рекурсивный обход папок')
    p.add_argument('-j', '--jobs', type=int, default=0,
                   help='Число параллельных задач (0 = авто)', metavar='N')
    p.add_argument('--man', action='store_true',
                   help='Показать man-страницу')
    p.add_argument('--completion', choices=['bash', 'zsh'],
                   help='Вывести скрипт автодополнения для указанной оболочки')
    p.add_argument('--check-tools', action='store_true',
                   help='Проверить доступность инструментов и выйти')
    p.add_argument('--trim-start', type=float, default=0.0, metavar='S',
                   help='Начало обрезки в секундах (0 = с начала)')
    p.add_argument('--trim-end', type=float, default=0.0, metavar='S',
                   help='Конец обрезки в секундах (0 = до конца)')
    p.add_argument('--sort-by-type', action='store_true',
                   help='Сортировать выходные файлы по типу (image/, video/, audio/)')
    p.add_argument('--no-audio', action='store_true',
                   help='Удалить аудиодорожку из видео')
    p.add_argument('--split-audio', metavar='FMT', nargs='?', const='mp3',
                   help='Разделить видео и аудио в отдельные файлы (формат: mp3, flac...)'
    )
    p.add_argument('--rename-to', metavar='EXT',
                   help='Переименовать файлы в указанное расширение (без конвертации)')
    p.add_argument('--info', action='store_true',
                   help='Показать информацию о медиафайлах (ffprobe) и выйти')
    p.add_argument('--dry-run', action='store_true',
                   help='Только показать, что будет конвертироваться')
    p.add_argument('--version', action='version',
                   version=f'conv v{__import__("conv").__version__} 🖧 Иохим Кузьмич')
    return p


def _print_tools(tools: dict[str, bool]) -> None:
    """Выводит таблицу доступности инструментов."""
    labels = {
        'ffmpeg': 'ffmpeg       (конвертация)',
        'ffprobe': 'ffprobe     (медиа-инфо)',
        'rsvg_convert': 'rsvg-convert (SVG → PNG)',
        'pil': 'Pillow      (изображения)',
        'pillow_heif': 'pillow-heif (HEIC/HEIF)',
    }
    print("\n  🔧 Проверка инструментов:\n")
    for key, label in labels.items():
        ok = tools.get(key, False)
        sym = "✅" if ok else "❌"
        print(f"  {sym}  {label}")
    print()

    missing = [k for k, v in tools.items() if not v]
    if missing:
        print("  ⚠ Отсутствуют:")
        tips = {
            'ffmpeg': 'apt install ffmpeg',
            'rsvg_convert': 'apt install librsvg2-bin',
            'pil': 'pip install Pillow',
            'pillow_heif': 'pip install pillow-heif',
        }
        for k in missing:
            tip = tips.get(k, '')
            print(f"     {k}  — {tip}")
        print()


def _print_completion(shell: str) -> None:
    """Генерирует скрипт автодополнения для bash или zsh."""
    fmt_choices = ' '.join(OUTPUT_FORMATS.keys())
    preset_choices = ' '.join(QUALITY_PRESETS.keys())
    all_exts = ' '.join(sorted(ALL_INPUT))

    if shell == 'bash':
        print(_BASH_COMPLETION_TEMPLATE.format(
            fmt_choices=fmt_choices,
            preset_choices=preset_choices,
            all_exts=all_exts,
        ))
    elif shell == 'zsh':
        print(_ZSH_COMPLETION_TEMPLATE.format(
            fmt_choices=fmt_choices,
            preset_choices=preset_choices,
            all_exts=all_exts,
        ))


_BASH_COMPLETION_TEMPLATE = '''# 🖧 conv — bash автодополнение
# Установка: source <(conv --completion bash)
# Или:      conv --completion bash > /etc/bash_completion.d/conv

_conv_completions() {{
    local cur prev words cword
    _init_completion -n = || return

    # Список всех флагов
    local opts="-o --output -f --format -q --quality -s --size"
    opts+=" --preset -r --recursive -j --jobs --check-tools --dry-run"
    opts+=" --trim-start --trim-end --version -h --help --completion"

    case $prev in
        -o|--output)
            _filedir -d
            return
            ;;
        -f|--format)
            COMPREPLY=($(compgen -W "{fmt_choices}" -- "$cur"))
            return
            ;;
        --preset)
            COMPREPLY=($(compgen -W "{preset_choices}" -- "$cur"))
            return
            ;;
        --completion)
            COMPREPLY=($(compgen -W "bash zsh" -- "$cur"))
            return
            ;;
        -j|--jobs)
            COMPREPLY=($(compgen -W "1 2 4 8 16" -- "$cur"))
            return
            ;;
        -q|--quality)
            COMPREPLY=($(compgen -W "{{1..100}}" -- "$cur"))
            return
            ;;
        -s|--size)
            COMPREPLY=($(compgen -W "640 1024 1920 3840" -- "$cur"))
            return
            ;;
    esac

    # Если курсор в начале слова — предлагаем флаги и файлы
    if [[ $cur == -* ]]; then
        COMPREPLY=($(compgen -W "$opts" -- "$cur"))
    else
        _filedir
    fi
}} &&
complete -F _conv_completions conv
'''

_ZSH_COMPLETION_TEMPLATE = '''# 🖧 conv — zsh автодополнение
# Установка: source <(conv --completion zsh)
# Или:      conv --completion zsh > /usr/local/share/zsh/site-functions/_conv

#compdef conv

_conv() {{
    local -a opts
    opts=(
        "-o[Выходная папка]:dir:_files -/"
        "--output[Выходная папка]:dir:_files -/"
        "-f[Выходной формат]:format:({fmt_choices})"
        "--format[Выходной формат]:format:({fmt_choices})"
        "-q[Качество 1-100]:quality:"
        "--quality[Качество 1-100]:quality:"
        "-s[Макс. px]:size:(640 1024 1920 3840)"
        "--size[Макс. px]:size:(640 1024 1920 3840)"
        "--preset[Пресет качества]:preset:({preset_choices})"
        "-r[Рекурсивный обход]"
        "--recursive[Рекурсивный обход]"
        "-j[Параллельных задач]:jobs:(1 2 4 8 16)"
        "--jobs[Параллельных задач]:jobs:(1 2 4 8 16)"
        "--check-tools[Проверить инструменты]"
        "--dry-run[Только предпросмотр]"
        "--trim-start[Начало обрезки, с]:seconds:"
        "--trim-end[Конец обрезки, с]:seconds:"
        "--completion[Скрипт дополнения]:shell:(bash zsh)"
        "--version[Версия]"
        "-h[Справка]"
        "--help[Справка]"
    )
    _arguments $opts '*:file:_files'
}}

_conv
'''


def _print_man() -> None:
    """Показывает man-страницу."""
    import shutil
    man_path = Path(__file__).resolve().parent.parent.parent / 'man' / 'conv.1'
    if not man_path.exists():
        print(f"⚠ man-страница не найдена: {man_path}", file=sys.stderr)
        sys.exit(1)

    # Если man доступен — показываем отформатированным
    if shutil.which('man'):
        import subprocess as sp
        sp.run(['man', '-l', str(man_path)])
    else:
        # Иначе печатаем raw troff
        sys.stdout.write(man_path.read_text(encoding='utf-8'))


def _print_media_info(files: list[Path]) -> None:
    """Выводит информацию о медиафайлах."""
    print("\n  🖧  Медиа-информация  🖧\n")
    for f in files:
        ext = f.suffix.lower()
        sym = '🖼' if ext not in VIDEO_INPUT | AUDIO_INPUT else \
              '🎬' if ext in VIDEO_INPUT else '🎵'
        print(f"  {sym}  {f.name}")
        print(f"      📦 {_fmt_size(_try_size(f))}")

        if ext in VIDEO_INPUT | AUDIO_INPUT:
            info = get_media_info(f)
            if info.duration:
                print(f"      ⏱ Длит.: {info.fmt_duration()}")
            if info.bit_rate:
                print(f"      📊 Битрейд: {info.fmt_bitrate()}")
            if info.has_video:
                parts = [f"      🎞 {info.video_codec}"]
                if info.resolution_str:
                    parts.append(info.resolution_str)
                if info.fps:
                    parts.append(f"{info.fps:.0f} fps")
                print("  ".join(parts))
            if info.has_audio:
                parts = [f"      🎵 {info.audio_codec}"]
                if info.audio_channels:
                    ch = {'1': 'моно', '2': 'стерео', '6': '5.1', '8': '7.1'}
                    parts.append(ch.get(str(info.audio_channels), f'{info.audio_channels}ch'))
                if info.sample_rate:
                    parts.append(f"{info.sample_rate // 1000}kHz")
                print("  ".join(parts))
        else:
            # Изображение — пробуем размеры
            try:
                from PIL import Image
                with Image.open(f) as img:
                    print(f"      📐 {img.width}\u00d7{img.height}")
            except Exception:
                pass
        print()


# ── Хелпер ──

def _try_size(path: Path) -> int:
    try:
        return path.stat().st_size
    except OSError:
        return 0


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    log.info("CLI args: %s", vars(args))

    # ── Сбор файлов ──
    converter = Converter(workers=args.jobs)

    # ── Проверка инструментов ──
    tools = converter.check_tools()

    if args.check_tools:
        _print_tools(tools)
        return 0

    if args.completion:
        _print_completion(args.completion)
        return 0

    if args.man:
        _print_man()
        return 0

    input_paths = [Path(p) for p in args.input] if args.input else [Path.cwd()]
    files = converter.collect(input_paths, recursive=args.recursive)

    if args.info:
        _print_media_info(files)
        return 0

    log.info("Собрано файлов: %d", len(files))

    if not files:
        print("ℹ Нет файлов для конвертации.")
        return 0

    # ── Выходная папка ──
    out_dir = Path(args.output or 'CONVERTED')
    if not out_dir.is_absolute():
        out_dir = Path.cwd() / out_dir
    if not args.dry_run:
        out_dir.mkdir(parents=True, exist_ok=True)
    log.info("Выходная папка: %s", out_dir)

    # ── Пресет ──
    preset_name = args.preset
    if preset_name and preset_name in QUALITY_PRESETS:
        preset = QUALITY_PRESETS[preset_name]
        quality = max(1, min(100, preset.quality))
        max_size = max(0, preset.max_size)
        log.info("Пресет качества: %s (q=%d, s=%d)", preset.label, quality, max_size)
    else:
        quality = max(1, min(100, args.quality))
        max_size = max(0, args.size)

    # ── Инфо ──
    print(f"\n  🖧  Иохим Кузьмич — Медиа-конвертер  🖧\n")
    print(f"  Файлов:     {len(files)}")
    print(f"  Выход:      {out_dir}")
    if preset_name:
        print(f"  Пресет:     {QUALITY_PRESETS[preset_name].label}")
    print(f"  Качество:   {quality}")
    if max_size:
        print(f"  Макс.размер: {max_size}px")
    print(f"  Потоков:    {converter.workers}")
    if args.sort_by_type:
        print(f"  Сортировка: по типу (image/video/audio)")
    print(f"  Режим:      {'🔍 DRY RUN' if args.dry_run else '⚡ КОНВЕРТАЦИЯ'}\n")

    # ── Предупреждение об отсутствующих инструментах ──
    need_video = any(f.suffix.lower() in VIDEO_INPUT for f in files)
    need_audio = any(f.suffix.lower() in AUDIO_INPUT for f in files)
    need_svg = any(f.suffix.lower() in SVG_INPUT for f in files)

    if need_video or need_audio:
        if not tools.get('ffmpeg'):
            print("  ⚠  ffmpeg не найден! Видео и аудио не сконвертируются.")
            print("     Установите: apt install ffmpeg\n")
    if need_svg and not tools.get('rsvg_convert'):
        print("  ⚠  rsvg-convert не найден! SVG не сконвертируются.")
        print("     Установите: apt install librsvg2-bin\n")

    # ── Режим переименования ──
    if args.rename_to:
        print(f"  🏷 Переименование: {len(files)} файлов → .{args.rename_to.lstrip('.')}\n")
        rename_results = converter.rename_many(files, args.rename_to)
        ok = sum(1 for r in rename_results if r.ok)
        fail = len(rename_results) - ok
        print(f"  ───── ИТОГ ─────")
        print(f"  ✅ Переименовано: {ok}")
        if fail:
            print(f"  ❌ Ошибок: {fail}")
            for r in rename_results:
                if not r.ok:
                    print(f"     {r.input_name}: {r.error}")
        return 0 if fail == 0 else 1

    # ── Создаём запросы ──
    requests: list[ConvertRequest] = []
    for f in files:
        try:
            rel = f.relative_to(Path.cwd()) if f.is_relative_to(Path.cwd()) else Path('')
        except ValueError:
            rel = Path('')

        requests.append(ConvertRequest(
            input_path=f,
            output_dir=out_dir,
            output_format=args.format,
            quality=quality,
            max_size=max_size,
            preserve_structure=args.recursive,
            dry_run=args.dry_run,
            trim_start=args.trim_start,
            trim_end=args.trim_end,
            sort_by_type=args.sort_by_type,
            audio_mode='remove' if args.no_audio else (
                'split' if args.split_audio else 'keep'),
            audio_format=args.split_audio or 'mp3',
        ))

    # ── DRY RUN ──
    if args.dry_run:
        for req in requests:
            sym = '🖼' if (req.input_ext in ALL_INPUT
                          and req.input_ext not in VIDEO_INPUT | AUDIO_INPUT) else \
                  '🎬' if req.input_ext in VIDEO_INPUT else '🎵'
            fmt = resolve_fmt(args.format, req.input_ext)
            print(f"  {sym} {req.input_path.name}  →  .{fmt}")
        return 0

    # ── Конвертация ──
    results = converter.convert_many(requests)

    # ── Итог ──
    ok = sum(1 for r in results if r.ok)
    fail = len(results) - ok
    total_src = sum(r.src_size for r in results)
    total_dst = sum(r.dst_size for r in results if r.ok)
    total_time = sum(r.took for r in results)

    if ok:
        print()
    print(f"  ───── ИТОГ ─────")
    print(f"  ✅ Успешно: {ok}")
    if fail:
        print(f"  ❌ Ошибок:  {fail}")
    if total_src > 0:
        ratio = total_dst / total_src * 100 if total_dst > 0 else 0
        print(f"  📦 {_fmt_size(total_src)} → {_fmt_size(total_dst)}  ({ratio:.1f}%)")
    print(f"  ⏱ {_fmt_time(total_time)}\n")

    if fail:
        print("  ❌ Ошибки:")
        for r in results:
            if not r.ok:
                print(f"     {r.input_name}: {r.error}")
        print()

    return 0 if fail == 0 else 1


if __name__ == '__main__':
    sys.exit(main())
