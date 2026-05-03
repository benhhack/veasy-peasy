"""Golden tests for tracer.from_state."""

from pathlib import Path

import pytest

from veasy_peasy.tracer import FastPathStep, from_state


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _empty_state(**overrides) -> dict:
    state = {
        "messages": [],
        "tool_timings": [],
        "llm_timings": [],
        "artifacts": {},
        "stop_reason": "final",
        "error": None,
    }
    state.update(overrides)
    return state


def _abs_path() -> Path:
    return Path("/abs/test.pdf")


# ---------------------------------------------------------------------------
# 1. Fast path hit (passport)
# ---------------------------------------------------------------------------

def test_fast_path_passport():
    fp = FastPathStep(tool="try_passport", result={"mrz_type": "P"}, elapsed_s=0.1, decision="passport")
    trace = from_state(
        final_state=_empty_state(),
        fast_path_step=fp,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=0.5,
    )

    assert trace["decision_path"] == "deterministic_mrz"
    assert trace["final_classification"] == "passport"
    assert len(trace["steps"]) == 2

    assert trace["steps"][0] == {
        "step": 1, "kind": "tool_call", "tool": "try_passport",
        "result": {"mrz_type": "P"}, "elapsed_s": 0.1,
    }
    assert trace["steps"][1] == {
        "step": 2, "kind": "decision",
        "rule": "mrz_type_starts_with_P", "outcome": "passport",
    }


# ---------------------------------------------------------------------------
# 2. Fast path tried but missed (no MRZ); engine has one final round
# ---------------------------------------------------------------------------

def test_fast_path_missed_no_mrz():
    fp = FastPathStep(tool="try_passport", result=None, elapsed_s=0.05, decision=None)

    # Engine: one round, LLM responded with no tool_calls → final
    state = _empty_state(
        messages=[{"role": "assistant", "content": "It is a passport."}],
        llm_timings=[{"round": 0, "wall_time_s": 1.2}],
        stop_reason="final",
    )

    trace = from_state(
        final_state=state,
        fast_path_step=fp,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=2.0,
        final_classification="passport",
        final_reason="MRZ detected.",
    )

    assert trace["decision_path"] == "llm_orchestrator"
    assert trace["final_classification"] == "passport"
    assert len(trace["steps"]) == 3

    assert trace["steps"][0]["kind"] == "tool_call"
    assert trace["steps"][0]["step"] == 1
    assert trace["steps"][1]["kind"] == "llm_message"
    assert trace["steps"][1]["step"] == 2
    assert trace["steps"][2]["kind"] == "llm_final"
    assert trace["steps"][2]["step"] == 3
    assert trace["steps"][2]["classification"] == "passport"


# ---------------------------------------------------------------------------
# 3. No fast path attempt; engine has one final round
# ---------------------------------------------------------------------------

def test_no_fast_path():
    state = _empty_state(
        messages=[{"role": "assistant", "content": "Driving licence."}],
        llm_timings=[{"round": 0, "wall_time_s": 0.9}],
        stop_reason="final",
    )

    trace = from_state(
        final_state=state,
        fast_path_step=None,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=1.1,
        final_classification="driving_licence",
        final_reason="text matches",
    )

    assert trace["decision_path"] == "llm_orchestrator"
    assert len(trace["steps"]) == 2

    assert trace["steps"][0]["kind"] == "llm_message"
    assert trace["steps"][0]["step"] == 1
    assert trace["steps"][1]["kind"] == "llm_final"
    assert trace["steps"][1]["step"] == 2
    assert trace["steps"][1]["classification"] == "driving_licence"


# ---------------------------------------------------------------------------
# 4. One tool round then final
# ---------------------------------------------------------------------------

