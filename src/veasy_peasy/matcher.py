"""LLM-based document matcher: takes requirements + extracted files → matching report."""

import json
import logging

from veasy_peasy.ollama_client import generate

logger = logging.getLogger(__name__)

MATCH_PROMPT_TEMPLATE = """\
You are a document-verification assistant for visa applications.

Our scanning pipeline has already classified each document and extracted structured data.
Your job is to:

1. VALIDATE: Check that each document's classification is plausible given its text excerpt. \
If a classification looks wrong, flag it in your output.
2. MATCH: Map each validated document to the requirement it satisfies.
3. CONFLICTS: If multiple documents satisfy the same requirement, pick the best one \
(prefer non-expired, most recent) and explain why.
4. MISSING: List any requirements that have no matching document.

## Visa requirements
{requirements_json}

## Scanned documents (already classified by our pipeline)
{files_json}

## Output format
Respond with ONLY a JSON object, no markdown fences, no explanation. Use this exact schema:
{{
  "matched": [
    {{"requirement": "<requirement name>", "file": "<file path>", "reason": "<why this file satisfies the requirement>"}}
  ],
  "missing": ["<requirement name that has no matching document>"],
  "conflicts_resolved": ["<description of conflict and which document was chosen and why>"],
  "validation_warnings": ["<any classification that looks wrong, or empty list if all look correct>"]
}}

JSON output:"""


def build_prompt(requirements_data: dict, file_results: list[dict]) -> str:
    """Build the matching prompt from requirements and extracted file results."""
    slim_files = []
    for f in file_results:
        entry = {
            "path": f["path"],
            "classification": f["classification"],
        }
        # Include extracted fields if present (e.g. passport MRZ data)
        if f.get("extracted_fields"):
            entry["extracted_fields"] = f["extracted_fields"]
        # Include a short text excerpt for validation context
        excerpt = f.get("text_excerpt", "")
        if excerpt:
            entry["text_excerpt"] = excerpt[:200]
        slim_files.append(entry)

    return MATCH_PROMPT_TEMPLATE.format(
        requirements_json=json.dumps(requirements_data["documents"], indent=2),
        files_json=json.dumps(slim_files, indent=2),
    )


def parse_response(raw: str) -> dict | None:
    """Try to parse the LLM response as the expected JSON schema.

    Returns the parsed dict, or None if parsing fails.
    """
    text = raw.strip()
    # Strip markdown fences if the model added them
    if text.startswith("```"):
        lines = text.split("\n")
        lines = [l for l in lines if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    try:
        data = json.loads(text)
    except json.JSONDecodeError:
        return None

    # Validate expected keys exist
    if not isinstance(data, dict):
        return None
    for key in ("matched", "missing", "conflicts_resolved"):
        if key not in data:
            return None
    # validation_warnings is optional — default to empty list
    if "validation_warnings" not in data:
        data["validation_warnings"] = []

    return data


def match(model: str, requirements_data: dict, file_results: list[dict]) -> dict:
    """Run the full match pipeline: build prompt, call LLM, parse response.

    Returns a dict with keys:
        result: parsed matching dict or None
        raw_response: the raw LLM text
        parse_ok: whether JSON parsing succeeded
        wall_time_s: generation wall time
        eval_count: tokens generated (if available)
    """
    prompt = build_prompt(requirements_data, file_results)
    gen = generate(model, prompt, temperature=0.0)
    raw = gen.get("response", "")
    parsed = parse_response(raw)

    return {
        "model": model,
        "result": parsed,
        "raw_response": raw,
        "parse_ok": parsed is not None,
        "wall_time_s": gen.get("wall_time_s", 0),
        "eval_count": gen.get("eval_count", 0),
        "prompt_eval_count": gen.get("prompt_eval_count", 0),
    }
