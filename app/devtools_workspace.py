from __future__ import annotations

import json
import uuid
from pathlib import Path

DEVTOOLS_RELATIVE_PATH = Path(".well-known/appspecific/com.chrome.devtools.json")


def ensure_devtools_workspace_file(project_root: Path) -> Path:
    """Create or refresh Chrome DevTools' automatic workspace descriptor.

    The project root must be absolute for Chrome, so the file is rewritten when
    the server starts after the project has been moved or extracted elsewhere.
    A previously generated UUID is retained so Chrome recognizes the workspace.
    """

    project_root = project_root.resolve()
    output_path = project_root / DEVTOOLS_RELATIVE_PATH
    output_path.parent.mkdir(parents=True, exist_ok=True)

    workspace_uuid = _existing_uuid(output_path) or str(uuid.uuid4())
    payload = {
        "workspace": {
            "root": str(project_root),
            "uuid": workspace_uuid,
        }
    }
    serialized = json.dumps(payload, indent=2) + "\n"

    if not output_path.exists() or output_path.read_text(encoding="utf-8") != serialized:
        output_path.write_text(serialized, encoding="utf-8")

    return output_path


def _existing_uuid(path: Path) -> str | None:
    if not path.exists():
        return None

    try:
        payload = json.loads(path.read_text(encoding="utf-8"))
        value = payload["workspace"]["uuid"]
        parsed = uuid.UUID(str(value), version=4)
    except (OSError, ValueError, TypeError, KeyError, json.JSONDecodeError):
        return None

    return str(parsed)
