from app.image_styler import build_stylization_prompt


def test_build_stylization_prompt_emphasizes_reference_style() -> None:
    prompt = build_stylization_prompt(
        panel_kind="punchline",
        style_strength="balanced",
    )
    assert "Image B" in prompt
    assert "Do not fall back to a generic comic-book" in prompt
    assert "style of Image B" in prompt


def test_build_stylization_prompt_strong_allows_more_stylization() -> None:
    prompt = build_stylization_prompt(
        panel_kind="setup",
        style_strength="strong",
        prompt_suffix="Use rougher linework.",
    )
    assert "Prioritize the visual language of Image B decisively" in prompt
    assert "Use rougher linework." in prompt
