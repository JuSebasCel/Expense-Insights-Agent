"""Formato SSE para transmitir el progreso del grafo en vivo."""

import json
from collections.abc import Iterator
from typing import Any


def format_sse(events: Iterator[dict[str, Any]]) -> Iterator[str]:
    for event in events:
        yield f"data: {json.dumps(event, ensure_ascii=False)}\n\n"
