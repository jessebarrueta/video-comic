import base64
from pathlib import Path

import httpx

from app.config import Settings


class ImageStylingError(RuntimeError):
    pass


def stylize_panel(
    frame_path: Path,
    style_reference_path: Path,
    output_path: Path,
    *,
    panel_kind: str,
    settings: Settings,
    prompt_suffix: str | None = None,
) -> None:
    prompt = f"""
Transform the FIRST input image into a polished comic-book panel.
Use the SECOND input image only as a visual style reference for line quality,
color treatment, texture, shading, and overall illustration language.

Preserve from the first image:
- the same people and recognizable facial identity
- pose, gesture, camera angle, framing, and spatial relationships
- the original performance moment

Panel narrative role: {panel_kind}.
Make the image read clearly at comic-panel size. Do not add speech bubbles,
captions, sound-effect lettering, logos, borders, or watermarks. Do not copy
specific characters or content from the style reference.
""".strip()
    if prompt_suffix:
        prompt = f"{prompt}\n\nAdditional direction: {prompt_suffix.strip()}"

    headers = {"Authorization": f"Bearer {settings.openai_api_key}"}
    files = [
        ("image[]", (frame_path.name, frame_path.read_bytes(), "image/jpeg")),
        (
            "image[]",
            (
                style_reference_path.name,
                style_reference_path.read_bytes(),
                _mime_for(style_reference_path),
            ),
        ),
    ]
    form = {
        "model": settings.openai_image_model,
        "prompt": prompt,
        "input_fidelity": "high",
        "quality": settings.openai_image_quality,
        "size": "1024x1024",
        "output_format": "png",
    }

    with httpx.Client(timeout=300.0) as client:
        response = client.post(
            "https://api.openai.com/v1/images/edits",
            headers=headers,
            data=form,
            files=files,
        )

    if response.is_error:
        raise ImageStylingError(
            f"OpenAI image edit failed ({response.status_code}): {response.text[:1000]}"
        )

    data = response.json()
    try:
        encoded = data["data"][0]["b64_json"]
    except (KeyError, IndexError, TypeError) as exc:
        raise ImageStylingError("OpenAI response did not contain image data") from exc

    output_path.write_bytes(base64.b64decode(encoded))


def _mime_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")
