from pathlib import Path

from PIL import Image, ImageDraw

from app.layout import (
    _choose_bubble_position,
    _tail_polygon_nearest,
    compose_comic,
)
from app.models import Beat, FaceBox, WordTiming


def test_compose_comic(tmp_path: Path) -> None:
    panels = []
    beats = []
    for index in range(4):
        panel_path = tmp_path / f"panel-{index}.png"
        Image.new("RGB", (800, 800), (180 + index * 10, 180, 180)).save(panel_path)
        panels.append(panel_path)
        beats.append(
            Beat(
                index=index,
                start=index,
                end=index + 1,
                text=f"Panel {index}",
                bubble_text=f"Panel {index}",
                words=[
                    WordTiming(text="Panel", start=index, end=index + 0.2),
                    WordTiming(text=str(index), start=index + 0.7, end=index + 0.9),
                ],
                importance=5 if index == 3 else 2,
                frame_time=index + 0.8,
            )
        )

    output = tmp_path / "comic.png"
    compose_comic(panels, beats, output)

    assert output.exists()
    with Image.open(output) as result:
        assert result.size == (1536, 2048)


def test_choose_bubble_position_prefers_quiet_side() -> None:
    image = Image.new("RGB", (600, 400), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    for step in range(0, 280, 18):
        draw.line((step, 0, step, 240), fill=(30, 30, 30), width=4)
        draw.line((0, step, 280, step), fill=(30, 30, 30), width=4)

    left, top, name = _choose_bubble_position(
        image,
        220,
        110,
        [],
        speaker_point=(430, 230),
    )
    assert name in {"top-right", "upper-right", "bottom-right"}
    assert left > 250
    assert top >= 0


def test_tail_is_narrow_and_points_to_face_edge() -> None:
    bubble = (20, 20, 260, 110)
    face = FaceBox(x=320, y=120, w=120, h=160)
    tail = _tail_polygon_nearest(
        bubble,
        (380, 250),
        face_boxes=[face],
        panel_origin=(0, 0),
    )

    assert len(tail) == 3
    base_width = ((tail[0][0] - tail[1][0]) ** 2 + (tail[0][1] - tail[1][1]) ** 2) ** 0.5
    assert base_width <= 28
    # The point should land on the face boundary rather than crossing to its center.
    assert tail[2][0] in {face.x, face.x + face.w} or tail[2][1] in {face.y, face.y + face.h}
