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
from app.models import Beat, JobManifest
from app.openrouter_client import plan_panels
from app.transcribe import transcribe_words
from app.vision import choose_best_candidate


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
    candidates_dir = job_dir / "frame-candidates"
    panels_dir = job_dir / "panels"
    frames_dir.mkdir(parents=True)
    candidates_dir.mkdir(parents=True)
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

    selection_debug: dict[str, object] = {"panels": []}
    output_panels: list[Path] = []
    for position, beat in enumerate(selected_beats):
        source_frame = frames_dir / f"{position:02d}.jpg"
        styled_frame = panels_dir / f"{position:02d}.png"

        chosen_frame, selection_info = _select_source_frame(
            video_copy,
            beat,
            duration,
            candidates_dir / f"panel-{position:02d}",
            source_frame,
        )
        selection_debug["panels"].append(
            {
                "panel_index": position,
                "beat_index": beat.index,
                "beat_text": beat.text,
                **selection_info,
                "final_source_frame": chosen_frame.name,
            }
        )

        if settings.skip_stylization:
            Image.open(chosen_frame).convert("RGB").save(styled_frame, "PNG")
        else:
            if not settings.openai_api_key:
                raise PipelineError(
                    "OPENAI_API_KEY is required unless SKIP_STYLIZATION=true"
                )
            stylize_panel(
                chosen_frame,
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
    (job_dir / "frame-selection.json").write_text(
        json.dumps(selection_debug, indent=2), encoding="utf-8"
    )
    return manifest


def _candidate_times(beat: Beat, clip_duration: float) -> list[float]:
    duration = max(0.15, beat.end - beat.start)
    anchors = [0.15, 0.35, 0.55, 0.78, 0.92]
    times = []
    for anchor in anchors:
        timestamp = beat.start + duration * anchor
        times.append(min(max(0.0, timestamp), max(0.0, clip_duration - 0.05)))
    # Preserve the originally computed frame time as an explicit candidate.
    times.append(min(max(0.0, beat.frame_time), max(0.0, clip_duration - 0.05)))
    # Dedupe while preserving order.
    unique: list[float] = []
    seen = set()
    for timestamp in times:
        rounded = round(timestamp, 3)
        if rounded not in seen:
            unique.append(timestamp)
            seen.add(rounded)
    return unique


def _select_source_frame(
    video_path: Path,
    beat: Beat,
    clip_duration: float,
    candidate_dir: Path,
    destination: Path,
) -> tuple[Path, dict[str, object]]:
    candidate_dir.mkdir(parents=True, exist_ok=True)
    candidates: list[tuple[Path, float]] = []
    for index, timestamp in enumerate(_candidate_times(beat, clip_duration)):
        candidate_path = candidate_dir / f"candidate-{index:02d}.jpg"
        extract_frame(video_path, timestamp, candidate_path)
        candidates.append((candidate_path, timestamp))

    best_path, debug = choose_best_candidate(candidates)
    shutil.copy2(best_path, destination)
    return destination, debug


def _validate_style_reference(path: Path) -> None:
    try:
        with Image.open(path) as image:
            image.verify()
    except Exception as exc:
        raise PipelineError("Style reference is not a readable image") from exc
