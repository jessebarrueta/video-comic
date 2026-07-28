from __future__ import annotations

import importlib
from pathlib import Path
from typing import Any

from PIL import Image

from app.models import FaceBox

_FACE_DETECTION_STATUS: dict[str, Any] = {
    "available": None,
    "reason": "Not checked yet",
    "version": None,
}


def detect_faces_path(image_path: Path) -> list[FaceBox]:
    """Detect faces when a complete OpenCV binding is available.

    Face detection is an optional enhancement. A missing, partial, or conflicting
    cv2 installation must never prevent comic generation.
    """
    try:
        with Image.open(image_path) as image:
            return detect_faces_image(image)
    except Exception as exc:
        _set_unavailable(f"Face detection failed safely: {exc}")
        return []


def detect_faces_image(image: Image.Image) -> list[FaceBox]:
    cv2 = _load_cv2()
    if cv2 is None:
        return []

    try:
        import numpy as np

        gray = np.asarray(image.convert("L"))
        cascade_path = Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml"
        if not cascade_path.exists():
            _set_unavailable(f"OpenCV Haar cascade file is missing: {cascade_path}")
            return []

        classifier = cv2.CascadeClassifier(str(cascade_path))
        if classifier is None or classifier.empty():
            _set_unavailable("OpenCV could not load its frontal-face Haar cascade")
            return []

        faces = classifier.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=5,
            minSize=(40, 40),
        )
        results = [
            FaceBox(x=int(x), y=int(y), w=int(w), h=int(h))
            for x, y, w, h in faces
        ]
        results.sort(key=lambda box: box.w * box.h, reverse=True)
        _FACE_DETECTION_STATUS.update(
            available=True,
            reason="OpenCV Haar-cascade face detection is available",
            version=getattr(cv2, "__version__", "unknown"),
        )
        return results
    except Exception as exc:
        _set_unavailable(f"OpenCV face detection failed safely: {exc}")
        return []


def face_detection_status() -> dict[str, Any]:
    """Return diagnostic state without making face detection a hard requirement."""
    if _FACE_DETECTION_STATUS["available"] is None:
        _load_cv2()
    return dict(_FACE_DETECTION_STATUS)


def _load_cv2():
    try:
        cv2 = importlib.import_module("cv2")
    except Exception as exc:
        _set_unavailable(f"OpenCV is not installed or could not be imported: {exc}")
        return None

    required = ("CascadeClassifier", "data")
    missing = [name for name in required if not hasattr(cv2, name)]
    if missing:
        module_path = getattr(cv2, "__file__", "unknown location")
        _set_unavailable(
            "The imported cv2 module is incomplete "
            f"(missing {', '.join(missing)}; loaded from {module_path})"
        )
        return None

    if not hasattr(cv2.data, "haarcascades"):
        _set_unavailable("The imported cv2 module does not include Haar cascade data")
        return None

    _FACE_DETECTION_STATUS.update(
        available=True,
        reason="OpenCV appears complete",
        version=getattr(cv2, "__version__", "unknown"),
    )
    return cv2


def _set_unavailable(reason: str) -> None:
    _FACE_DETECTION_STATUS.update(
        available=False,
        reason=reason,
        version=None,
    )


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
