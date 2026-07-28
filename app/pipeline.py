import json
import shutil
import uuid
from pathlib import Path

from PIL import Image

from app.beats import apply_plan, build_beats, heuristic_plan
from app.config import Settings
from app.frame_selection import choose_best_frame
from app.image_styler import stylize_panel
from app.layout import compose_comic
from app.media import assert_ffmpeg_available, extract_audio, probe_duration
from app.models import GeneratedPanel, JobManifest, RegeneratePanelRequest
from app.openrouter_client import plan_panels
from app.transcribe import transcribe_words
from app.vision import detect_faces_path


class PipelineError(RuntimeError):
    pass


def generate_comic(
    video_path: Path,
    style_reference_path: Path,
    settings: Settings,
    *,
    style_strength: str = "balanced",
    source_type: str = "upload",
    source_title: str | None = None,
    source_url: str | None = None,
    source_start: float | None = None,
    source_end: float | None = None,
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
    candidate_frames_dir = job_dir / "frame-candidates"
    panels_dir = job_dir / "panels"
    pages_dir = job_dir / "pages"
    frames_dir.mkdir(parents=True)
    candidate_frames_dir.mkdir(parents=True)
    panels_dir.mkdir(parents=True)
    pages_dir.mkdir(parents=True)

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

    panel_budget = _desired_panel_count(duration, len(beats), settings)
    used_openrouter = False
    decisions = []
    if settings.openrouter_api_key:
        try:
            decisions = plan_panels(beats, panel_budget, settings)
            used_openrouter = bool(decisions)
        except Exception as exc:  # Fall back while preserving debug evidence.
            (job_dir / "openrouter-error.txt").write_text(str(exc), encoding="utf-8")

    if not decisions:
        decisions = heuristic_plan(beats, panel_budget)

    selected_beats = apply_plan(beats, decisions)
    if not selected_beats:
        raise PipelineError("Panel planning produced no usable panels")

    panels: list[GeneratedPanel] = []
    for position, beat in enumerate(selected_beats):
        source_frame = frames_dir / f"{position:02d}.jpg"
        styled_frame = panels_dir / f"{position:02d}.png"
        choose_best_frame(
            video_copy,
            beat,
            duration=duration,
            output_path=source_frame,
            scratch_dir=candidate_frames_dir / f"beat-{position:02d}",
        )

        if settings.skip_stylization:
            Image.open(source_frame).convert("RGB").save(styled_frame, "PNG")
        else:
            if not settings.openai_api_key:
                raise PipelineError(
                    "OPENAI_API_KEY is required unless SKIP_STYLIZATION=true"
                )
            prompt_used = stylize_panel(
                source_frame,
                style_copy,
                styled_frame,
                panel_kind=beat.kind,
                settings=settings,
                style_strength=style_strength,
            )
            (panels_dir / f"{position:02d}.prompt.txt").write_text(prompt_used, encoding="utf-8")

        panels.append(
            GeneratedPanel(
                index=position,
                page_index=position // settings.max_panels_per_page,
                source_frame=_job_url(job_id, source_frame.relative_to(job_dir)),
                styled_frame=_job_url(job_id, styled_frame.relative_to(job_dir)),
                beat=beat,
                face_boxes=detect_faces_path(source_frame),
            )
        )

    manifest = JobManifest(
        job_id=job_id,
        transcript=transcript,
        beats=[panel.beat for panel in panels],
        comic_path="",
        comic_paths=[],
        page_count=0,
        panels=panels,
        style_strength=style_strength,
        source_type=source_type,
        source_title=source_title,
        source_url=source_url,
        source_start=source_start,
        source_end=source_end,
        used_openrouter=used_openrouter,
        used_stylization=not settings.skip_stylization,
    )

    _compose_pages(manifest, job_dir, settings)
    _save_manifest(job_dir, manifest, words)
    return manifest


def regenerate_panel(
    job_id: str,
    panel_index: int,
    request: RegeneratePanelRequest,
    settings: Settings,
) -> JobManifest:
    manifest, job_dir = load_manifest(job_id, settings)
    panel = next((item for item in manifest.panels if item.index == panel_index), None)
    if panel is None:
        raise PipelineError(f"Panel {panel_index} was not found")

    source_path = _job_fs_path(job_dir, panel.source_frame)
    styled_path = _job_fs_path(job_dir, panel.styled_frame)
    style_path = _find_style_reference(job_dir)

    if request.bubble_text:
        panel.beat.bubble_text = request.bubble_text.strip()

    effective_style_strength = request.style_strength or manifest.style_strength

    if settings.skip_stylization:
        Image.open(source_path).convert("RGB").save(styled_path, "PNG")
    else:
        if not settings.openai_api_key:
            raise PipelineError("OPENAI_API_KEY is required to regenerate stylized panels")
        prompt_used = stylize_panel(
            source_path,
            style_path,
            styled_path,
            panel_kind=panel.beat.kind,
            settings=settings,
            prompt_suffix=request.prompt_suffix,
            style_strength=effective_style_strength,
        )
        prompt_path = _job_fs_path(job_dir, panel.styled_frame).with_suffix(".prompt.txt")
        prompt_path.write_text(prompt_used, encoding="utf-8")

    manifest.style_strength = effective_style_strength

    panel.face_boxes = detect_faces_path(source_path)
    manifest.beats = [item.beat for item in manifest.panels]
    _compose_pages(manifest, job_dir, settings)
    _save_manifest(job_dir, manifest)
    return manifest


def load_manifest(job_id: str, settings: Settings) -> tuple[JobManifest, Path]:
    job_dir = settings.work_dir / job_id
    manifest_path = job_dir / "manifest.json"
    if not manifest_path.exists():
        raise PipelineError("Job manifest not found")
    return JobManifest.model_validate_json(manifest_path.read_text(encoding="utf-8")), job_dir


def _compose_pages(manifest: JobManifest, job_dir: Path, settings: Settings) -> None:
    pages_dir = job_dir / "pages"
    pages_dir.mkdir(exist_ok=True)
    comic_paths: list[str] = []

    total_pages = max(1, (len(manifest.panels) + settings.max_panels_per_page - 1) // settings.max_panels_per_page)
    for page_index in range(total_pages):
        chunk = [panel for panel in manifest.panels if panel.page_index == page_index]
        if not chunk:
            continue
        chunk = sorted(chunk, key=lambda item: item.index)
        panel_paths = [_job_fs_path(job_dir, panel.styled_frame) for panel in chunk]
        page_path = pages_dir / f"page-{page_index + 1:02d}.png"
        compose_comic(panel_paths, [panel.beat for panel in chunk], page_path)
        comic_paths.append(_job_url(manifest.job_id, page_path.relative_to(job_dir)))

    manifest.comic_paths = comic_paths
    manifest.page_count = len(comic_paths)
    manifest.comic_path = comic_paths[0] if comic_paths else ""


def _save_manifest(job_dir: Path, manifest: JobManifest, words: list | None = None) -> None:
    (job_dir / "manifest.json").write_text(
        manifest.model_dump_json(indent=2), encoding="utf-8"
    )
    if words is not None:
        (job_dir / "transcript.json").write_text(
            json.dumps([word.model_dump() for word in words], indent=2), encoding="utf-8"
        )


def _desired_panel_count(duration: float, beat_count: int, settings: Settings) -> int:
    desired = max(4, round(duration / 10))
    desired = min(desired, settings.max_total_panels, beat_count)
    if duration > 90:
        desired = min(max(desired, 8), settings.max_total_panels, beat_count)
    return max(1, desired)


def _job_url(job_id: str, relative_path: Path) -> str:
    return f"/jobs/{job_id}/{relative_path.as_posix()}"


def _job_fs_path(job_dir: Path, url_path: str) -> Path:
    marker = f"/jobs/{job_dir.name}/"
    if marker in url_path:
        relative = url_path.split(marker, 1)[1]
        return job_dir / relative
    return job_dir / Path(url_path).name


def _find_style_reference(job_dir: Path) -> Path:
    matches = [*job_dir.glob("style.*")]
    if not matches:
        raise PipelineError("Style reference image not found in job directory")
    return matches[0]


def _validate_style_reference(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        raise PipelineError("Style reference is not a readable image") from exc
