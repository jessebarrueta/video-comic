import math
from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter, ImageFont, ImageStat

from app.models import Beat, FaceBox
from app.vision import detect_faces_image

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
        faces = detect_faces_image(original)
        panel, transformed_faces = _fit_panel_smart(
            original,
            (rect[2] - rect[0], rect[3] - rect[1]),
            faces,
        )
        page.paste(panel, rect[:2])
        _draw_panel_border(page, rect)
        _draw_speech_bubble(page, rect, beat, panel, transformed_faces)

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


def _fit_panel_smart(
    image: Image.Image,
    size: tuple[int, int],
    faces: list[FaceBox],
) -> tuple[Image.Image, list[FaceBox]]:
    target_w, target_h = size
    src_w, src_h = image.size
    target_ratio = target_w / target_h
    src_ratio = src_w / src_h

    crop = (0, 0, src_w, src_h)
    if abs(src_ratio - target_ratio) >= 0.01:
        crop = _suggest_crop_box(image, target_ratio, faces)

    cropped = image.crop(crop)
    resized = cropped.resize(size, Image.Resampling.LANCZOS)
    transformed_faces = _transform_faces(faces, crop, size)
    return resized, transformed_faces


def _suggest_crop_box(
    image: Image.Image,
    target_ratio: float,
    faces: list[FaceBox],
) -> tuple[int, int, int, int]:
    src_w, src_h = image.size
    gray = image.convert("L").resize((320, 320), Image.Resampling.BILINEAR)
    edges = gray.filter(ImageFilter.FIND_EDGES)
    centroid_x, centroid_y = _activity_centroid(edges)
    centroid_y = centroid_y * 0.82 + 0.10

    if faces:
        main_face = faces[0]
        face_cx = (main_face.x + main_face.w / 2) / src_w
        face_cy = (main_face.y + main_face.h / 2) / src_h
        centroid_x = (centroid_x * 0.35) + (face_cx * 0.65)
        centroid_y = (centroid_y * 0.2) + (face_cy * 0.8)

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

    if faces:
        face = faces[0]
        desired_margin = int(face.w * 0.35)
        left = min(left, max(0, face.x - desired_margin))
        left = max(0, min(src_w - crop_w, left))
        top = min(top, max(0, face.y - int(face.h * 0.9)))
        top = max(0, min(src_h - crop_h, top))

    return (left, top, left + crop_w, top + crop_h)


