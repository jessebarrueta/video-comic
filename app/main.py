import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, HTTPException, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.pipeline import PipelineError, generate_comic

BASE_DIR = Path(__file__).resolve().parent
STATIC_DIR = BASE_DIR / "static"
settings = get_settings()

app = FastAPI(title="Video Comic MVP", version="0.1.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/jobs", StaticFiles(directory=settings.work_dir), name="jobs")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "openrouter_enabled": bool(settings.openrouter_api_key),
        "stylization_enabled": not settings.skip_stylization,
        "openai_key_configured": bool(settings.openai_api_key),
    }


@app.post("/api/generate")
def generate(
    video: UploadFile = File(...),
    style_reference: UploadFile = File(...),
) -> dict[str, object]:
    video_suffix = _safe_suffix(video.filename, {".mp4", ".mov", ".m4v", ".webm"})
    style_suffix = _safe_suffix(
        style_reference.filename, {".png", ".jpg", ".jpeg", ".webp"}
    )

    with tempfile.TemporaryDirectory(prefix="video-comic-upload-") as temp_dir:
        temp_path = Path(temp_dir)
        video_path = temp_path / f"video{video_suffix}"
        style_path = temp_path / f"style{style_suffix}"
        _copy_upload(video, video_path)
        _copy_upload(style_reference, style_path)

        try:
            manifest = generate_comic(video_path, style_path, settings)
        except PipelineError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Generation failed: {exc}") from exc

    return manifest.model_dump()


def _copy_upload(upload: UploadFile, destination: Path) -> None:
    with destination.open("wb") as output:
        shutil.copyfileobj(upload.file, output)


def _safe_suffix(filename: str | None, allowed: set[str]) -> str:
    suffix = Path(filename or "").suffix.lower()
    if suffix not in allowed:
        raise HTTPException(
            status_code=400,
            detail=f"Unsupported file type. Allowed: {', '.join(sorted(allowed))}",
        )
    return suffix
