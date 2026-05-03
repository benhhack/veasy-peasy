import json


def parse_llm_json(text: str, required_keys: tuple[str, ...] = ()) -> dict | None:
    """Extract a JSON object from an LLM's free-text response.

    Strips ``` code fences, locates the outermost {...} block, json.loads it,
    and optionally verifies that all `required_keys` are present.

    Returns the parsed dict, or None if parsing fails or any required key is missing.
    """
    if not text:
        return None

    text = text.strip()

    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    start = text.find("{")
    end = text.rfind("}")
    if start == -1 or end == -1 or end <= start:
        return None

    candidate = text[start:end + 1]

    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return None

    if not isinstance(data, dict):
        return None

    if any(k not in data for k in required_keys):
        return None

    return data
