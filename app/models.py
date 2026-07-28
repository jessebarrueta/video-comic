from pydantic import BaseModel, Field


class WordTiming(BaseModel):
    text: str
    start: float
    end: float


class Beat(BaseModel):
    index: int
    start: float
    end: float
    text: str
    words: list[WordTiming] = Field(default_factory=list)
    importance: int = 3
    kind: str = "beat"
    bubble_text: str = ""
    frame_time: float = 0.0


class PanelDecision(BaseModel):
    beat_index: int
    importance: int = Field(ge=1, le=5)
    kind: str
    bubble_text: str


class PanelPlan(BaseModel):
    panels: list[PanelDecision]


class GeneratedPanel(BaseModel):
    index: int
    source_frame: str
    styled_frame: str
    beat: Beat


class JobManifest(BaseModel):
    job_id: str
    transcript: str
    beats: list[Beat]
    comic_path: str
    used_openrouter: bool
    used_stylization: bool
