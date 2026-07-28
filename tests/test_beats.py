from app.beats import apply_plan, build_beats, heuristic_plan
from app.models import WordTiming


def test_build_beats_splits_on_pause_and_punctuation() -> None:
    words = [
        WordTiming(text="I", start=0.0, end=0.2),
        WordTiming(text="have", start=0.2, end=0.4),
        WordTiming(text="a", start=0.4, end=0.5),
        WordTiming(text="question.", start=0.5, end=0.9),
        WordTiming(text="Why", start=1.8, end=2.0),
        WordTiming(text="humans?", start=2.0, end=2.5),
    ]

    beats = build_beats(words)

    assert len(beats) == 2
    assert beats[0].text == "I have a question."
    assert beats[1].text == "Why humans?"


def test_heuristic_plan_respects_limit_and_order() -> None:
    words = [
        WordTiming(text=f"Beat{i}.", start=float(i), end=float(i) + 0.3)
        for i in range(8)
    ]
    beats = build_beats(words, pause_threshold=0.1)
    decisions = heuristic_plan(beats, 4)
    selected = apply_plan(beats, decisions)

    assert len(selected) == 4
    assert selected[0].index == 0
    assert selected[-1].index == len(beats) - 1
    assert [beat.index for beat in selected] == sorted(beat.index for beat in selected)
