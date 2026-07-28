from functools import lru_cache
from pathlib import Path

from faster_whisper import WhisperModel

from app.config import get_settings
from app.models import WordTiming


@lru_cache(maxsize=1)
def _get_model() -> WhisperModel:
    settings = get_settings()
    return WhisperModel(
        settings.whisper_model,
        device=settings.whisper_device,
        compute_type=settings.whisper_compute_type,
    )


def transcribe_words(audio_path: Path) -> tuple[list[WordTiming], str]:
    model = _get_model()
    segments, _ = model.transcribe(
        str(audio_path),
        word_timestamps=True,
        vad_filter=True,
        vad_parameters={"min_silence_duration_ms": 400},
        condition_on_previous_text=False,
    )

    words: list[WordTiming] = []
    transcript_parts: list[str] = []
    for segment in segments:
        text = segment.text.strip()
        if text:
            transcript_parts.append(text)
        for word in segment.words or []:
            token = word.word.strip()
            if token and word.start is not None and word.end is not None:
                words.append(
                    WordTiming(text=token, start=float(word.start), end=float(word.end))
                )

    if not words:
        raise RuntimeError("No speech was detected in the clip")

    return words, " ".join(transcript_parts).strip()
