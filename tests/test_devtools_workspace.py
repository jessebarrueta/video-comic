import json
import uuid
from pathlib import Path

from app.devtools_workspace import ensure_devtools_workspace_file


def test_devtools_workspace_file_uses_absolute_root_and_stable_uuid(tmp_path: Path) -> None:
    first_path = ensure_devtools_workspace_file(tmp_path)
    first = json.loads(first_path.read_text(encoding="utf-8"))

    second_path = ensure_devtools_workspace_file(tmp_path)
    second = json.loads(second_path.read_text(encoding="utf-8"))

    assert first_path == tmp_path / ".well-known/appspecific/com.chrome.devtools.json"
    assert first["workspace"]["root"] == str(tmp_path.resolve())
    assert first["workspace"]["uuid"] == second["workspace"]["uuid"]
    assert uuid.UUID(first["workspace"]["uuid"]).version == 4
