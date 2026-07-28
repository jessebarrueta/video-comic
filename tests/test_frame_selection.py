from pathlib import Path

from PIL import Image, ImageDraw

from app.frame_selection import _candidate_timestamps, _score_frame
from app.models import Beat, WordTiming


def test_candidate_timestamps_stay_within_beat_and_duration() -> None:
    beat = Beat(
        index=0,
        start=1.0,
        end=2.2,
        text="hello there",
        bubble_text="hello there",
        words=[WordTiming(text="hello", start=1.0, end=1.3), WordTiming(text="there", start=1.4, end=1.8)],
        frame_time=2.0,
    )
    candidates = _candidate_timestamps(beat, duration=3.0)
    assert candidates
    assert all(1.0 <= ts <= 3.0 for ts in candidates)


def test_score_frame_prefers_sharper_image(tmp_path: Path) -> None:
    sharp = tmp_path / "sharp.jpg"
    blurry = tmp_path / "blurry.jpg"

    image = Image.new("RGB", (400, 400), (160, 160, 160))
    draw = ImageDraw.Draw(image)
    for x in range(40, 360, 35):
        draw.line((x, 40, x, 360), fill=(20, 20, 20), width=6)
    for y in range(40, 360, 35):
        draw.line((40, y, 360, y), fill=(20, 20, 20), width=6)
    image.save(sharp)

    image.resize((120, 120), Image.Resampling.BILINEAR).resize((400, 400), Image.Resampling.BILINEAR).save(blurry)

    assert _score_frame(sharp) > _score_frame(blurry)
