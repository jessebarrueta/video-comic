import subprocess
from pathlib import Path

import pytest

import app.youtube_import as youtube_import
from app.youtube_import import (
    YouTubeImportError,
    YouTubeMetadata,
    download_youtube_section,
    parse_timestamp,
    validate_youtube_url,
)


def test_parse_timestamp_accepts_common_formats() -> None:
    assert parse_timestamp("90") == 90
    assert parse_timestamp("1:30") == 90
    assert parse_timestamp("01:30.5") == 90.5
    assert parse_timestamp("1:02:03") == 3723


def test_parse_timestamp_rejects_invalid_values() -> None:
    with pytest.raises(YouTubeImportError):
        parse_timestamp("1:72")
    with pytest.raises(YouTubeImportError):
        parse_timestamp("banana")


def test_validate_youtube_url_rejects_non_youtube_hosts() -> None:
    assert validate_youtube_url("https://youtu.be/abc") == "https://youtu.be/abc"
    assert validate_youtube_url("https://www.youtube.com/watch?v=abc")
    with pytest.raises(YouTubeImportError):
        validate_youtube_url("https://example.com/watch?v=abc")


def test_download_youtube_section_builds_clip(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(youtube_import, "_require_ytdlp", lambda: None)
    monkeypatch.setattr(
        youtube_import,
        "inspect_youtube",
        lambda *args, **kwargs: YouTubeMetadata(
            title="A test performance",
            duration=300.0,
            webpage_url="https://www.youtube.com/watch?v=abc",
        ),
    )

    def fake_run(arguments: list[str], *, timeout_seconds: int):
        assert "--download-sections" in arguments
        assert "*12.000-42.000" in arguments
        template = Path(arguments[arguments.index("-o") + 1])
        output = Path(str(template).replace("%(ext)s", "mp4"))
        output.parent.mkdir(parents=True, exist_ok=True)
        output.write_bytes(b"fake-video")
        return subprocess.CompletedProcess(arguments, 0, stdout="", stderr="")

    monkeypatch.setattr(youtube_import, "_run_ytdlp", fake_run)

    imported = download_youtube_section(
        "https://www.youtube.com/watch?v=abc",
        start=12,
        end=42,
        output_dir=tmp_path,
        max_clip_seconds=60,
    )

    assert imported.path.exists()
    assert imported.metadata.title == "A test performance"
    assert imported.start == 12
    assert imported.end == 42


def test_download_youtube_section_enforces_clip_limit(monkeypatch, tmp_path: Path) -> None:
    monkeypatch.setattr(youtube_import, "_require_ytdlp", lambda: None)
    with pytest.raises(YouTubeImportError, match="limit"):
        download_youtube_section(
            "https://youtu.be/abc",
            start=0,
            end=61,
            output_dir=tmp_path,
            max_clip_seconds=60,
        )
