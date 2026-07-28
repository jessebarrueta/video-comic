import shutil
import tempfile
from pathlib import Path

from fastapi import FastAPI, File, Form, HTTPException, Request, UploadFile
from fastapi.responses import FileResponse
from fastapi.staticfiles import StaticFiles

from app.config import get_settings
from app.devtools_workspace import ensure_devtools_workspace_file
from app.models import RegeneratePanelRequest
from app.pipeline import PipelineError, generate_comic, load_manifest, regenerate_panel
from app.vision import face_detection_status

BASE_DIR = Path(__file__).resolve().parent
PROJECT_ROOT = BASE_DIR.parent
STATIC_DIR = BASE_DIR / "static"
settings = get_settings()
DEVTOOLS_WORKSPACE_FILE = ensure_devtools_workspace_file(PROJECT_ROOT)

app = FastAPI(title="Video Comic MVP", version="0.2.0")
app.mount("/static", StaticFiles(directory=STATIC_DIR), name="static")
app.mount("/jobs", StaticFiles(directory=settings.work_dir), name="jobs")


@app.get("/")
def index() -> FileResponse:
    return FileResponse(STATIC_DIR / "index.html")


@app.get(
    "/.well-known/appspecific/com.chrome.devtools.json",
    include_in_schema=False,
)
def chrome_devtools_workspace(request: Request) -> FileResponse:
    # This descriptor reveals a local absolute path and is only useful when the
    # app itself is being debugged on the local machine.
    hostname = (request.url.hostname or "").lower()
    if hostname not in {"localhost", "127.0.0.1", "::1"}:
        raise HTTPException(status_code=404, detail="Not found")

    refreshed_path = ensure_devtools_workspace_file(PROJECT_ROOT)
    return FileResponse(refreshed_path, media_type="application/json")


@app.get("/api/health")
def health() -> dict[str, object]:
    return {
        "ok": True,
        "openrouter_enabled": bool(settings.openrouter_api_key),
        "stylization_enabled": not settings.skip_stylization,
        "openai_key_configured": bool(settings.openai_api_key),
        "max_video_seconds": settings.max_video_seconds,
        "max_panels_per_page": settings.max_panels_per_page,
        "max_total_panels": settings.max_total_panels,
        "face_detection": face_detection_status(),
    }


@app.post("/api/generate")
def generate(
    video: UploadFile = File(...),
    style_reference: UploadFile = File(...),
    style_strength: str = Form("balanced"),
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
            manifest = generate_comic(video_path, style_path, settings, style_strength=style_strength)
        except PipelineError as exc:
            raise HTTPException(status_code=400, detail=str(exc)) from exc
        except Exception as exc:
            raise HTTPException(status_code=500, detail=f"Generation failed: {exc}") from exc

    return manifest.model_dump()


@app.get("/api/jobs/{job_id}")
def get_job(job_id: str) -> dict[str, object]:
    try:
        manifest, _ = load_manifest(job_id, settings)
    except PipelineError as exc:
        raise HTTPException(status_code=404, detail=str(exc)) from exc
    return manifest.model_dump()


@app.post("/api/jobs/{job_id}/panels/{panel_index}/regenerate")
def regenerate_job_panel(job_id: str, panel_index: int, request: RegeneratePanelRequest) -> dict[str, object]:
    try:
        manifest = regenerate_panel(job_id, panel_index, request, settings)
    except PipelineError as exc:
        raise HTTPException(status_code=400, detail=str(exc)) from exc
    except Exception as exc:
        raise HTTPException(status_code=500, detail=f"Regeneration failed: {exc}") from exc
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
