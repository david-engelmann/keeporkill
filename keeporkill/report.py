"""Deterministic rendering helpers."""

from __future__ import annotations

import json


def render_json(document):
    """Render JSON with sorted keys and two space indentation and one trailing newline."""

    return json.dumps(document, ensure_ascii=False, indent=2, sort_keys=True) + "\n"
