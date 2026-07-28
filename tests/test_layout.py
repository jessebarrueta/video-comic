from pathlib import Path

from PIL import Image

from app.layout import compose_comic
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
