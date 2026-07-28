from pathlib import Path

from PIL import Image, ImageDraw, ImageFilter

from app.vision import choose_best_candidate


def test_choose_best_candidate_prefers_sharper_frame(tmp_path: Path) -> None:
    sharp_path = tmp_path / 'sharp.jpg'
    blurry_path = tmp_path / 'blurry.jpg'

    sharp = Image.new('RGB', (320, 320), 'white')
    draw = ImageDraw.Draw(sharp)
    draw.rectangle((40, 40, 280, 280), outline='black', width=10)
    draw.line((40, 40, 280, 280), fill='black', width=8)
    draw.line((280, 40, 40, 280), fill='black', width=8)
    sharp.save(sharp_path)

    blurry = sharp.filter(ImageFilter.GaussianBlur(radius=8))
    blurry.save(blurry_path)

    best, debug = choose_best_candidate([
        (blurry_path, 0.1),
        (sharp_path, 0.2),
    ])

    assert best == sharp_path
    assert debug['selected'] == sharp_path.name