def _transform_faces(
    faces: list[FaceBox],
    crop: tuple[int, int, int, int],
    size: tuple[int, int],
) -> list[FaceBox]:
    left, top, right, bottom = crop
    crop_w = right - left
    crop_h = bottom - top
    sx = size[0] / crop_w
    sy = size[1] / crop_h
    transformed: list[FaceBox] = []
    for face in faces:
        nx = max(0, face.x - left)
        ny = max(0, face.y - top)
        rx = min(crop_w, nx + face.w)
        ry = min(crop_h, ny + face.h)
        if rx <= nx or ry <= ny:
            continue
        transformed.append(
            FaceBox(
                x=int(nx * sx),
                y=int(ny * sy),
                w=int((rx - nx) * sx),
                h=int((ry - ny) * sy),
            )
        )
    transformed.sort(key=lambda box: box.w * box.h, reverse=True)
    return transformed


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
    face_boxes: list[FaceBox],
) -> None:
    panel_w = rect[2] - rect[0]
    panel_h = rect[3] - rect[1]
    text = _timed_text(beat)
    word_count = max(1, len(text.replace("\n", " ").split()))

    # Long dialogue reads better in a wider, shallower balloon. The old layout
    # made narrow balloons and compensated with height, which is how one ends up
    # covering a character's entire forehead with typography.
    width_fraction = 0.82 if word_count >= 14 else 0.74
    max_bubble_w = int(panel_w * width_fraction)
    font_size = max(18, min(36, int(panel_w / 20)))

    while True:
        font = _font(font_size)
        lines = _wrap_text(text, font, max_bubble_w - 48)
        line_height = int(font_size * 1.08)
        required_h = len(lines) * line_height + 36
        required_w = (
            min(max_bubble_w, max(_measure(line, font) for line in lines) + 48)
            if lines
            else 0
        )
        if (
            lines
            and required_h <= int(panel_h * 0.36)
            and required_w <= int(panel_w * 0.84)
        ) or font_size <= 16:
            break
        font_size -= 2

    if not lines:
        return

    bubble_w = required_w
    bubble_h = min(required_h, int(panel_h * 0.40))
    speaker_point_local = _estimate_speaker_point_local(panel_image, face_boxes)
    left_local, top_local, placement = _choose_bubble_position(
        panel_image,
        bubble_w,
        bubble_h,
        face_boxes,
        speaker_point_local,
    )

    left = rect[0] + left_local
    top = rect[1] + top_local
    bubble_rect = (left, top, left + bubble_w, top + bubble_h)
    speaker_point = (rect[0] + speaker_point_local[0], rect[1] + speaker_point_local[1])

    overlay = Image.new("RGBA", page.size, (0, 0, 0, 0))
    draw = ImageDraw.Draw(overlay)
    draw.rounded_rectangle(
        bubble_rect,
        radius=30,
        fill=BUBBLE,
        outline=INK + (255,),
        width=6,
    )

    tail = _tail_polygon_nearest(
        bubble_rect,
        speaker_point,
        face_boxes=face_boxes,
        panel_origin=(rect[0], rect[1]),
    )
    if tail:
        draw.polygon(tail, fill=BUBBLE, outline=INK + (255,))

    text_y = top + 18
    for line in lines:
        draw.text((left + 24, text_y), line, font=font, fill=INK + (255,))
        text_y += line_height

    page.paste(overlay, (0, 0), overlay)


