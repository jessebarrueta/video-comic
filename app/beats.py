import re

from app.models import Beat, PanelDecision, WordTiming

_SENTENCE_END = re.compile(r"[.!?…][\"')\]]?$")


def _join_words(words: list[WordTiming]) -> str:
    text = " ".join(word.text for word in words)
    # Repair punctuation spacing produced by token joining.
    text = re.sub(r"\s+([,.;:!?%])", r"\1", text)
    text = re.sub(r"([\[(])\s+", r"\1", text)
    text = re.sub(r"\s+([\])])", r"\1", text)
    return text.strip()


def build_beats(
    words: list[WordTiming],
    *,
    pause_threshold: float = 0.65,
    max_duration: float = 6.0,
    max_words: int = 26,
) -> list[Beat]:
    beats: list[Beat] = []
    current: list[WordTiming] = []

    def flush() -> None:
        if not current:
            return
        index = len(beats)
        start = current[0].start
        end = current[-1].end
        text = _join_words(current)
        beats.append(
            Beat(
                index=index,
                start=start,
                end=end,
                text=text,
                words=list(current),
                bubble_text=text,
                frame_time=max(start, end - min(0.18, (end - start) * 0.1)),
            )
        )
        current.clear()

    for word in words:
        if current:
            gap = word.start - current[-1].end
            duration = current[-1].end - current[0].start
            if gap >= pause_threshold or duration >= max_duration or len(current) >= max_words:
                flush()

        current.append(word)
        if _SENTENCE_END.search(word.text) and len(current) >= 4:
            flush()

    flush()
    return beats


def _heuristic_importance(beat: Beat, all_beats: list[Beat]) -> int:
    duration = beat.end - beat.start
    text = beat.text
    score = 2
    if "!" in text or "?" in text:
        score += 1
    if duration >= 3.5:
        score += 1
    if beat.index == len(all_beats) - 1:
        score += 1
    if len(text.split()) <= 6:
        score += 1
    return max(1, min(5, score))


def heuristic_plan(beats: list[Beat], max_panels: int) -> list[PanelDecision]:
    if not beats or max_panels <= 0:
        return []

    scored = [
        PanelDecision(
            beat_index=beat.index,
            importance=_heuristic_importance(beat, beats),
            kind=("punchline" if beat.index == len(beats) - 1 else "beat"),
            bubble_text=beat.text,
        )
        for beat in beats
    ]

    if len(scored) <= max_panels:
        return scored
    if max_panels == 1:
        return [max(scored, key=lambda item: (item.importance, item.beat_index))]

    # Preserve beginning and ending, then choose strongest interior beats.
    mandatory = {0, len(scored) - 1}
    ranked = sorted(
        (item for item in scored if item.beat_index not in mandatory),
        key=lambda item: (-item.importance, item.beat_index),
    )
    selected_ids = mandatory | {item.beat_index for item in ranked[: max_panels - 2]}
    return [item for item in scored if item.beat_index in selected_ids]


def apply_plan(beats: list[Beat], decisions: list[PanelDecision]) -> list[Beat]:
    by_index = {beat.index: beat.model_copy(deep=True) for beat in beats}
    selected: list[Beat] = []
    for decision in sorted(decisions, key=lambda item: item.beat_index):
        beat = by_index.get(decision.beat_index)
        if beat is None:
            continue
        beat.importance = decision.importance
        beat.kind = decision.kind
        beat.bubble_text = decision.bubble_text.strip() or beat.text
        selected.append(beat)
    return selected
