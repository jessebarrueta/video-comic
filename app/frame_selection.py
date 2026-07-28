from __future__ import annotations

from pathlib import Path
from statistics import mean

from PIL import Image, ImageFilter, ImageStat

from app.media import extract_frame
from app.models import Beat


class FrameSelectionError(RuntimeError):
    pass


def choose_best_frame(
    video_path: Path,
    beat: Beat,
    *,
    duration: float,
    output_path: Path,
    scratch_dir: Path,
) -> Path:
    """Extract several nearby candidate frames and keep the sharpest, most readable one."""

    scratch_dir.mkdir(parents=True, exist_ok=True)
    candidates = _candidate_timestamps(beat, duration)
    if not candidates:
        raise FrameSelectionError("No candidate timestamps were produced")

    scored: list[tuple[float, Path]] = []
    for index, ts in enumerate(candidates):
        candidate_path = scratch_dir / f"cand-{index:02d}.jpg"
        extract_frame(video_path, ts, candidate_path)
        scored.append((_score_frame(candidate_path), candidate_path))

    scored.sort(key=lambda item: item[0], reverse=True)
    best_path = scored[0][1]
    output_path.write_bytes(best_path.read_bytes())
    return output_path


def _candidate_timestamps(beat: Beat, duration: float) -> list[float]:
    start = max(0.0, beat.start)
    end = min(duration - 0.05, max(beat.end, start + 0.05))
    midpoint = (start + end) / 2.0
    anchor = min(end, max(start, beat.frame_time or midpoint))

    points = {
        round(start + min(0.22, max(0.0, end - start) * 0.18), 3),
        round(midpoint, 3),
        round(anchor, 3),
        round(max(start, anchor - 0.18), 3),
        round(min(end, anchor + 0.12), 3),
        round(max(start, end - 0.1), 3),
    }
    return sorted(point for point in points if 0.0 <= point <= duration)


def _score_frame(path: Path) -> float:
    with Image.open(path) as image:
        rgb = image.convert("RGB")
        gray = rgb.convert("L")
        small = gray.resize((320, 320), Image.Resampling.BILINEAR)
        edges = small.filter(ImageFilter.FIND_EDGES)
        edge_stat = ImageStat.Stat(edges)
        lum_stat = ImageStat.Stat(small)

        sharpness = edge_stat.var[0]
        contrast = lum_stat.stddev[0]
        brightness = lum_stat.mean[0]
        exposure_penalty = abs(brightness - 148.0) / 20.0

        center_detail = _region_mean(edges, (0.2, 0.18, 0.8, 0.82))
        corner_noise = mean(
            [
                _region_mean(edges, (0.0, 0.0, 0.25, 0.25)),
                _region_mean(edges, (0.75, 0.0, 1.0, 0.25)),
                _region_mean(edges, (0.0, 0.75, 0.25, 1.0)),
                _region_mean(edges, (0.75, 0.75, 1.0, 1.0)),
            ]
        )

        # Favor readable, well-exposed frames with detail concentrated near the subject.
        return (
            sharpness * 1.7
            + contrast * 2.2
            + center_detail * 1.4
            - corner_noise * 0.55
            - exposure_penalty * 8.0
        )


def _region_mean(image: Image.Image, box_fraction: tuple[float, float, float, float]) -> float:
    width, height = image.size
    left = int(width * box_fraction[0])
    top = int(height * box_fraction[1])
    right = int(width * box_fraction[2])
    bottom = int(height * box_fraction[3])
    region = image.crop((left, top, right, bottom))
    return float(ImageStat.Stat(region).mean[0])
