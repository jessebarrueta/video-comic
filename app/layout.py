import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageOps, ImageStat

from app.models import Beat

PAGE_W = 1536
PAGE_H = 2048
MARGIN = 54
GUTTER = 22
INK = (18, 18, 18)
PAPER = (247, 243, 232)
BUBBLE = (255, 255, 255, 242)


def compose_comic(
    panel_paths: list[Path],
    beats: list[Beat],
    output_path: Path,
) -> None:
    if not panel_paths or len(panel_paths) != len(beats):
        raise ValueError("Panel images and beats must be non-empty and aligned")

    page = Image.new("RGB", (PAGE_W, PAGE_H), PAPER)
    rects = _layout_rects(len(panel_paths), beats)

    for panel_path, beat, rect in zip(panel_paths, beats, rects, strict=True):
        original = Image.open(panel_path).convert("RGB")
        panel = _fit_panel_smart(original, (rect[2] - rect[0], rect[3] - rect[1]))
        page.paste(panel, rect[:2])
        _draw_panel_border(page, rect)
        _draw_speech_bubble(page, rect, beat, panel)

    page.save(output_path, "PNG", optimize=True)


def _layout_rects(count: int, beats: list[Beat]) -> list[tuple[int, int, int, int]]:
    usable_w = PAGE_W - 2 * MARGIN
    usable_h = PAGE_H - 2 * MARGIN

    if count == 1:
        return [(MARGIN, MARGIN, PAGE_W - MARGIN, PAGE_H - MARGIN)]

    if count == 2:
        h = (usable_h - GUTTER) // 2
        return [
            (MARGIN, MARGIN, PAGE_W - MARGIN, MARGIN + h),
            (MARGIN, MARGIN + h + GUTTER, PAGE_W - MARGIN, PAGE_H - MARGIN),
        ]

    ending_importance = beats[-1].importance
    hero_fraction = min(0.50, max(0.34, 0.36 + 0.035 * ending_importance))
    hero_h = int(usable_h * hero_fraction)
    grid_h = usable_h - hero_h - GUTTER
    small_count = count - 1
    cols = 2 if small_count <= 4 else 3
    rows = math.ceil(small_count / cols)
    small_w = (usable_w - (cols - 1) * GUTTER) // cols
    small_h = (grid_h - (rows - 1) * GUTTER) // rows

    rects: list[tuple[int, int, int, int]] = []
    for i in range(small_count):
        row = i // cols
        col = i % cols
        items_in_row = min(cols, small_count - row * cols)
        row_width = items_in_row * small_w + (items_in_row - 1) * GUTTER
        row_left = MARGIN + (usable_w - row_width) // 2
        x0 = row_left + col * (small_w + GUTTER)
        y0 = MARGIN + row * (small_h + GUTTER)
        rects.append((x0, y0, x0 + small_w, y0 + small_h))

    hero_top = MARGIN + grid_h + GUTTER
    rects.append((MARGIN, hero_top, PAGE_W - MARGIN, PAGE_H - MARGIN))
    return rects


def _draw_panel_border(page: Image.Image, rect: tuple[int, int, int, int]) -> None:
    draw = ImageDraw.Draw(page)
    draw.rectangle(rect, outline=INK, width=9)


