"""Unit tests for the per-document classifier orchestrator.

These stub out Ollama so they run without a live server.
"""

import json
from pathlib import Path
from unittest.mock import patch

from veasy_peasy import orchestrator
from fixtures.engines import ScriptedEngine
from fixtures.llms import ScriptedLLM


REQUIREMENTS = {
    "visa_type": "Test",
    "documents": [
        {"name": "passport", "description": "valid passport"},
        {"name": "bank_statement", "description": "3 months of bank statements"},
        {"name": "cover_letter", "description": "letter of intent"},
    ],
}


def _chat_response(assistant_message: dict, wall_time_s: float = 0.0) -> dict:
    """Wrap an assistant message dict into the ChatResponse shape ScriptedLLM expects."""
    return {"message": assistant_message, "wall_time_s": wall_time_s}


def test_mrz_fast_path_skips_llm(tmp_path: Path):
    """Valid passport MRZ should short-circuit before any LLM call."""
    fake_path = tmp_path / "passport.jpg"
    fake_path.write_bytes(b"")

    with patch.object(orchestrator, "try_passport", return_value={"mrz_type": "P", "name": "JOHN"}):
        # ScriptedLLM with no responses raises if chat() is called.
        llm = ScriptedLLM(chat_responses=[])
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm)

    assert result["classification"] == "passport"
    assert result["trace"]["decision_path"] == "deterministic_mrz"
    assert result["extracted_fields"]["mrz_type"] == "P"


def test_llm_final_without_tools(tmp_path: Path):
    """If the LLM replies with a valid JSON classification and no tool calls, use it."""
    fake_path = tmp_path / "doc.pdf"
    fake_path.write_bytes(b"")

    with patch.object(orchestrator, "try_passport", return_value=None):
        llm = ScriptedLLM(chat_responses=[
            _chat_response({"role": "assistant", "content": json.dumps({"classification": "bank_statement", "reason": "Looks like a statement."})}),
        ])
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm)

    assert result["classification"] == "bank_statement"
    assert result["trace"]["decision_path"] == "llm_orchestrator"
    assert any(s["kind"] == "llm_final" for s in result["trace"]["steps"])


def test_llm_tool_call_then_final(tmp_path: Path):
    """LLM requests a tool, receives result, then emits final JSON."""
    fake_path = tmp_path / "doc.pdf"
    fake_path.write_bytes(b"")

    tool_call = {
        "function": {
            "name": "keyword_score",
            "arguments": {"text": "some text"},
        }
    }
    with patch.object(orchestrator, "try_passport", return_value=None):
        llm = ScriptedLLM(chat_responses=[
            _chat_response({"role": "assistant", "content": "Checking keywords.", "tool_calls": [tool_call]}),
            _chat_response({"role": "assistant", "content": json.dumps({"classification": "cover_letter", "reason": "Intent to travel."})}),
        ])
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm)

    assert result["classification"] == "cover_letter"
    steps = result["trace"]["steps"]
    assert any(s["kind"] == "tool_result" and s["tool"] == "keyword_score" for s in steps)


def test_invalid_category_falls_back_to_unknown(tmp_path: Path):
    """LLM returning a category outside the allowed set is rejected."""
    fake_path = tmp_path / "doc.pdf"
    fake_path.write_bytes(b"")

    with patch.object(orchestrator, "try_passport", return_value=None):
        llm = ScriptedLLM(chat_responses=[
            _chat_response({"role": "assistant", "content": json.dumps({"classification": "not_a_category", "reason": "made up"})}),
        ])
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm)

    assert result["classification"] == "unknown"


def test_non_json_final_falls_back_to_unknown(tmp_path: Path):
    """Final message that isn't JSON → unknown, not a crash."""
    fake_path = tmp_path / "doc.pdf"
    fake_path.write_bytes(b"")

    with patch.object(orchestrator, "try_passport", return_value=None):
        llm = ScriptedLLM(chat_responses=[
            _chat_response({"role": "assistant", "content": "I think this is a bank statement."}),
        ])
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm)

    assert result["classification"] == "unknown"


def test_max_rounds_cap(tmp_path: Path):
    """After DEFAULT_MAX_ROUNDS of tool calls with no final, classify as unknown."""
    fake_path = tmp_path / "doc.pdf"
    fake_path.write_bytes(b"")

    tool_call = {
        "function": {
            "name": "keyword_score",
            "arguments": {"text": "x"},
        }
    }
    # Always tool-call, never finalise.
    responses = [
        _chat_response({"role": "assistant", "content": "still looking", "tool_calls": [tool_call]})
        for _ in range(orchestrator.DEFAULT_MAX_ROUNDS + 2)
    ]

    with patch.object(orchestrator, "try_passport", return_value=None):
        llm = ScriptedLLM(chat_responses=responses)
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm)

    assert result["classification"] == "unknown"
    assert any(
        s.get("kind") == "decision" and s.get("rule") == "max_rounds_exceeded"
        for s in result["trace"]["steps"]
    )


def test_fenced_json_final(tmp_path: Path):
    """Final JSON wrapped in ```json fences still parses."""
    fake_path = tmp_path / "doc.pdf"
    fake_path.write_bytes(b"")

    with patch.object(orchestrator, "try_passport", return_value=None):
        llm = ScriptedLLM(chat_responses=[
            _chat_response({"role": "assistant", "content": '```json\n{"classification": "passport", "reason": "MRZ present"}\n```'}),
        ])
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm)

    assert result["classification"] == "passport"


def test_tool_arg_as_json_string(tmp_path: Path):
    """Some models send tool arguments as a JSON string rather than a dict."""
    fake_path = tmp_path / "doc.pdf"
    fake_path.write_bytes(b"")

    tool_call = {
        "function": {
            "name": "keyword_score",
            "arguments": json.dumps({"text": "passport"}),
        }
    }
    with patch.object(orchestrator, "try_passport", return_value=None):
        llm = ScriptedLLM(chat_responses=[
            _chat_response({"role": "assistant", "content": "", "tool_calls": [tool_call]}),
            _chat_response({"role": "assistant", "content": json.dumps({"classification": "passport", "reason": "x"})}),
        ])
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm)

    assert result["classification"] == "passport"
    tool_result_steps = [s for s in result["trace"]["steps"] if s.get("kind") == "tool_result"]
    assert tool_result_steps and tool_result_steps[0]["args"] == {"text": "passport"}


def test_orchestrator_uses_scripted_engine_when_provided(tmp_path: Path):
    """ScriptedEngine's final state is used directly; LLM is never called."""
    fake_path = tmp_path / "doc.pdf"
    fake_path.write_bytes(b"")

    engine = ScriptedEngine({
        "messages": [{"role": "assistant", "content": '{"classification": "bank_statement", "reason": "x"}'}],
        "stop_reason": "final",
    })

    with patch.object(orchestrator, "try_passport", return_value=None):
        # ScriptedLLM with no responses raises if chat() is called.
        llm = ScriptedLLM(chat_responses=[])
        result = orchestrator.classify_document(fake_path, REQUIREMENTS, llm=llm, engine=engine)

    assert result["classification"] == "bank_statement"
