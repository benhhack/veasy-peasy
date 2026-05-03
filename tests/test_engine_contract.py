"""Behavioral contract tests for ManualEngine.

Each test scripts one scenario through ScriptedLLM and asserts on the
observable EngineState after run(). Any future Engine Adapter must pass
these tests unchanged.
"""

import json

from fixtures.engines import ScriptedEngine
from fixtures.llms import ScriptedLLM
from veasy_peasy.engine import Engine, EngineState, ManualEngine
from veasy_peasy.tools import TOOL_REGISTRY


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _final_resp(content="done"):
    return {
        "message": {"role": "assistant", "content": content, "tool_calls": []},
        "wall_time_s": 0.0,
    }


def _tool_resp(name, arguments):
    return {
        "message": {
            "role": "assistant",
            "content": "",
            "tool_calls": [{"function": {"name": name, "arguments": arguments}}],
        },
        "wall_time_s": 0.0,
    }


def _engine() -> ManualEngine:
    return ManualEngine()


def _empty_state() -> EngineState:
    return {}


# ---------------------------------------------------------------------------
# Test 1: Final response on first round
# ---------------------------------------------------------------------------

def test_final_on_first_round():
    llm = ScriptedLLM(chat_responses=[_final_resp("I am done")])
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=5)

    assert result["stop_reason"] == "final"
    assert len(result["llm_timings"]) == 1
    assert result.get("tool_timings", []) == []
    # Final assistant message appended
    assert result["messages"][-1] == {"role": "assistant", "content": "I am done"}


# ---------------------------------------------------------------------------
# Test 2: One tool call then final
# ---------------------------------------------------------------------------

def test_one_tool_call_then_final():
    llm = ScriptedLLM(chat_responses=[
        _tool_resp("keyword_score", {"text": "test"}),
        _final_resp("done"),
    ])
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=5)

    assert result["stop_reason"] == "final"
    assert len(result["llm_timings"]) == 2
    assert len(result["tool_timings"]) == 1
    assert result["tool_timings"][0]["name"] == "keyword_score"
    # messages: assistant w/ tool_calls, tool result, final assistant
    roles = [m["role"] for m in result["messages"]]
    assert roles == ["assistant", "tool", "assistant"]


# ---------------------------------------------------------------------------
# Test 3: Max rounds exceeded
# ---------------------------------------------------------------------------

def test_max_rounds_exceeded():
    responses = [_tool_resp("keyword_score", {"text": "x"})] * 10
    llm = ScriptedLLM(chat_responses=responses)
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=2)

    assert result["stop_reason"] == "max_rounds"
    assert len(result["llm_timings"]) == 2
    assert len(result["tool_timings"]) == 2


# ---------------------------------------------------------------------------
# Test 4: Bad tool name
# ---------------------------------------------------------------------------

def test_bad_tool_name():
    llm = ScriptedLLM(chat_responses=[
        _tool_resp("nonexistent", {}),
        _final_resp("done"),
    ])
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=5)

    assert result["stop_reason"] == "final"
    assert len(result["tool_timings"]) == 1
    # error is in the tool timing result excerpt, not raised
    assert "nonexistent" in result["tool_timings"][0]["name"]
    assert "error" in result["tool_timings"][0]["result_excerpt"]


# ---------------------------------------------------------------------------
# Test 5: LLM raises exception
# ---------------------------------------------------------------------------

def test_llm_raises_exception():
    # ScriptedLLM exhausts on second call — it raises AssertionError
    llm = ScriptedLLM(chat_responses=[_tool_resp("keyword_score", {"text": "x"})])
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=5)

    assert result["stop_reason"] == "error"
    assert result["error"] is not None
    assert isinstance(result["error"], str)


# ---------------------------------------------------------------------------
# Test 6: Args coercion — stringified JSON arguments
# ---------------------------------------------------------------------------

def test_args_coercion_string_json():
    llm = ScriptedLLM(chat_responses=[
        _tool_resp("keyword_score", json.dumps({"text": "hi"})),
        _final_resp("done"),
    ])
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=5)

    assert result["stop_reason"] == "final"
    assert result["tool_timings"][0]["args"] == {"text": "hi"}


# ---------------------------------------------------------------------------
# Test 7: Initial state preserved
# ---------------------------------------------------------------------------

def test_initial_state_preserved():
    system_msg = {"role": "system", "content": "You are a classifier."}
    llm = ScriptedLLM(chat_responses=[_final_resp("done")])
    state: EngineState = {"messages": [system_msg]}
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=5)

    assert result["messages"][0] == system_msg
    assert len(result["messages"]) == 2  # system + final assistant


# ---------------------------------------------------------------------------
# Test 8: _current_round removed before return
# ---------------------------------------------------------------------------

def test_current_round_removed_on_final():
    llm = ScriptedLLM(chat_responses=[_final_resp()])
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=5)
    assert "_current_round" not in result


def test_current_round_removed_on_max_rounds():
    llm = ScriptedLLM(chat_responses=[_tool_resp("keyword_score", {"text": "x"})] * 10)
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=1)
    assert "_current_round" not in result


def test_current_round_removed_on_error():
    llm = ScriptedLLM(chat_responses=[])  # exhausts immediately
    state = _empty_state()
    result = _engine().run(state, TOOL_REGISTRY, llm, max_rounds=5)
    assert "_current_round" not in result


# ---------------------------------------------------------------------------
# Test 9: Both adapters satisfy Protocol
# ---------------------------------------------------------------------------

def test_both_adapters_satisfy_protocol():
    assert isinstance(ManualEngine(), Engine)
    assert isinstance(ScriptedEngine({}), Engine)


# ---------------------------------------------------------------------------
# Test 10: ScriptedEngine returns canned state
# ---------------------------------------------------------------------------

def test_scripted_engine_returns_canned_state():
    canned = {
        "stop_reason": "final",
        "messages": [{"role": "assistant", "content": "canned"}],
    }
    engine = ScriptedEngine(canned)
    result = engine.run({}, TOOL_REGISTRY, None, max_rounds=5)

    assert result["stop_reason"] == "final"
    assert result["messages"] == [{"role": "assistant", "content": "canned"}]
    assert result["error"] is None
