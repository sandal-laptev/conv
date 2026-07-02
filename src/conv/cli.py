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
    p.add_argument('-r', '--recursive', action='store_true',
                   help='Рекурсивный обход папок')
    p.add_argument('-j', '--jobs', type=int, default=0,
                   help='Число параллельных задач (0 = авто)', metavar='N')
    p.add_argument('--dry-run', action='store_true',
                   help='Только показать, что будет конвертироваться')
    p.add_argument('--version', action='version',
                   version=f'conv v{__import__("conv").__version__} 🖧 Иохим Кузьмич')
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)

    log.info("CLI args: %s", vars(args))

    # ── Сбор файлов ──
    converter = Converter(workers=args.jobs)

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

    quality = max(1, min(100, args.quality))
    max_size = max(0, args.size)

    # ── Инфо ──
    print(f"\n  🖧  Иохим Кузьмич — Медиа-конвертер  🖧\n")
    print(f"  Файлов:     {len(files)}")
    print(f"  Выход:      {out_dir}")
    print(f"  Качество:   {quality}")
    if max_size:
        print(f"  Макс.размер: {max_size}px")
    print(f"  Потоков:    {converter.workers}")
    print(f"  Режим:      {'🔍 DRY RUN' if args.dry_run else '⚡ КОНВЕРТАЦИЯ'}\n")

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