def test_one_tool_round_then_final():
    fp = FastPathStep(tool="try_passport", result=None, elapsed_s=0.05, decision=None)

    # Round 0: LLM calls extract_pdf_text; round 1: LLM gives final answer
    tool_calls_round0 = [
        {"function": {"name": "extract_pdf_text", "arguments": {"path": "/doc.pdf"}}}
    ]
    state = _empty_state(
        messages=[
            {"role": "assistant", "content": "Checking text.", "tool_calls": tool_calls_round0},
            {"role": "tool", "content": '{"text": "some text"}'},
            {"role": "assistant", "content": "It is a passport."},
        ],
        llm_timings=[
            {"round": 0, "wall_time_s": 0.8},
            {"round": 1, "wall_time_s": 0.6},
        ],
        tool_timings=[
            {
                "round": 0, "name": "extract_pdf_text",
                "args": {"path": "/doc.pdf"}, "elapsed_s": 0.2,
                "result_excerpt": "some text",
            }
        ],
        stop_reason="final",
    )

    trace = from_state(
        final_state=state,
        fast_path_step=fp,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=3.0,
        final_classification="passport",
        final_reason="PDF text confirms passport.",
    )

    kinds = [s["kind"] for s in trace["steps"]]
    assert kinds == ["tool_call", "llm_message", "tool_result", "llm_message", "llm_final"]

    steps_by_kind = {s["kind"]: s for s in trace["steps"] if s["kind"] == "tool_result"}
    assert steps_by_kind["tool_result"]["tool"] == "extract_pdf_text"


# ---------------------------------------------------------------------------
# 5. Two tools in one round
# ---------------------------------------------------------------------------

def test_two_tools_same_round():
    tool_calls = [
        {"function": {"name": "extract_pdf_text", "arguments": {"path": "/doc.pdf"}}},
        {"function": {"name": "check_mrz", "arguments": {"path": "/doc.pdf"}}},
    ]
    state = _empty_state(
        messages=[
            {"role": "assistant", "content": "Checking both.", "tool_calls": tool_calls},
            {"role": "tool", "content": '{"text": "some text"}'},
            {"role": "tool", "content": '{"mrz": null}'},
            {"role": "assistant", "content": "Not a passport."},
        ],
        llm_timings=[
            {"round": 0, "wall_time_s": 0.7},
            {"round": 1, "wall_time_s": 0.5},
        ],
        tool_timings=[
            {
                "round": 0, "name": "extract_pdf_text",
                "args": {"path": "/doc.pdf"}, "elapsed_s": 0.1,
                "result_excerpt": "some text",
            },
            {
                "round": 0, "name": "check_mrz",
                "args": {"path": "/doc.pdf"}, "elapsed_s": 0.2,
                "result_excerpt": '{"mrz": null}',
            },
        ],
        stop_reason="final",
    )

    trace = from_state(
        final_state=state,
        fast_path_step=None,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=2.0,
        final_classification="unknown",
        final_reason="",
    )

    kinds = [s["kind"] for s in trace["steps"]]
    assert kinds == ["llm_message", "tool_result", "tool_result", "llm_message", "llm_final"]

    tool_results = [s for s in trace["steps"] if s["kind"] == "tool_result"]
    assert tool_results[0]["tool"] == "extract_pdf_text"
    assert tool_results[1]["tool"] == "check_mrz"


# ---------------------------------------------------------------------------
# 6. Max rounds exit
# ---------------------------------------------------------------------------

def test_max_rounds_exit():
    state = _empty_state(
        messages=[
            {"role": "assistant", "content": "Calling tool.", "tool_calls": [
                {"function": {"name": "extract_pdf_text", "arguments": {}}}
            ]},
        ],
        llm_timings=[{"round": 0, "wall_time_s": 0.5}],
        tool_timings=[
            {
                "round": 0, "name": "extract_pdf_text",
                "args": {}, "elapsed_s": 0.1, "result_excerpt": "",
            }
        ],
        stop_reason="max_rounds",
        error=None,
    )

    trace = from_state(
        final_state=state,
        fast_path_step=None,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=5.0,
        final_classification="passport",  # should be overridden to "unknown"
    )

    assert trace["final_classification"] == "unknown"
    last = trace["steps"][-1]
    assert last["kind"] == "decision"
    assert last["rule"] == "max_rounds_exceeded"
    assert last["outcome"] == "unknown"


# ---------------------------------------------------------------------------
# 7. Error exit
# ---------------------------------------------------------------------------

def test_error_exit():
    state = _empty_state(
        stop_reason="error",
        error="some failure",
    )

    trace = from_state(
        final_state=state,
        fast_path_step=None,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=0.3,
        final_classification="passport",  # should be overridden to "unknown"
    )

    assert trace["final_classification"] == "unknown"
    last = trace["steps"][-1]
    assert last["kind"] == "error"
    assert last["message"] == "some failure"


