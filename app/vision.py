from __future__ import annotations

from pathlib import Path

from PIL import Image

from app.models import FaceBox

try:
    import cv2  # type: ignore
except Exception:  # pragma: no cover - dependency is optional at runtime
    cv2 = None


def detect_faces_path(image_path: Path) -> list[FaceBox]:
    with Image.open(image_path) as image:
        return detect_faces_image(image)


def detect_faces_image(image: Image.Image) -> list[FaceBox]:
    if cv2 is None:
        return []

    gray = cv2.cvtColor(_pil_to_bgr(image), cv2.COLOR_BGR2GRAY)
    classifier = cv2.CascadeClassifier(
        str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
    )
    faces = classifier.detectMultiScale(
        gray,
        scaleFactor=1.08,
        minNeighbors=5,
        minSize=(40, 40),
    )
    results = [FaceBox(x=int(x), y=int(y), w=int(w), h=int(h)) for x, y, w, h in faces]
    results.sort(key=lambda box: box.w * box.h, reverse=True)
    return results


def _pil_to_bgr(image: Image.Image):
    import numpy as np

    rgb = image.convert("RGB")
    array = np.array(rgb)
    return cv2.cvtColor(array, cv2.COLOR_RGB2BGR)


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