def _choose_bubble_position(
    panel_image: Image.Image,
    bubble_w: int,
    bubble_h: int,
    face_boxes: list[FaceBox] | None,
    speaker_point: tuple[int, int],
) -> tuple[int, int, str]:
    panel_w, panel_h = panel_image.size
    face_boxes = face_boxes or []
    edges = panel_image.convert("L").filter(ImageFilter.FIND_EDGES)
    pad = 16

    x_left = pad
    x_center = max(pad, (panel_w - bubble_w) // 2)
    x_right = max(pad, panel_w - bubble_w - pad)
    y_top = pad
    y_upper = max(pad, int(panel_h * 0.16))
    y_bottom = max(pad, panel_h - bubble_h - pad)

    candidates = {
        "top-left": (x_left, y_top),
        "top-center": (x_center, y_top),
        "top-right": (x_right, y_top),
        "upper-left": (x_left, y_upper),
        "upper-right": (x_right, y_upper),
        "bottom-left": (x_left, y_bottom),
        "bottom-right": (x_right, y_bottom),
    }

    scored: list[tuple[float, int, int, str]] = []
    for name, (left, top) in candidates.items():
        right = min(panel_w, left + bubble_w)
        bottom = min(panel_h, top + bubble_h)
        box = (left, top, right, bottom)
        region = edges.crop(box)
        activity = ImageStat.Stat(region).mean[0]

        face_overlap = sum(_overlap_area(box, face_rect(face)) for face in face_boxes)
        face_penalty = face_overlap / max(1, bubble_w * bubble_h) * 520.0

        nearest = _nearest_point_on_rect(box, speaker_point)
        distance = math.dist(nearest, speaker_point)
        distance_penalty = distance / max(1.0, math.hypot(panel_w, panel_h)) * 38.0

        placement_penalty = 0.0
        if name.startswith("bottom"):
            placement_penalty += 10.0
        if name.startswith("upper"):
            placement_penalty += 3.0
        if name.endswith("right"):
            placement_penalty += 1.0

        scored.append(
            (
                activity + face_penalty + distance_penalty + placement_penalty,
                left,
                top,
                name,
            )
        )

    scored.sort(key=lambda item: item[0])
    _, left, top, name = scored[0]
    return left, top, name


def face_rect(face: FaceBox) -> tuple[int, int, int, int]:
    return (face.x, face.y, face.x + face.w, face.y + face.h)


def _overlap_area(a: tuple[int, int, int, int], b: tuple[int, int, int, int]) -> int:
    left = max(a[0], b[0])
    top = max(a[1], b[1])
    right = min(a[2], b[2])
    bottom = min(a[3], b[3])
    if right <= left or bottom <= top:
        return 0
    return (right - left) * (bottom - top)


def _estimate_speaker_point_local(
    panel_image: Image.Image,
    face_boxes: list[FaceBox],
) -> tuple[int, int]:
    panel_w, panel_h = panel_image.size
    if face_boxes:
        face = face_boxes[0]
        # Aim near the lower-middle face boundary, not through the center of the
        # face. It reads as a speaker pointer without becoming facial fencing.
        return (
            max(8, min(panel_w - 8, face.x + face.w // 2)),
            max(8, min(panel_h - 8, face.y + int(face.h * 0.82))),
        )

    centroid_x, centroid_y = _activity_centroid(
        panel_image.convert("L").resize((320, 320), Image.Resampling.BILINEAR).filter(ImageFilter.FIND_EDGES)
    )
    return (
        int(panel_w * centroid_x),
        int(panel_h * min(0.78, centroid_y + 0.12)),
    )


def _nearest_point_on_rect(
    rect: tuple[int, int, int, int],
    point: tuple[int, int],
) -> tuple[int, int]:
    left, top, right, bottom = rect
    px, py = point
    clamped_x = max(left, min(right, px))
    clamped_y = max(top, min(bottom, py))

    # If the point projects inside the rectangle, force the nearest boundary.
    if left < px < right and top < py < bottom:
        distances = {
            "left": px - left,
            "right": right - px,
            "top": py - top,
            "bottom": bottom - py,
        }
        edge = min(distances, key=distances.get)
        if edge == "left":
            return left, py
        if edge == "right":
            return right, py
        if edge == "top":
            return px, top
        return px, bottom

    return int(clamped_x), int(clamped_y)


def _tail_polygon_nearest(
    bubble_rect: tuple[int, int, int, int],
    speaker_point: tuple[int, int],
    *,
    face_boxes: list[FaceBox],
    panel_origin: tuple[int, int],
) -> list[tuple[int, int]]:
    bubble_center = (
        (bubble_rect[0] + bubble_rect[2]) // 2,
        (bubble_rect[1] + bubble_rect[3]) // 2,
    )

    target = speaker_point
    if face_boxes:
        face = face_boxes[0]
        face_global = (
            panel_origin[0] + face.x,
            panel_origin[1] + face.y,
            panel_origin[0] + face.x + face.w,
            panel_origin[1] + face.y + face.h,
        )
        # Point to the nearest edge of the face rather than slicing across it.
        target = _nearest_point_on_rect(face_global, bubble_center)

    base = _nearest_point_on_rect(bubble_rect, target)
    dx = target[0] - base[0]
    dy = target[1] - base[1]
    distance = math.hypot(dx, dy)
    if distance < 8:
        return []

    # A narrow base keeps even a moderately long tail from becoming a giant
    # white spear. Width scales gently and remains capped.
    half_width = max(6.0, min(13.0, distance * 0.035))
    perp_x = -dy / distance
    perp_y = dx / distance
    base_a = (
        int(base[0] + perp_x * half_width),
        int(base[1] + perp_y * half_width),
    )
    base_b = (
        int(base[0] - perp_x * half_width),
        int(base[1] - perp_y * half_width),
    )
    return [base_a, base_b, (int(target[0]), int(target[1]))]


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
