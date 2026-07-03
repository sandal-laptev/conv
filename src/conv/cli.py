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
    p.add_argument('--check-tools', action='store_true',
                   help='Проверить доступность инструментов и выйти')
    p.add_argument('--dry-run', action='store_true',
                   help='Только показать, что будет конвертироваться')
    p.add_argument('--version', action='version',
                   version=f'conv v{__import__("conv").__version__} 🖧 Иохим Кузьмич')
    return p


def _print_tools(tools: dict[str, bool]) -> None:
    """Выводит таблицу доступности инструментов."""
    labels = {
        'ffmpeg': 'ffmpeg      (видео/аудио)',
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

    input_paths = [Path(p) for p in args.input] if args.input else [Path.cwd()]
    files = converter.collect(input_paths, recursive=args.recursive)

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
