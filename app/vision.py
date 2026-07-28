from __future__ import annotations

import json
import subprocess
import sys
import tempfile
from pathlib import Path

from PIL import Image

from app.models import FaceBox


def detect_faces_path(image_path: Path) -> list[FaceBox]:
    """Detect faces in an isolated process.

    OpenCV and Faster Whisper/PyAV each bundle FFmpeg libraries on macOS. Loading
    both into one Python process can register duplicate Objective-C AVFoundation
    classes and cause crashes. Keeping OpenCV in a short-lived worker process
    prevents those native libraries from sharing an address space.
    """
    worker_path = Path(__file__).with_name("face_worker.py")
    try:
        result = subprocess.run(
            [sys.executable, str(worker_path), str(image_path)],
            check=False,
            capture_output=True,
            text=True,
            timeout=30,
        )
        output = result.stdout.strip()
        if not output:
            return []
        payload = json.loads(output.splitlines()[-1])
        return [FaceBox.model_validate(item) for item in payload.get("faces", [])]
    except (OSError, subprocess.SubprocessError, json.JSONDecodeError, ValueError):
        # Face detection is a layout enhancement, not a reason to fail the job.
        return []


def detect_faces_image(image: Image.Image) -> list[FaceBox]:
    with tempfile.NamedTemporaryFile(suffix=".png") as temporary:
        image.convert("RGB").save(temporary.name, "PNG")
        return detect_faces_path(Path(temporary.name))


def choose_best_candidate(candidates: list[tuple[Path, float]]):
    """Compatibility helper for tests and future debugging UIs."""
    from app.frame_selection import _score_frame

    scored = [(path, timestamp, _score_frame(path)) for path, timestamp in candidates]
    scored.sort(key=lambda item: item[2], reverse=True)
    best = scored[0]
    return best[0], {
        "selected": best[0].name,
        "timestamp": best[1],
        "scores": [
            {"path": path.name, "timestamp": timestamp, "score": score}
            for path, timestamp, score in scored
        ],
    }
