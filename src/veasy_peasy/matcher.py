"""LLM-based document matcher: takes requirements + extracted files → matching report."""

import json
import logging

from veasy_peasy.llm import LLM
from veasy_peasy.llm_json import parse_llm_json

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
    {{"requirement": "<requirement name>", "file": "<file path>", "reason": "<one sentence explaining why this file satisfies the requirement>"}}
  ],
  "missing": ["<requirement name that has no matching document>"],
  "conflicts_resolved": ["<one sentence: which requirement had a conflict, which file was chosen, and why>"],
  "validation_warnings": ["<one sentence: which file looks misclassified and why; empty list if all look correct>"]
}}

Rules:
- Every entry in `matched` MUST include a non-empty `reason` string (one concise sentence).
- `conflicts_resolved` and `validation_warnings` MUST be arrays of plain strings, NOT objects.

Example of a well-formed matched entry:
{{"requirement": "bank_statement", "file": "/tmp/amex_aug.pdf", "reason": "Amex statement covering Aug 2025 with account number and closing balance."}}

Example of a well-formed conflict entry:
"bank_statement: two statements found; chose /tmp/amex_aug.pdf because it is the most recent (Aug 2025)."

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


def _parse_match_response(raw: str) -> dict | None:
    """Parse the matcher LLM response. Returns None if JSON parsing fails or
    required keys are missing. Defaults validation_warnings + matched[].reason
    on success."""
    data = parse_llm_json(raw, required_keys=("matched", "missing", "conflicts_resolved"))
    if data is None:
        return None

    # Default validation_warnings to [] (LLM may omit it)
    data.setdefault("validation_warnings", [])

    # Ensure every matched entry has a reason key (renderer falls back gracefully)
    if isinstance(data.get("matched"), list):
        for entry in data["matched"]:
            if isinstance(entry, dict) and "reason" not in entry:
                entry["reason"] = ""

    return data


def match(requirements_data: dict, file_results: list[dict], llm: LLM) -> dict:
    """Run the LLM-based matcher: build prompt, call llm.generate, parse JSON.
    Returns the same dict shape as today (model, result, raw_response, parse_ok, wall_time_s, eval_count, prompt_eval_count).
    """
    prompt = build_prompt(requirements_data, file_results)
    gen = llm.generate(prompt, temperature=0.0)
    raw = gen.get("response", "")
    parsed = _parse_match_response(raw)

    return {
        "model": llm.model_name,
        "result": parsed,
        "raw_response": raw,
        "parse_ok": parsed is not None,
        "wall_time_s": gen.get("wall_time_s", 0),
        "eval_count": gen.get("eval_count", 0),
        "prompt_eval_count": gen.get("prompt_eval_count", 0),
    }
