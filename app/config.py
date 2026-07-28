from functools import lru_cache
from pathlib import Path

from pydantic_settings import BaseSettings, SettingsConfigDict


class Settings(BaseSettings):
    model_config = SettingsConfigDict(env_file=".env", extra="ignore")

    openai_api_key: str = ""
    openai_image_model: str = "gpt-image-1.5"
    openai_image_quality: str = "medium"

    openrouter_api_key: str = ""
    openrouter_model: str = "openai/gpt-5-mini"
    openrouter_app_url: str = "http://localhost:8000"
    openrouter_app_name: str = "Video Comic MVP"

    whisper_model: str = "small"
    whisper_device: str = "cpu"
    whisper_compute_type: str = "int8"

    max_video_seconds: int = 300
    max_panels_per_page: int = 6
    max_total_panels: int = 18
    skip_stylization: bool = False
    work_dir: Path = Path("./var/jobs")

    def ensure_directories(self) -> None:
        self.work_dir.mkdir(parents=True, exist_ok=True)


@lru_cache
def get_settings() -> Settings:
    settings = Settings()
    settings.ensure_directories()
    return settings
