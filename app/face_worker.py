from __future__ import annotations

import json
import sys
from pathlib import Path


def main() -> int:
    if len(sys.argv) != 2:
        print(json.dumps({"error": "expected one image path"}))
        return 2

    image_path = Path(sys.argv[1])
    try:
        import cv2  # type: ignore

        image = cv2.imread(str(image_path))
        if image is None:
            print(json.dumps({"error": "could not read image"}))
            return 3

        gray = cv2.cvtColor(image, cv2.COLOR_BGR2GRAY)
        classifier = cv2.CascadeClassifier(
            str(Path(cv2.data.haarcascades) / "haarcascade_frontalface_default.xml")
        )
        faces = classifier.detectMultiScale(
            gray,
            scaleFactor=1.08,
            minNeighbors=5,
            minSize=(40, 40),
        )
        payload = [
            {"x": int(x), "y": int(y), "w": int(w), "h": int(h)}
            for x, y, w, h in faces
        ]
        payload.sort(key=lambda box: box["w"] * box["h"], reverse=True)
        print(json.dumps({"faces": payload}))
        return 0
    except Exception as exc:
        print(json.dumps({"error": str(exc)}))
        return 1


if __name__ == "__main__":
    raise SystemExit(main())
