"""Tests for veasy_peasy.matcher."""

import json

from fixtures.llms import ScriptedLLM
from veasy_peasy.matcher import build_prompt, match

# Minimal inline fixtures used across tests
REQUIREMENTS = {
    "documents": [
        {"name": "passport", "description": "Valid travel passport"},
        {"name": "bank_statement", "description": "Last 3 months bank statement"},
    ]
}

FILES = [
    {"path": "/docs/passport.pdf", "classification": "passport", "text_excerpt": "SURNAME SMITH"},
    {"path": "/docs/bank.pdf", "classification": "bank_statement", "text_excerpt": "Account balance"},
]

VALID_RESPONSE = {
    "matched": [
        {"requirement": "passport", "file": "/docs/passport.pdf", "reason": "Valid passport."},
        {"requirement": "bank_statement", "file": "/docs/bank.pdf", "reason": "Recent statement."},
    ],
    "missing": [],
    "conflicts_resolved": [],
    "validation_warnings": [],
}


def _scripted(response_str: str, wall_time_s: float = 0.5, model_name: str = "scripted") -> ScriptedLLM:
    return ScriptedLLM(
        generate_responses=[{"response": response_str, "wall_time_s": wall_time_s}],
        model_name=model_name,
    )


# 1. Happy path
def test_happy_path():
    llm = _scripted(json.dumps(VALID_RESPONSE))
    result = match(REQUIREMENTS, FILES, llm)
    assert result["parse_ok"] is True
    assert result["model"] == "scripted"
    assert len(result["result"]["matched"]) == 2


# 2. JSON wrapped in code fences
def test_json_wrapped_in_code_fences():
    fenced = f"```json\n{json.dumps(VALID_RESPONSE)}\n```"
    llm = _scripted(fenced)
    result = match(REQUIREMENTS, FILES, llm)
    assert result["parse_ok"] is True
    assert result["result"]["matched"] is not None


# 3. Missing required key
def test_missing_required_key():
    bad = {"missing": [], "conflicts_resolved": []}  # no "matched"
    llm = _scripted(json.dumps(bad))
    result = match(REQUIREMENTS, FILES, llm)
    assert result["parse_ok"] is False
    assert result["result"] is None


# 4. Invalid JSON
def test_invalid_json():
    llm = _scripted("this is not json at all")
    result = match(REQUIREMENTS, FILES, llm)
    assert result["parse_ok"] is False
    assert result["result"] is None
    assert result["raw_response"] == "this is not json at all"


# 5. validation_warnings defaulted to [] when LLM omits it
def test_validation_warnings_defaulted():
    no_warnings = {
        "matched": [],
        "missing": ["passport"],
        "conflicts_resolved": [],
        # validation_warnings intentionally absent
    }
    llm = _scripted(json.dumps(no_warnings))
    result = match(REQUIREMENTS, FILES, llm)
    assert result["parse_ok"] is True
    assert result["result"]["validation_warnings"] == []


# 6. matched[].reason defaulted to "" when entry omits it
def test_matched_reason_defaulted():
    no_reason = {
        "matched": [
            {"requirement": "passport", "file": "/docs/passport.pdf"},  # no reason
        ],
        "missing": [],
        "conflicts_resolved": [],
    }
    llm = _scripted(json.dumps(no_reason))
    result = match(REQUIREMENTS, FILES, llm)
    assert result["parse_ok"] is True
    for entry in result["result"]["matched"]:
        assert "reason" in entry
        assert entry["reason"] == ""


# 7. model field comes from llm.model_name
def test_model_name_from_llm():
    llm = _scripted(json.dumps(VALID_RESPONSE), model_name="custom-model")
    result = match(REQUIREMENTS, FILES, llm)
    assert result["model"] == "custom-model"


# 8. Pass-through fields eval_count and prompt_eval_count
def test_passthrough_eval_counts():
    llm = ScriptedLLM(
        generate_responses=[{
            "response": json.dumps(VALID_RESPONSE),
            "wall_time_s": 0.5,
            "eval_count": 42,
            "prompt_eval_count": 7,
        }],
    )
    result = match(REQUIREMENTS, FILES, llm)
    assert result["eval_count"] == 42
    assert result["prompt_eval_count"] == 7


# 9. wall_time_s from generate response
def test_wall_time_s_passthrough():
    llm = _scripted(json.dumps(VALID_RESPONSE), wall_time_s=1.5)
    result = match(REQUIREMENTS, FILES, llm)
    assert result["wall_time_s"] == 1.5


# 10. build_prompt contains requirements and file results
def test_build_prompt_contains_key_tokens():
    prompt = build_prompt(REQUIREMENTS, FILES)
    assert isinstance(prompt, str)
    assert "passport" in prompt
    assert "bank_statement" in prompt
    assert "/docs/passport.pdf" in prompt
    assert "/docs/bank.pdf" in prompt
