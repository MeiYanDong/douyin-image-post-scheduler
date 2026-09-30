"""Image-only subtitle layout, adapted from native-subtitle-quote-image (MIT).

Copyright (c) 2026 程意. See ../references/upstream-license.txt.
Frames can come from a still-image adapter or an external video-frame adapter.
"""

from __future__ import annotations

import math
from typing import Sequence

from PIL import Image, ImageDraw, ImageFont, ImageOps


FONT_CANDIDATES = [
    "/System/Library/Fonts/PingFang.ttc",
    "/System/Library/Fonts/STHeiti Medium.ttc",
    "/System/Library/Fonts/Hiragino Sans GB.ttc",
    "C:/Windows/Fonts/msyh.ttc",
    "C:/Windows/Fonts/simhei.ttf",
    "/usr/share/fonts/opentype/noto/NotoSansCJK-Regular.ttc",
    "/usr/share/fonts/opentype/noto/NotoSansCJKsc-Regular.otf",
    "/usr/share/fonts/truetype/wqy/wqy-zenhei.ttc",
]
DEFAULT_LABEL = "创作者评论 · AI配图"


def contains_cjk(text: str) -> bool:
    ranges = (("\u1100", "\u11ff"), ("\u3040", "\u30ff"), ("\u3130", "\u318f"),
              ("\u3400", "\u9fff"), ("\uac00", "\ud7af"), ("\uf900", "\ufaff"),
              ("\uff66", "\uff9d"))
    return any(start <= char <= end for char in text for start, end in ranges)


def load_font(path: str | None, size: int, text: str):
    # An explicitly supplied font must work; a typo must not silently fall back.
    candidates = [path] if path else list(FONT_CANDIDATES)
    if not path and not contains_cjk(text):
        candidates.append("DejaVuSans.ttf")
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size)
        except OSError:
            continue
    raise ValueError("找不到可用字体；请安装中文字体或用 --font 指定字体文件")


def choose_hero_fraction(strip_count: int, requested: float | None = None) -> float:
    if strip_count < 1:
        raise ValueError("至少需要一个字幕条")
    if requested is not None:
        if not math.isfinite(requested) or not 0.48 <= requested <= 0.82:
            raise ValueError("主画面比例必须在 0.48—0.82 之间")
        return requested
    return min(0.82, max(0.48, 1.0 - strip_count * 0.075))


