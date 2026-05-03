"""Tracer: pure derivation of Trace JSON from a final EngineState.

No I/O. No clock reads. Output shape matches what output._write_traces consumes.
"""

from dataclasses import dataclass
from pathlib import Path

from veasy_peasy.engine import EngineState


@dataclass(frozen=True)
class FastPathStep:
    tool: str               # e.g. "try_passport"
    result: dict | None     # MRZ data dict, or None if no MRZ found
    elapsed_s: float
    decision: str | None    # "passport" if MRZ matched, else None


def from_state(
    final_state: EngineState,
    fast_path_step: FastPathStep | None,
    model: str,
    file_path: Path,
    wall_time_s: float,
    final_classification: str = "unknown",
    final_reason: str = "",
) -> dict:
    """Build the Trace JSON from a final EngineState and an optional FastPathStep.

    Pure: no I/O, no clock reads. Output JSON shape matches what
    orchestrator.classify_document currently writes.
    """
    steps = []

    # Determine decision_path and whether the fast path short-circuited.
    fast_path_hit = (
        fast_path_step is not None and fast_path_step.decision == "passport"
    )
    decision_path = "deterministic_mrz" if fast_path_hit else "llm_orchestrator"

    # 1. Fast path tool_call step (always emitted when fast_path_step provided).
    if fast_path_step is not None:
        steps.append({
            "step": len(steps) + 1,
            "kind": "tool_call",
            "tool": fast_path_step.tool,
            "result": fast_path_step.result,
            "elapsed_s": fast_path_step.elapsed_s,
        })
        if fast_path_hit:
            steps.append({
                "step": len(steps) + 1,
                "kind": "decision",
                "rule": "mrz_type_starts_with_P",
                "outcome": "passport",
            })
            # Fast path short-circuited: return immediately, override classification.
            return {
                "file": str(file_path.resolve()),
                "final_classification": "passport",
                "decision_path": decision_path,
                "model": model,
                "wall_time_s": round(wall_time_s, 3),
                "steps": steps,
            }

    # 2. Engine steps (only reached if fast path did not hit).
    llm_timings = final_state.get("llm_timings") or []
    tool_timings = final_state.get("tool_timings") or []
    messages = final_state.get("messages") or []

    # Pair each llm_timing entry (one per round) with the assistant message
    # produced in that round. Assistant messages appear in messages in the
    # same order the rounds executed; one per round for tool-calling rounds,
    # plus one final assistant message for the "final" stop.
    assistant_messages = [m for m in messages if m.get("role") == "assistant"]

    for i, timing in enumerate(llm_timings):
        round_idx = timing["round"]

        # Match the i-th llm_timing to the i-th assistant message.
        msg = assistant_messages[i] if i < len(assistant_messages) else {}
        content = (msg.get("content") or "")[:500]
        raw_tool_calls = msg.get("tool_calls") or []
        tool_calls = [
            {
                "name": tc.get("function", {}).get("name"),
                "args": tc.get("function", {}).get("arguments"),
            }
            for tc in raw_tool_calls
        ]

        steps.append({
            "step": len(steps) + 1,
            "kind": "llm_message",
            "content": content,
            "tool_calls": tool_calls,
            "wall_time_s": round(timing.get("wall_time_s", 0.0), 3),
        })

        # Emit tool_result steps for this round, preserving original order.
        for tt in tool_timings:
            if tt.get("round") == round_idx:
                steps.append({
                    "step": len(steps) + 1,
                    "kind": "tool_result",
                    "tool": tt["name"],
                    "args": tt["args"],
                    "result_excerpt": tt["result_excerpt"],
                    "elapsed_s": tt["elapsed_s"],
                })

    # 3. Final step based on stop_reason.
    stop_reason = final_state.get("stop_reason", "final")

    if stop_reason == "final":
        steps.append({
            "step": len(steps) + 1,
            "kind": "llm_final",
            "classification": final_classification,
            "reason": final_reason,
        })
    elif stop_reason == "max_rounds":
        final_classification = "unknown"
        steps.append({
            "step": len(steps) + 1,
            "kind": "decision",
            "rule": "max_rounds_exceeded",
            "outcome": "unknown",
        })
    elif stop_reason == "error":
        final_classification = "unknown"
        steps.append({
            "step": len(steps) + 1,
            "kind": "error",
            "message": final_state.get("error") or "",
        })

    return {
        "file": str(file_path.resolve()),
        "final_classification": final_classification,
        "decision_path": decision_path,
        "model": model,
        "wall_time_s": round(wall_time_s, 3),
        "steps": steps,
    }
