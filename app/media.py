import json
import shutil
import subprocess
from pathlib import Path


class MediaError(RuntimeError):
    pass


def _run(args: list[str]) -> subprocess.CompletedProcess[str]:
    try:
        return subprocess.run(
            args,
            check=True,
            capture_output=True,
            text=True,
        )
    except FileNotFoundError as exc:
        raise MediaError(f"Required executable not found: {args[0]}") from exc
    except subprocess.CalledProcessError as exc:
        detail = (exc.stderr or exc.stdout or "unknown ffmpeg error").strip()
        raise MediaError(detail) from exc


def assert_ffmpeg_available() -> None:
    for binary in ("ffmpeg", "ffprobe"):
        if shutil.which(binary) is None:
            raise MediaError(
                f"{binary} is not installed. On macOS: brew install ffmpeg"
            )


def probe_duration(video_path: Path) -> float:
    result = _run(
        [
            "ffprobe",
            "-v",
            "error",
            "-show_entries",
            "format=duration",
            "-of",
            "json",
            str(video_path),
        ]
    )
    data = json.loads(result.stdout)
    try:
        return float(data["format"]["duration"])
    except (KeyError, TypeError, ValueError) as exc:
        raise MediaError("Could not determine video duration") from exc


def extract_audio(video_path: Path, audio_path: Path) -> None:
    _run(
        [
            "ffmpeg",
            "-y",
            "-i",
            str(video_path),
            "-vn",
            "-ac",
            "1",
            "-ar",
            "16000",
            "-c:a",
            "pcm_s16le",
            str(audio_path),
        ]
    )


def extract_frame(video_path: Path, timestamp: float, output_path: Path) -> None:
    # Seek before decoding for speed, then emit a single high-quality JPEG.
    _run(
        [
            "ffmpeg",
            "-y",
            "-ss",
            f"{max(0.0, timestamp):.3f}",
            "-i",
            str(video_path),
            "-frames:v",
            "1",
            "-q:v",
            "2",
            str(output_path),
        ]
    )
