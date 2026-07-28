import json
import shutil
import uuid
from pathlib import Path

from PIL import Image

from app.beats import apply_plan, build_beats, heuristic_plan
from app.config import Settings
from app.image_styler import stylize_panel
from app.layout import compose_comic
from app.media import assert_ffmpeg_available, extract_audio, extract_frame, probe_duration
from app.models import JobManifest
from app.openrouter_client import plan_panels
from app.transcribe import transcribe_words


class PipelineError(RuntimeError):
    pass


def generate_comic(
    video_path: Path,
    style_reference_path: Path,
    settings: Settings,
) -> JobManifest:
    assert_ffmpeg_available()
    _validate_style_reference(style_reference_path)

    duration = probe_duration(video_path)
    if duration <= 0:
        raise PipelineError("The uploaded video has no duration")
    if duration > settings.max_video_seconds:
        raise PipelineError(
            f"Clip is {duration:.1f}s; MVP limit is {settings.max_video_seconds}s"
        )

    job_id = uuid.uuid4().hex[:12]
    job_dir = settings.work_dir / job_id
    frames_dir = job_dir / "frames"
    panels_dir = job_dir / "panels"
    frames_dir.mkdir(parents=True)
    panels_dir.mkdir(parents=True)

    video_copy = job_dir / f"input{video_path.suffix.lower()}"
    style_copy = job_dir / f"style{style_reference_path.suffix.lower()}"
    shutil.copy2(video_path, video_copy)
    shutil.copy2(style_reference_path, style_copy)

    audio_path = job_dir / "audio.wav"
    extract_audio(video_copy, audio_path)
    words, transcript = transcribe_words(audio_path)
    beats = build_beats(words)
    if not beats:
        raise PipelineError("No usable spoken beats were found")

    used_openrouter = False
    decisions = []
    if settings.openrouter_api_key:
        try:
            decisions = plan_panels(beats, settings.max_panels, settings)
            used_openrouter = bool(decisions)
        except Exception as exc:  # Fall back while preserving debug evidence.
            (job_dir / "openrouter-error.txt").write_text(str(exc), encoding="utf-8")

    if not decisions:
        decisions = heuristic_plan(beats, settings.max_panels)

    selected_beats = apply_plan(beats, decisions)
    if not selected_beats:
        raise PipelineError("Panel planning produced no usable panels")

    output_panels: list[Path] = []
    for position, beat in enumerate(selected_beats):
        source_frame = frames_dir / f"{position:02d}.jpg"
        styled_frame = panels_dir / f"{position:02d}.png"
        extract_frame(video_copy, min(duration - 0.05, beat.frame_time), source_frame)

        if settings.skip_stylization:
            Image.open(source_frame).convert("RGB").save(styled_frame, "PNG")
        else:
            if not settings.openai_api_key:
                raise PipelineError(
                    "OPENAI_API_KEY is required unless SKIP_STYLIZATION=true"
                )
            stylize_panel(
                source_frame,
                style_copy,
                styled_frame,
                panel_kind=beat.kind,
                settings=settings,
            )
        output_panels.append(styled_frame)

    comic_path = job_dir / "comic.png"
    compose_comic(output_panels, selected_beats, comic_path)

    manifest = JobManifest(
        job_id=job_id,
        transcript=transcript,
        beats=selected_beats,
        comic_path=f"/jobs/{job_id}/comic.png",
        used_openrouter=used_openrouter,
        used_stylization=not settings.skip_stylization,
    )
    (job_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    (job_dir / "transcript.json").write_text(
        json.dumps([word.model_dump() for word in words], indent=2), encoding="utf-8"
    )
    return manifest


def _validate_style_reference(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        raise PipelineError("Style reference is not a readable image") from exc
