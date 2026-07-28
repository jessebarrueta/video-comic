from app.config import Settings
from app.pipeline import _desired_panel_count


def test_desired_panel_count_scales_with_duration() -> None:
    settings = Settings(max_total_panels=18)
    assert _desired_panel_count(20, 20, settings) >= 2
    assert _desired_panel_count(120, 20, settings) >= 8
    assert _desired_panel_count(300, 40, settings) <= 18