# ---------------------------------------------------------------------------
# 8. Step numbers are contiguous and 1-indexed
# ---------------------------------------------------------------------------

def test_step_numbers_contiguous():
    fp = FastPathStep(tool="try_passport", result=None, elapsed_s=0.05, decision=None)
    tool_calls = [
        {"function": {"name": "extract_pdf_text", "arguments": {"path": "/doc.pdf"}}}
    ]
    state = _empty_state(
        messages=[
            {"role": "assistant", "content": "text", "tool_calls": tool_calls},
            {"role": "tool", "content": "{}"},
            {"role": "assistant", "content": "done"},
        ],
        llm_timings=[
            {"round": 0, "wall_time_s": 0.5},
            {"round": 1, "wall_time_s": 0.4},
        ],
        tool_timings=[
            {
                "round": 0, "name": "extract_pdf_text",
                "args": {"path": "/doc.pdf"}, "elapsed_s": 0.1,
                "result_excerpt": "",
            }
        ],
        stop_reason="final",
    )

    trace = from_state(
        final_state=state,
        fast_path_step=fp,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=2.0,
        final_classification="unknown",
    )

    step_nums = [s["step"] for s in trace["steps"]]
    assert step_nums == list(range(1, len(trace["steps"]) + 1))


# ---------------------------------------------------------------------------
# 9. Content truncation at 500 chars
# ---------------------------------------------------------------------------

def test_content_truncation():
    long_content = "x" * 600
    state = _empty_state(
        messages=[{"role": "assistant", "content": long_content}],
        llm_timings=[{"round": 0, "wall_time_s": 0.5}],
        stop_reason="final",
    )

    trace = from_state(
        final_state=state,
        fast_path_step=None,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=1.0,
    )

    llm_msg = next(s for s in trace["steps"] if s["kind"] == "llm_message")
    assert len(llm_msg["content"]) == 500


# ---------------------------------------------------------------------------
# 10. `file` field is absolute even when file_path is relative
# ---------------------------------------------------------------------------

def test_file_field_is_absolute(tmp_path):
    # Create a real file so resolve() works properly
    doc = tmp_path / "doc.pdf"
    doc.touch()

    # Use a relative path derived from an absolute one (simulate caller passing relative)
    import os
    orig_dir = os.getcwd()
    os.chdir(tmp_path)
    try:
        relative = Path("doc.pdf")
        trace = from_state(
            final_state=_empty_state(),
            fast_path_step=None,
            model="llava",
            file_path=relative,
            wall_time_s=0.1,
        )
    finally:
        os.chdir(orig_dir)

    assert Path(trace["file"]).is_absolute()


# ---------------------------------------------------------------------------
# 11. wall_time_s rounded to 3 decimal places
# ---------------------------------------------------------------------------

def test_wall_time_rounded():
    trace = from_state(
        final_state=_empty_state(),
        fast_path_step=None,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=1.23456789,
    )

    assert trace["wall_time_s"] == round(1.23456789, 3)


# ---------------------------------------------------------------------------
# 12. tool_calls.args is None (not {}) when LLM omits "arguments" key
# ---------------------------------------------------------------------------

def test_tool_call_args_none_when_arguments_key_missing():
    # LLM tool call with no "arguments" key in the function dict.
    tool_calls = [{"function": {"name": "extract_pdf_text"}}]
    state = _empty_state(
        messages=[
            {"role": "assistant", "content": "calling", "tool_calls": tool_calls},
            {"role": "tool", "content": "{}"},
            {"role": "assistant", "content": "done"},
        ],
        llm_timings=[
            {"round": 0, "wall_time_s": 0.1},
            {"round": 1, "wall_time_s": 0.1},
        ],
        tool_timings=[
            {
                "round": 0, "name": "extract_pdf_text",
                "args": {}, "elapsed_s": 0.05, "result_excerpt": "",
            }
        ],
        stop_reason="final",
    )

    trace = from_state(
        final_state=state,
        fast_path_step=None,
        model="llava",
        file_path=_abs_path(),
        wall_time_s=0.5,
    )

    llm_msg = next(s for s in trace["steps"] if s["kind"] == "llm_message")
    assert llm_msg["tool_calls"][0]["args"] is None
