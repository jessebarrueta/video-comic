import importlib
from types import SimpleNamespace

from PIL import Image

import app.vision as vision


def test_incomplete_cv2_is_non_fatal(monkeypatch) -> None:
    original_import_module = importlib.import_module

    def fake_import(name: str):
        if name == "cv2":
            return SimpleNamespace(__file__="fake/cv2.py", __version__="broken")
        return original_import_module(name)

    monkeypatch.setattr(vision.importlib, "import_module", fake_import)
    faces = vision.detect_faces_image(Image.new("RGB", (200, 200), "white"))

    assert faces == []
    status = vision.face_detection_status()
    assert status["available"] is False
    assert "incomplete" in status["reason"]
