import json

import httpx

from app.config import Settings
from app.models import Beat, PanelDecision, PanelPlan


_PANEL_SCHEMA = {
    "type": "object",
    "properties": {
        "panels": {
            "type": "array",
            "items": {
                "type": "object",
                "properties": {
                    "beat_index": {"type": "integer"},
                    "importance": {"type": "integer", "minimum": 1, "maximum": 5},
                    "kind": {
                        "type": "string",
                        "enum": ["setup", "beat", "reaction", "transition", "punchline"],
                    },
                    "bubble_text": {"type": "string"},
                },
                "required": ["beat_index", "importance", "kind", "bubble_text"],
                "additionalProperties": False,
            },
        }
    },
    "required": ["panels"],
    "additionalProperties": False,
}


def plan_panels(
    beats: list[Beat],
    max_panels: int,
    settings: Settings,
) -> list[PanelDecision]:
    beat_payload = [
        {
            "index": beat.index,
            "start": round(beat.start, 2),
            "end": round(beat.end, 2),
            "duration": round(beat.end - beat.start, 2),
            "text": beat.text,
        }
        for beat in beats
    ]

    prompt = f"""
You are editing a short spoken performance into a single comic page.
Choose at most {max_panels} beats. Preserve chronological order and always include
an intelligible opening/setup and the strongest ending/payoff. Prefer expressive,
self-contained moments over redundant wording.

For every selected beat:
- importance 1-5 controls panel area; use 5 sparingly for the payoff.
- kind is setup, beat, reaction, transition, or punchline.
- bubble_text should preserve the speaker's voice but may remove filler words.
- never invent a joke, fact, or line that was not said.

Beats:
{json.dumps(beat_payload, ensure_ascii=False)}
""".strip()

    payload = {
        "model": settings.openrouter_model,
        "messages": [
            {
                "role": "system",
                "content": "Return only a schema-valid comic panel plan.",
            },
            {"role": "user", "content": prompt},
        ],
        "response_format": {
            "type": "json_schema",
            "json_schema": {
                "name": "comic_panel_plan",
                "strict": True,
                "schema": _PANEL_SCHEMA,
            },
        },
        "provider": {"require_parameters": True},
    }

    headers = {
        "Authorization": f"Bearer {settings.openrouter_api_key}",
        "Content-Type": "application/json",
        "HTTP-Referer": settings.openrouter_app_url,
        "X-Title": settings.openrouter_app_name,
    }

    with httpx.Client(timeout=90.0) as client:
        response = client.post(
            "https://openrouter.ai/api/v1/chat/completions",
            headers=headers,
            json=payload,
        )
        response.raise_for_status()
        data = response.json()

    content = data["choices"][0]["message"]["content"]
    parsed = PanelPlan.model_validate_json(content)

    valid_indices = {beat.index for beat in beats}
    deduped: dict[int, PanelDecision] = {}
    for decision in parsed.panels:
        if decision.beat_index in valid_indices:
            deduped[decision.beat_index] = decision

    return sorted(deduped.values(), key=lambda item: item.beat_index)[:max_panels]
