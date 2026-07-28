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


class FaceBox(BaseModel):
    x: int
    y: int
    w: int
    h: int


class GeneratedPanel(BaseModel):
    index: int
    page_index: int
    source_frame: str
    styled_frame: str
    beat: Beat
    face_boxes: list[FaceBox] = Field(default_factory=list)


class JobManifest(BaseModel):
    job_id: str
    transcript: str
    beats: list[Beat]
    comic_path: str
    comic_paths: list[str] = Field(default_factory=list)
    page_count: int = 1
    panels: list[GeneratedPanel] = Field(default_factory=list)
    style_strength: str = "balanced"
    used_openrouter: bool
    used_stylization: bool


class RegeneratePanelRequest(BaseModel):
    bubble_text: str | None = None
    prompt_suffix: str | None = None
    style_strength: str | None = None