def draw_subtitle(image, text, y_center, font_path, font_size, max_width):
    draw = ImageDraw.Draw(image)
    minimum = max(12, round(font_size * 0.55))
    for size in range(font_size, minimum - 1, -2):
        font = load_font(font_path, size, text)
        stroke = max(2, size // 14)
        box = draw.textbbox((0, 0), text, font=font, stroke_width=stroke)
        text_width, text_height = box[2] - box[0], box[3] - box[1]
        if text_width > max_width or text_height > image.height - 8:
            continue
        x = (image.width - text_width) // 2 - box[0]
        y = y_center - text_height // 2 - box[1]
        if y + box[1] < 0 or y + box[3] > image.height:
            continue
        draw.text((x, y), text, font=font, fill="white", stroke_width=stroke,
                  stroke_fill="black")
        return {"text": text, "font_size": size, "stroke_width": stroke,
                "bounds": [x + box[0], y + box[1], x + box[2], y + box[3]]}
    raise ValueError(f"台词过长，缩小到可读下限后仍放不下；请拆句或删减：{text!r}")


def draw_label(image, label, font_path, width):
    if not isinstance(label, str) or not label.strip() or "\n" in label or "\r" in label:
        raise ValueError("来源标识必须是非空单行文字")
    size = max(14, round(width / 48))
    font = load_font(font_path, size, label)
    draw = ImageDraw.Draw(image)
    stroke = max(1, size // 14)
    box = draw.textbbox((0, 0), label, font=font, stroke_width=stroke)
    if box[2] - box[0] > width * 0.92:
        raise ValueError("来源标识过长，请缩短 label")
    padding = max(12, round(width * 0.024))
    draw.text((padding - box[0], padding - box[1]), label, font=font,
              fill="white", stroke_width=stroke, stroke_fill="black")


def render_collage(
    frames: Sequence[Image.Image],
    texts: Sequence[str],
    *,
    width: int = 1080,
    aspect: tuple[int, int] = (3, 4),
    band_center: float = 0.88,
    hero_center: float = 0.5,
    hero_fraction: float | None = None,
    font_path: str | None = None,
    font_size: int | None = None,
    label: str = DEFAULT_LABEL,
):
    """Return a composed RGB image and measured layout; perform no file writes."""
    if not 2 <= len(texts) <= 7 or len(frames) != len(texts):
        raise ValueError("需要 2—7 句台词，以及与台词数量一致的图片")
    if any(not isinstance(text, str) or not text.strip() or "\n" in text or "\r" in text
           for text in texts):
        raise ValueError("每句台词必须是非空单行文字")
    if width < 360 or width > 4096:
        raise ValueError("图片宽度必须在 360—4096 之间")
    aw, ah = aspect
    if aw <= 0 or ah <= 0 or not 1 <= ah / aw <= 2:
        raise ValueError("宽高比必须是竖图，且高度不超过宽度的两倍")
    if not math.isfinite(band_center) or not 0 <= band_center <= 1:
        raise ValueError("字幕取图位置必须在 0—1 之间")
    if not math.isfinite(hero_center) or not 0 <= hero_center <= 1:
        raise ValueError("主画面取图位置必须在 0—1 之间")
    if font_size is not None and not 12 <= font_size <= width // 8:
        raise ValueError("字号必须在 12 到图片宽度的 1/8 之间")

    height = round(width * ah / aw)
    fraction = choose_hero_fraction(len(texts) - 1, hero_fraction)
    hero_height = round(height * fraction)
    remaining = height - hero_height
    strip_count = len(texts) - 1
    strip_heights = [remaining // strip_count] * strip_count
    strip_heights[-1] += remaining - sum(strip_heights)
    base_font = font_size or max(24, round(width / 18))
    hero = ImageOps.fit(frames[0].convert("RGB"), (width, hero_height),
                        method=Image.Resampling.LANCZOS, centering=(0.5, hero_center))
    line_layouts = [draw_subtitle(
        hero, texts[0], hero_height - strip_heights[0] // 2 - max(4, height // 150),
        font_path, min(base_font, max(16, round(strip_heights[0] * 0.62))),
        round(width * 0.92),
    )]
    draw_label(hero, label, font_path, width)

    canvas = Image.new("RGB", (width, height), "black")
    canvas.paste(hero, (0, 0))
    regions = [{"y": 0, "height": hero_height}]
    y = hero_height
    for frame, text, strip_height in zip(frames[1:], texts[1:], strip_heights):
        frame = frame.convert("RGB")
        source_height = min(frame.height, max(1, round(frame.width * strip_height / width)))
        center_y = round(frame.height * band_center)
        y0 = max(0, min(frame.height - source_height, center_y - source_height // 2))
        band = frame.crop((0, y0, frame.width, y0 + source_height))
        strip = ImageOps.fit(band, (width, strip_height),
                             method=Image.Resampling.LANCZOS, centering=(0.5, 0.5))
        measured = draw_subtitle(
            strip, text, strip_height // 2, font_path,
            min(base_font, max(16, round(strip_height * 0.62))), round(width * 0.92),
        )
        measured["bounds"][1] += y
        measured["bounds"][3] += y
        line_layouts.append(measured)
        canvas.paste(strip, (0, y))
        regions.append({"y": y, "height": strip_height})
        y += strip_height
    return canvas, {"width": width, "height": height, "hero_fraction": fraction,
                    "strip_count": strip_count, "gap": 0, "band_center": band_center,
                    "hero_center": hero_center,
                    "label": label, "regions": regions, "lines": line_layouts}