def _font(size: int) -> ImageFont.FreeTypeFont | ImageFont.ImageFont:
    candidates = [
        "/System/Library/Fonts/Supplemental/Arial Bold.ttf",
        "/System/Library/Fonts/Supplemental/Arial.ttf",
        "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    ]
    for candidate in candidates:
        try:
            return ImageFont.truetype(candidate, size=size)
        except OSError:
            pass
    return ImageFont.load_default()


def _fit_panel_smart(image: Image.Image, size: tuple[int, int]) -> Image.Image:
    target_w, target_h = size
    src_w, src_h = image.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    if abs(src_ratio - target_ratio) < 0.01:
        return image.resize(size, Image.Resampling.LANCZOS)

    crop = _suggest_crop_box(image, target_ratio)
    cropped = image.crop(crop)
    return cropped.resize(size, Image.Resampling.LANCZOS)


def _suggest_crop_box(image: Image.Image, target_ratio: float) -> tuple[int, int, int, int]:
    src_w, src_h = image.size
    gray = image.convert("L").resize((320, 320), Image.Resampling.BILINEAR)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    centroid_x, centroid_y = _activity_centroid(edges)

    # Bias slightly upward to preserve faces and de-emphasize lower-corner watermarks.
    centroid_y = centroid_y * 0.82 + 0.10

    if (src_w / src_h) > target_ratio:
        crop_h = src_h
        crop_w = int(crop_h * target_ratio)
    else:
        crop_w = src_w
        crop_h = int(crop_w / target_ratio)

    center_x = int(src_w * centroid_x)
    center_y = int(src_h * centroid_y)
    left = max(0, min(src_w - crop_w, center_x - crop_w // 2))
    top = max(0, min(src_h - crop_h, center_y - crop_h // 2))
    return (left, top, left + crop_w, top + crop_h)


def _activity_centroid(edges: Image.Image) -> tuple[float, float]:
    width, height = edges.size
    pixels = edges.load()
    total = 0
    weighted_x = 0
    weighted_y = 0
    for y in range(height):
        for x in range(width):
            weight = max(1, int(pixels[x, y]))
            total += weight
            weighted_x += x * weight
            weighted_y += y * weight
    return weighted_x / total / width, weighted_y / total / height


def _draw_speech_bubble(
    page: Image.Image,
    rect: tuple[int, int, int, int],
    beat: Beat,
    panel_image: Image.Image,
) -> None:
    panel_w = rect[2] - rect[0]
    panel_h = rect[3] - rect[1]
    max_bubble_w = int(panel_w * 0.70)
    font_size = max(20, min(40, int(panel_w / 18)))
    text = _timed_text(beat)

    while True:
        font = _font(font_size)
        lines = _wrap_text(text, font, max_bubble_w - 56)
        line_height = int(font_size * 1.12)
        required_h = len(lines) * line_height + 44
        required_w = min(max_bubble_w, max(_measure(line, font) for line in lines) + 56) if lines else 0
        if (
            lines
            and required_h <= int(panel_h * 0.48)
            and required_w <= int(panel_w * 0.72)
        ) or font_size <= 17:
            break
        font_size -= 2

    if not lines:
        return

    bubble_w = required_w
    bubble_h = min(required_h, int(panel_h * 0.52))
    anchor = _choose_bubble_anchor(panel_image, bubble_w, bubble_h)
    left, top = _anchor_to_position(rect, bubble_w, bubble_h, anchor)
    bubble_rect = (left, top, left + bubble_w, top + bubble_h)

    overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(bubble_rect, radius=34, fill=BUBBLE, outline=INK + (255,), width=6)

    speaker_point = _estimate_speaker_point(rect, anchor)
    tail = _tail_polygon(bubble_rect, anchor, speaker_point)
    draw.polygon(tail, fill=BUBBLE, outline=INK + (255,))

    text_y = top + 22
    for line in lines:
        draw.text((left + 28, text_y), line, font=font, fill=INK + (255,))
        text_y += line_height

    page.paste(overlay, (0, 0), overlay)


def _choose_bubble_anchor(panel_image: Image.Image, bubble_w: int, bubble_h: int) -> str:
    panel_w, panel_h = panel_image.size
    normalized = panel_image.convert("L").filter(ImageFilter.FIND_EDGES)
    candidates = {
        "top-left": (16, 16),
        "top-right": (panel_w - bubble_w - 16, 16),
        "bottom-left": (16, panel_h - bubble_h - 16),
        "bottom-right": (panel_w - bubble_w - 16, panel_h - bubble_h - 16),
    }

    scores: list[tuple[float, str]] = []
    for name, (left, top) in candidates.items():
        left = max(0, left)
        top = max(0, top)
        right = min(panel_w, left + bubble_w)
        bottom = min(panel_h, top + bubble_h)
        region = normalized.crop((left, top, right, bottom))
        activity = ImageStat.Stat(region).mean[0]
        penalty = 0.0
        if name.startswith("bottom"):
            penalty += 6.0
        if name == "bottom-right":
            penalty += 2.0  # mild anti-watermark bias without punishing clean top-right space
        scores.append((activity + penalty, name))

    scores.sort(key=lambda item: item[0])
    return scores[0][1]


def _anchor_to_position(
    rect: tuple[int, int, int, int],
    bubble_w: int,
    bubble_h: int,
    anchor: str,
) -> tuple[int, int]:
    x_pad = 26
    y_pad = 24
    if anchor == "top-left":
        return rect[0] + x_pad, rect[1] + y_pad
    if anchor == "top-right":
        return rect[2] - bubble_w - x_pad, rect[1] + y_pad
    if anchor == "bottom-left":
        return rect[0] + x_pad, rect[3] - bubble_h - y_pad
    return rect[2] - bubble_w - x_pad, rect[3] - bubble_h - y_pad


def _estimate_speaker_point(rect: tuple[int, int, int, int], anchor: str) -> tuple[int, int]:
    panel_w = rect[2] - rect[0]
    panel_h = rect[3] - rect[1]
    if anchor == "top-left":
        return rect[0] + int(panel_w * 0.62), rect[1] + int(panel_h * 0.58)
    if anchor == "top-right":
        return rect[0] + int(panel_w * 0.38), rect[1] + int(panel_h * 0.58)
    if anchor == "bottom-left":
        return rect[0] + int(panel_w * 0.60), rect[1] + int(panel_h * 0.42)
    return rect[0] + int(panel_w * 0.40), rect[1] + int(panel_h * 0.42)


def _tail_polygon(
    bubble_rect: tuple[int, int, int, int],
    anchor: str,
    speaker_point: tuple[int, int],
) -> list[tuple[int, int]]:
    left, top, right, bottom = bubble_rect
    if anchor == "top-left":
        base_x = left + int((right - left) * 0.76)
        base_y = bottom
        return [(base_x - 18, base_y - 6), (base_x + 20, base_y - 6), speaker_point]
    if anchor == "top-right":
        base_x = left + int((right - left) * 0.24)
        base_y = bottom
        return [(base_x - 20, base_y - 6), (base_x + 18, base_y - 6), speaker_point]
    if anchor == "bottom-left":
        base_x = left + int((right - left) * 0.72)
        base_y = top
        return [(base_x - 18, base_y + 6), (base_x + 20, base_y + 6), speaker_point]
    base_x = left + int((right - left) * 0.28)
    base_y = top
    return [(base_x - 20, base_y + 6), (base_x + 18, base_y + 6), speaker_point]


def _timed_text(beat: Beat) -> str:
    if len(beat.words) < 2:
        return beat.bubble_text

    selected_words = beat.bubble_text.split()
    original_words = [word.text for word in beat.words]
    if len(selected_words) != len(original_words):
        return beat.bubble_text

    chunks: list[str] = [original_words[0]]
    for previous, word in zip(beat.words[:-1], beat.words[1:], strict=True):
        separator = "\n" if word.start - previous.end >= 0.42 else " "
        chunks.append(separator + word.text)
    return "".join(chunks)


def _measure(text: str, font: ImageFont.ImageFont) -> int:
    box = font.getbbox(text)
    return box[2] - box[0]


def _wrap_text(text: str, font: ImageFont.ImageFont, max_width: int) -> list[str]:
    paragraphs = text.split("\n")
    lines: list[str] = []
    for paragraph in paragraphs:
        words = paragraph.split()
        current = ""
        for word in words:
            candidate = word if not current else f"{current} {word}"
            if _measure(candidate, font) <= max_width:
                current = candidate
            else:
                if current:
                    lines.append(current)
                current = word
        if current:
            lines.append(current)
        if paragraph != paragraphs[-1]:
            lines.append("…")
    return lines[:8]
