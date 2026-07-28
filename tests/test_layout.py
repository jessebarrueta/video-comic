from pathlib import Path

from PIL import Image, ImageDraw

from app.layout import _choose_bubble_anchor, compose_comic
from app.models import Beat, WordTiming


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


def test_choose_bubble_anchor_prefers_empty_corner() -> None:
    image = Image.new("RGB", (600, 400), (240, 240, 240))
    draw = ImageDraw.Draw(image)
    # Make the left side busy with visible edges so the bubble logic should prefer top-right.
    for step in range(0, 280, 18):
        draw.line((step, 0, step, 240), fill=(30, 30, 30), width=4)
        draw.line((0, step, 280, step), fill=(30, 30, 30), width=4)
    anchor = _choose_bubble_anchor(image, 220, 110)
    assert anchor == "top-right"
