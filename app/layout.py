import math
import re
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont, ImageOps

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
        panel = Image.open(panel_path).convert("RGB")
        panel = ImageOps.fit(panel, (rect[2] - rect[0], rect[3] - rect[1]), method=Image.Resampling.LANCZOS)
        page.paste(panel, rect[:2])
        _draw_panel_border(page, rect)
        _draw_speech_bubble(page, rect, beat)

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

    # Keep chronological reading order sacred. The final panel receives the
    # largest slot because spoken-performance clips overwhelmingly place their
    # payoff there, and both the LLM and heuristic planner are instructed to
    # preserve that structure. Its height still responds to emphasis.
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

        # Center an incomplete final row while preserving left-to-right order.
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


def _draw_speech_bubble(
    page: Image.Image,
    rect: tuple[int, int, int, int],
    beat: Beat,
) -> None:
    panel_w = rect[2] - rect[0]
    panel_h = rect[3] - rect[1]
    max_bubble_w = int(panel_w * 0.78)
    font_size = max(22, min(48, int(panel_w / 16)))
    text = _timed_text(beat)

    while True:
        font = _font(font_size)
        lines = _wrap_text(text, font, max_bubble_w - 70)
        line_height = font_size + 9
        required_h = len(lines) * line_height + 56
        if required_h <= int(panel_h * 0.68) or font_size <= 18:
            break
        font_size -= 2

    if not lines:
        return

    bubble_w = min(
        max_bubble_w,
        max(_measure(line, font) for line in lines) + 70,
    )
    bubble_h = min(required_h, int(panel_h * 0.72))

    # Alternate bubble side to avoid a relentlessly mechanical page rhythm.
    left = rect[0] + 30 if beat.index % 2 == 0 else rect[2] - bubble_w - 30
    top = rect[1] + 30
    bubble_rect = (left, top, left + bubble_w, top + bubble_h)

    overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(bubble_rect, radius=42, fill=BUBBLE, outline=INK + (255,), width=7)

    # Simple tail. Exact character tracking is deliberately postponed until the
    # project earns the right to become difficult.
    tail_x = left + (bubble_w * 3 // 4 if beat.index % 2 == 0 else bubble_w // 4)
    tail_y = top + bubble_h
    tail = [
        (tail_x - 18, tail_y - 8),
        (tail_x + 28, tail_y - 7),
        (tail_x + (50 if beat.index % 2 == 0 else -50), min(rect[3] - 28, tail_y + 62)),
    ]
    draw.polygon(tail, fill=BUBBLE, outline=INK + (255,))

    text_y = top + 27
    for line in lines:
        draw.text((left + 35, text_y), line, font=font, fill=INK + (255,))
        text_y += line_height

    page.paste(overlay, (0, 0), overlay)


def _timed_text(beat: Beat) -> str:
    # Convert conspicuous intra-beat pauses into line breaks so timing survives
    # as visible whitespace without asking an image model to render text.
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
