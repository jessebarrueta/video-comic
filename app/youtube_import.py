from __future__ import annotations

import importlib.util
import json
import subprocess
import sys
from dataclasses import dataclass
from pathlib import Path
from urllib.parse import urlparse


class YouTubeImportError(RuntimeError):
    pass


@dataclass(frozen=True)
class YouTubeMetadata:
    title: str
    duration: float | None
    webpage_url: str


@dataclass(frozen=True)
class ImportedYouTubeClip:
    path: Path
    metadata: YouTubeMetadata
    start: float
    end: float


_VIDEO_SUFFIXES = {".mp4", ".mkv", ".webm", ".mov", ".m4v"}


def youtube_import_status() -> dict[str, object]:
    available = importlib.util.find_spec("yt_dlp") is not None
    return {
        "available": available,
        "runner": f"{sys.executable} -m yt_dlp" if available else None,
        "reason": None if available else "yt-dlp is not installed in this virtual environment",
    }


def parse_timestamp(value: str, *, field_name: str = "time") -> float:
    raw = (value or "").strip()
    if not raw:
        raise YouTubeImportError(f"{field_name.capitalize()} is required")

    try:
        if ":" not in raw:
            seconds = float(raw)
        else:
            parts = raw.split(":")
            if len(parts) not in {2, 3}:
                raise ValueError
            numeric = [float(part) for part in parts]
            if any(part < 0 for part in numeric):
                raise ValueError
            if len(parts) == 2:
                minutes, second_part = numeric
                if second_part >= 60:
                    raise ValueError
                seconds = minutes * 60 + second_part
            else:
                hours, minutes, second_part = numeric
                if minutes >= 60 or second_part >= 60:
                    raise ValueError
                seconds = hours * 3600 + minutes * 60 + second_part
    except ValueError as exc:
        raise YouTubeImportError(
            f"Invalid {field_name}: {raw!r}. Use seconds, MM:SS, or HH:MM:SS."
        ) from exc

    if seconds < 0:
        raise YouTubeImportError(f"{field_name.capitalize()} cannot be negative")
    return seconds


def validate_youtube_url(url: str) -> str:
    normalized = (url or "").strip()
    if not normalized:
        raise YouTubeImportError("YouTube URL is required")

    parsed = urlparse(normalized)
    if parsed.scheme not in {"http", "https"}:
        raise YouTubeImportError("YouTube URL must begin with http:// or https://")

    hostname = (parsed.hostname or "").lower().rstrip(".")
    allowed = (
        hostname == "youtu.be"
        or hostname == "youtube.com"
        or hostname.endswith(".youtube.com")
        or hostname == "youtube-nocookie.com"
        or hostname.endswith(".youtube-nocookie.com")
    )
    if not allowed:
        raise YouTubeImportError("Only YouTube and youtu.be URLs are supported")
    return normalized


def inspect_youtube(url: str, *, timeout_seconds: int = 120) -> YouTubeMetadata:
    validated_url = validate_youtube_url(url)
    _require_ytdlp()

    result = _run_ytdlp(
        [
            "--dump-single-json",
            "--skip-download",
            "--no-playlist",
            validated_url,
        ],
        timeout_seconds=timeout_seconds,
    )

    try:
        payload = json.loads(result.stdout)
    except json.JSONDecodeError as exc:
        raise YouTubeImportError("yt-dlp returned unreadable video metadata") from exc

    duration_value = payload.get("duration")
    try:
        duration = float(duration_value) if duration_value is not None else None
    except (TypeError, ValueError):
        duration = None

    title = str(payload.get("title") or "YouTube clip").strip()
    webpage_url = str(payload.get("webpage_url") or validated_url).strip()
    return YouTubeMetadata(title=title, duration=duration, webpage_url=webpage_url)


def download_youtube_section(
    url: str,
    *,
    start: float,
    end: float,
    output_dir: Path,
    max_clip_seconds: float,
    timeout_seconds: int = 900,
) -> ImportedYouTubeClip:
    validated_url = validate_youtube_url(url)
    _require_ytdlp()

    if start < 0:
        raise YouTubeImportError("Start time cannot be negative")
    if end <= start:
        raise YouTubeImportError("Out time must be after in time")

    selected_duration = end - start
    if selected_duration > max_clip_seconds:
        raise YouTubeImportError(
            f"Selected section is {selected_duration:.1f}s; the limit is {max_clip_seconds:.0f}s"
        )

    metadata = inspect_youtube(validated_url, timeout_seconds=min(timeout_seconds, 180))
    if metadata.duration is not None:
        if start >= metadata.duration:
            raise YouTubeImportError(
                f"In time begins after the video ends at {_format_seconds(metadata.duration)}"
            )
        if end > metadata.duration + 0.5:
            raise YouTubeImportError(
                f"Out time exceeds the video duration of {_format_seconds(metadata.duration)}"
            )

    output_dir.mkdir(parents=True, exist_ok=True)
    output_template = output_dir / "youtube-source.%(ext)s"
    section = f"*{start:.3f}-{end:.3f}"

    _run_ytdlp(
        [
            "--no-playlist",
            "--download-sections",
            section,
            "--force-keyframes-at-cuts",
            "--merge-output-format",
            "mp4",
            "--restrict-filenames",
            "-f",
            "bv*+ba/b",
            "-o",
            str(output_template),
            validated_url,
        ],
        timeout_seconds=timeout_seconds,
    )

    candidates = sorted(
        (
            path
            for path in output_dir.glob("youtube-source.*")
            if path.is_file()
            and path.suffix.lower() in _VIDEO_SUFFIXES
            and not path.name.endswith(".part")
        ),
        key=lambda path: path.stat().st_size,
        reverse=True,
    )
    if not candidates:
        raise YouTubeImportError("YouTube download completed but produced no readable video file")

    return ImportedYouTubeClip(
        path=candidates[0],
        metadata=metadata,
        start=start,
        end=end,
    )


def _require_ytdlp() -> None:
    if importlib.util.find_spec("yt_dlp") is None:
        raise YouTubeImportError(
            "yt-dlp is not installed in this project environment. Run `pip install -r requirements.txt`."
        )


def _run_ytdlp(
    arguments: list[str],
    *,
    timeout_seconds: int,
) -> subprocess.CompletedProcess[str]:
    command = [sys.executable, "-m", "yt_dlp", *arguments]
    try:
        return subprocess.run(
            command,
            check=True,
            capture_output=True,
            text=True,
            timeout=timeout_seconds,
        )
    except subprocess.TimeoutExpired as exc:
        raise YouTubeImportError("YouTube import timed out") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "yt-dlp failed").strip()
        useful_lines = [line for line in detail.splitlines() if line.strip()]
        concise = "\n".join(useful_lines[-8:])
        raise YouTubeImportError(f"YouTube import failed:\n{concise}") from exc


def _format_seconds(value: float) -> str:
    total = max(0, int(round(value)))
    hours, remainder = divmod(total, 3600)
    minutes, seconds = divmod(remainder, 60)
    if hours:
        return f"{hours}:{minutes:02d}:{seconds:02d}"
    return f"{minutes}:{seconds:02d}"
