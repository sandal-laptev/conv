"""Генерация .ico для MO Kolomyagi Media Converter.

Использует только PIL + math — не требует rsvg-convert.
Создаёт ICO со всеми стандартными размерами (16–256).
"""

from __future__ import annotations

import math
from pathlib import Path

from PIL import Image, ImageDraw


def _draw_icon(size: int) -> Image.Image:
    """Нарисовать иконку MO Kolomyagi в заданном размере."""
    img = Image.new("RGBA", (size, size), (0, 0, 0, 0))
    draw = ImageDraw.Draw(img)

    # Цвета
    bg_dark = (10, 10, 46, 255)
    bg_light = (26, 5, 51, 255)
    accent = (0, 212, 255, 255)
    accent2 = (123, 47, 247, 220)
    text_color = (123, 47, 247, 200)
    dim = 0.5

    def p(x):
        """Масштабировать координату (0..256 → 0..size)."""
        return int(x / 256 * size)

    cx, cy = p(128), p(128)

    # ── Фон (скруглённый прямоугольник) ──
    r = p(48)
    draw.rounded_rectangle(
        (0, 0, size - 1, size - 1), radius=r,
        fill=bg_dark,
    )

    # ── Внешнее кольцо ──
    r_outer = p(92)
    draw.ellipse(
        [cx - r_outer, cy - r_outer, cx + r_outer, cy + r_outer],
        outline=(*accent[:3], int(accent[3] * 0.3)),
        width=max(1, p(2)),
    )

    # ── Сетевые линии ──
    nodes = [
        (p(75), p(75)), (p(181), p(75)),
        (p(75), p(181)), (p(181), p(181)),
        (cx, p(55)), (cx, p(201)),
        (p(55), cy), (p(201), cy),
    ]
    line_color = (*accent[:3], int(accent[3] * dim * 0.5))
    for nx, ny in nodes:
        draw.line([(cx, cy), (nx, ny)], fill=line_color, width=max(1, p(1)))

    # ── Узлы ──
    for nx, ny in nodes:
        rn = p(4) if abs(nx - cx) > 20 else p(3)
        draw.ellipse(
            [nx - rn, ny - rn, nx + rn, ny + rn],
            fill=(*accent[:3], int(accent[3] * 0.6)),
        )

    # ── Внутренний круг (лицо) ──
    r_inner = p(40)
    draw.ellipse(
        [cx - r_inner, cy - r_inner - p(3),
         cx + r_inner, cy + r_inner - p(3)],
        outline=(*accent[:3], int(accent[3] * 0.9)),
        width=max(1, p(2)),
    )

    # ── Глаза ──
    eye_r = max(1, p(5))
    for ex in (cx - p(15), cx + p(15)):
        ey = cy - p(10)
        draw.ellipse(
            [ex - eye_r, ey - eye_r, ex + eye_r, ey + eye_r],
            fill=(*accent[:3], 220),
        )
        hl_r = max(1, p(2))
        draw.ellipse(
            [ex - hl_r, ey - hl_r, ex + hl_r, ey + hl_r],
            fill=(255, 255, 255, 180),
        )

    # ── Улыбка ──
    draw.arc(
        [cx - p(16), cy - p(3), cx + p(16), cy + p(12)],
        start=0, end=180,
        fill=(*accent[:3], 220),
        width=max(1, p(2)),
    )

    # ── Текст MO ──
    if size >= 48:
        try:
            font_size = max(8, size // 14)
            try:
                from PIL import ImageFont
                font = ImageFont.truetype("arial.ttf", font_size)
            except (IOError, OSError):
                font = ImageFont.load_default()
            draw.text(
                (cx, cy + p(45)),
                "MO",
                fill=text_color,
                font=font,
                anchor="mm",
            )
        except Exception:
            pass

    return img


def generate_ico(output_path: str | Path) -> None:
    """Сгенерировать .ico со всеми стандартными размерами."""
    sizes = [16, 24, 32, 48, 64, 128, 256]

    icons: list[Image.Image] = []
    for s in sizes:
        img = _draw_icon(s)
        icons.append(img)

    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    icons[0].save(
        str(output),
        format="ICO",
        sizes=[(s, s) for s in sizes],
        append_images=icons[1:],
    )
    print(f"✅ ICO created: {output} ({len(icons)} sizes)")


def generate_png(output_path: str | Path, size: int = 256) -> None:
    """Сгенерировать PNG для предпросмотра."""
    img = _draw_icon(size)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    img.save(str(output), format="PNG")
    print(f"✅ PNG created: {output} ({size}px)")


if __name__ == "__main__":
    import sys
    base = Path(__file__).resolve().parent.parent
    if len(sys.argv) > 1 and sys.argv[1] == "--png":
        generate_png(base / "src" / "conv" / "gui_qt" / "resources" / "icon.png")
    else:
        generate_ico(base / "src" / "conv" / "gui_qt" / "resources" / "icon.ico")
        generate_png(base / "src" / "conv" / "gui_qt" / "resources" / "icon.png")
