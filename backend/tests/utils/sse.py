"""Server-Sent Events parser for backend integration tests."""

import json

from app.models import StreamEvent


def parse_sse_events(text: str | list[str]) -> list[StreamEvent]:
    """Parse raw SSE response text into a list of validated StreamEvent instances.

    Accepts either a raw SSE response body as a string or an already-split
    list of lines.  Blank lines and keep-alive comment lines (starting with
    ``:``) are skipped.  Only ``data: {...}`` lines are parsed.

    Args:
        text: Raw SSE response body string, or a list of lines.

    Returns:
        List of ``StreamEvent`` instances, empty when no data lines are found.

    Raises:
        json.JSONDecodeError: If a ``data:`` line contains malformed JSON.
        pydantic.ValidationError: If a parsed JSON object fails StreamEvent validation.
    """
    lines = text.strip().split("\n") if isinstance(text, str) else text

    events: list[StreamEvent] = []
    for line in lines:
        if not line.startswith("data: "):
            continue
        payload = line[len("data: ") :]
        events.append(StreamEvent.model_validate(json.loads(payload)))
    return events
