import base64
from pathlib import Path

import httpx

from app.config import Settings


class ImageStylingError(RuntimeError):
    pass


_ALLOWED_STYLE_STRENGTHS = {"subtle", "balanced", "strong"}


def stylize_panel(
    frame_path: Path,
    style_reference_path: Path,
    output_path: Path,
    *,
    panel_kind: str,
    settings: Settings,
    prompt_suffix: str | None = None,
    style_strength: str = "balanced",
) -> str:
    prompt = build_stylization_prompt(
        panel_kind=panel_kind,
        style_strength=style_strength,
        prompt_suffix=prompt_suffix,
    )

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
        "quality": settings.openai_image_quality,
        "size": "1024x1024",
        "output_format": "png",
    }

    input_fidelity = _input_fidelity_for(style_strength)
    if input_fidelity:
        form["input_fidelity"] = input_fidelity

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
    return prompt


def build_stylization_prompt(
    *,
    panel_kind: str,
    style_strength: str,
    prompt_suffix: str | None = None,
) -> str:
    strength = _normalize_style_strength(style_strength)
    strength_block = {
        "subtle": (
            "Keep the scene and facial proportions fairly close to Image A. "
            "Apply the reference style with restraint: gently adapt the linework, palette, shading, "
            "and texture while keeping the result grounded and faithful to the source frame."
        ),
        "balanced": (
            "Match the style reference clearly rather than defaulting to a generic comic look. "
            "Preserve the identity, pose, and composition from Image A, but allow noticeable stylization in "
            "facial design, shapes, palette, line quality, and rendering technique so the result genuinely feels "
            "drawn in the style of Image B."
        ),
        "strong": (
            "Prioritize the visual language of Image B decisively over photo-real fidelity. "
            "It is acceptable to simplify forms, stylize facial proportions, enlarge or redesign eyes if that matches "
            "Image B, flatten or reshape shading, shift the palette, and introduce the texture and line treatment of "
            "Image B, as long as the person remains recognizable and the performance moment still matches Image A."
        ),
    }[strength]

    prompt = f"""
Edit the provided images. Image A is the source performance frame. Image B is the style reference.

Transform Image A into a finished illustrated panel that adopts the SPECIFIC visual language of Image B.
Do not fall back to a generic comic-book or generic editorial illustration style.

Preserve from Image A:
- the same person and recognizable identity
- the same core expression, emotion, and performance moment
- pose, gesture, camera angle, and overall composition
- the same scene and spatial relationships

Study Image B and imitate as many of these qualities as possible:
- line quality, contour weight, and edge treatment
- shape simplification or exaggeration
- facial-feature design, eye treatment, and character proportions
- palette, color temperature, and contrast
- shading approach (flat, cel-shaded, textured, crosshatched, painterly, etc.)
- texture, grain, halftone, paper feel, or surface finish
- overall mood and degree of stylization

Panel narrative role: {panel_kind}.
{strength_block}

The result should read as an illustrated panel in the style of Image B, not as a lightly filtered photo.
Do not add speech bubbles, captions, logos, watermarks, or panel borders.
""".strip()

    if prompt_suffix:
        prompt = f"{prompt}\n\nAdditional direction: {prompt_suffix.strip()}"
    return prompt


def _normalize_style_strength(style_strength: str) -> str:
    value = (style_strength or "balanced").strip().lower()
    if value not in _ALLOWED_STYLE_STRENGTHS:
        return "balanced"
    return value


def _input_fidelity_for(style_strength: str) -> str | None:
    strength = _normalize_style_strength(style_strength)
    if strength == "subtle":
        return "high"
    if strength == "balanced":
        return None
    return None


def _mime_for(path: Path) -> str:
    suffix = path.suffix.lower()
    return {
        ".png": "image/png",
        ".webp": "image/webp",
        ".jpg": "image/jpeg",
        ".jpeg": "image/jpeg",
    }.get(suffix, "application/octet-stream")
