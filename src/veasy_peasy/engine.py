"""Engine: swappable LLM tool-call loop.

The orchestrator hands an initial EngineState to Engine.run and receives a
final EngineState back. Engine knows nothing about Documents, Requirements, or
Trace JSON shape.
"""

import json
from typing import Any, Protocol, TypedDict, runtime_checkable

from veasy_peasy.llm import LLM
from veasy_peasy.tools import ToolRegistry


class EngineState(TypedDict, total=False):
    messages: list[dict]       # [{role, content, tool_calls?}, ...]
    tool_timings: list[dict]   # written by ToolRegistry.dispatch
    llm_timings: list[dict]    # [{round, wall_time_s}]
    artifacts: dict            # {extracted_fields, text_excerpt, text_length}
    stop_reason: str           # "final" | "max_rounds" | "error"
    error: str | None


@runtime_checkable
class Engine(Protocol):
    def run(
        self,
        state: EngineState,
        tools: ToolRegistry,
        llm: LLM,
        max_rounds: int,
    ) -> EngineState: ...


def _coerce_args(raw: Any) -> dict:
    """Ollama returns tool args as a dict, but some models send a JSON string."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


class ManualEngine:
    def run(
        self,
        state: EngineState,
        tools: ToolRegistry,
        llm: LLM,
        max_rounds: int,
    ) -> EngineState:
        state.setdefault("messages", [])
        state.setdefault("tool_timings", [])
        state.setdefault("llm_timings", [])
        state.setdefault("artifacts", {})

        try:
            for round_idx in range(max_rounds):
                # Bridge to ToolRegistry.dispatch: registry reads state["_current_round"] when
                # stamping tool_timings entries with the round index. The key is transient —
                # popped on every exit path, never declared in EngineState.
                state["_current_round"] = round_idx
                resp = llm.chat(state["messages"], tools.schemas())

                msg = resp.get("message", {}) or {}
                content = msg.get("content", "") or ""
                tool_calls = msg.get("tool_calls") or []

                state["llm_timings"].append({
                    "round": round_idx,
                    "wall_time_s": round(resp.get("wall_time_s", 0.0), 3),
                })

                # Final response: no tool calls → done
                if not tool_calls:
                    state["messages"].append({"role": "assistant", "content": content})
                    state["stop_reason"] = "final"
                    state.pop("_current_round", None)
                    state["error"] = None
                    return state

                # Append assistant message with tool_calls, dispatch each
                state["messages"].append({
                    "role": "assistant",
                    "content": content,
                    "tool_calls": tool_calls,
                })
                for tc in tool_calls:
                    fn = tc.get("function", {}) or {}
                    name = fn.get("name", "")
                    raw_args = fn.get("arguments", {}) or {}
                    args = _coerce_args(raw_args)
                    tool_result = tools.dispatch(name, args, state)
                    state["messages"].append({
                        "role": "tool",
                        "content": json.dumps(tool_result, default=str)[:4000],
                    })

            # Ran out of rounds
            state["stop_reason"] = "max_rounds"
            state.pop("_current_round", None)
            state["error"] = None
            return state

        except Exception as e:
            state["stop_reason"] = "error"
            state["error"] = str(e)
            state.pop("_current_round", None)
            return state
