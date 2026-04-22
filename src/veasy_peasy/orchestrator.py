"""Per-document classifier orchestrator.

Hybrid design:
  1. Deterministic fast path — a valid passport MRZ short-circuits the LLM.
  2. LLM tool-call loop — for everything else. The LLM (via Ollama tool-calling)
     picks which extractor to run, observes the result, and emits a final
     classification drawn from the loaded requirement names.

Every decision is recorded in `trace.steps` so failures are debuggable.
"""

import json
import logging
import time
from pathlib import Path
from typing import Callable

from veasy_peasy.extractors.passport import try_passport
from veasy_peasy.ollama_client import chat_with_tools
from veasy_peasy.tools import TOOL_DISPATCH, TOOL_SCHEMAS

logger = logging.getLogger(__name__)

MAX_TOOL_ROUNDS = 5
TEXT_EXCERPT_LEN = 500

# Tools that produce text — used to cache a text excerpt on the result.
_TEXT_TOOLS = {"extract_pdf_text", "ocr_image"}


def classify_document(
    path: Path,
    requirements_data: dict,
    model: str,
    chat_fn: Callable[..., dict] = chat_with_tools,
) -> dict:
    """Classify a single document. Returns the full file-result dict (incl. trace)."""
    result = {
        "path": str(path.resolve()),
        "ext": path.suffix.lower(),
        "classification": "unknown",
        "extracted_fields": {},
        "text_excerpt": "",
        "text_length": 0,
        "error": None,
        "trace": {
            "file": str(path.resolve()),
            "final_classification": "unknown",
            "decision_path": "llm_orchestrator",
            "model": model,
            "wall_time_s": 0.0,
            "steps": [],
        },
    }
    trace = result["trace"]
    started = time.time()

    try:
        # 1. Deterministic fast path: valid passport MRZ → passport.
        t0 = time.time()
        mrz = try_passport(path)
        trace["steps"].append({
            "step": len(trace["steps"]) + 1,
            "kind": "tool_call",
            "tool": "try_passport",
            "result": mrz,
            "elapsed_s": round(time.time() - t0, 3),
        })
        if mrz and str(mrz.get("mrz_type", "")).startswith("P"):
            result["classification"] = "passport"
            result["extracted_fields"] = mrz
            trace["final_classification"] = "passport"
            trace["decision_path"] = "deterministic_mrz"
            trace["steps"].append({
                "step": len(trace["steps"]) + 1,
                "kind": "decision",
                "rule": "mrz_type_starts_with_P",
                "outcome": "passport",
            })
            return _finalise(result, started)

        # 2. LLM loop — classify into one of the declared requirement names.
        valid_categories = [d["name"] for d in requirements_data.get("documents", [])]
        messages = _build_initial_messages(path, requirements_data, valid_categories)

        for round_idx in range(MAX_TOOL_ROUNDS):
            resp = chat_fn(model, messages, TOOL_SCHEMAS)
            msg = resp.get("message", {}) or {}
            content = msg.get("content", "") or ""
            tool_calls = msg.get("tool_calls") or []

            trace["steps"].append({
                "step": len(trace["steps"]) + 1,
                "kind": "llm_message",
                "content": content[:500],
                "tool_calls": [
                    {"name": tc.get("function", {}).get("name"),
                     "args": tc.get("function", {}).get("arguments")}
                    for tc in tool_calls
                ],
                "wall_time_s": round(resp.get("wall_time_s", 0.0), 3),
            })

            # No tool calls → LLM is trying to finalise. Parse classification from `content`.
            if not tool_calls:
                final = _parse_final(content, valid_categories)
                trace["steps"].append({
                    "step": len(trace["steps"]) + 1,
                    "kind": "llm_final",
                    "classification": final["classification"],
                    "reason": final["reason"],
                })
                result["classification"] = final["classification"]
                trace["final_classification"] = final["classification"]
                return _finalise(result, started)

            # Otherwise, execute each tool call and feed results back.
            messages.append({"role": "assistant", "content": content, "tool_calls": tool_calls})
            for tc in tool_calls:
                fn = tc.get("function", {}) or {}
                name = fn.get("name", "")
                raw_args = fn.get("arguments", {}) or {}
                args = _coerce_args(raw_args)
                t0 = time.time()
                tool_result = _dispatch_tool(name, args)
                elapsed = round(time.time() - t0, 3)

                trace["steps"].append({
                    "step": len(trace["steps"]) + 1,
                    "kind": "tool_result",
                    "tool": name,
                    "args": args,
                    "result_excerpt": _excerpt_result(tool_result),
                    "elapsed_s": elapsed,
                })

                # Cache text excerpt + fields on the result for downstream matcher.
                if name in _TEXT_TOOLS and isinstance(tool_result, dict) and tool_result.get("text"):
                    if not result["text_excerpt"]:
                        result["text_excerpt"] = tool_result["text"][:TEXT_EXCERPT_LEN]
                        result["text_length"] = tool_result.get("text_length", len(tool_result["text"]))
                if name == "check_mrz" and isinstance(tool_result, dict) and tool_result.get("mrz"):
                    result["extracted_fields"] = tool_result["mrz"]

                messages.append({
                    "role": "tool",
                    "content": json.dumps(tool_result, default=str)[:4000],
                })

        # Ran out of rounds without a final answer.
        trace["steps"].append({
            "step": len(trace["steps"]) + 1,
            "kind": "decision",
            "rule": "max_rounds_exceeded",
            "outcome": "unknown",
        })
        return _finalise(result, started)

    except Exception as e:
        result["error"] = str(e)
        trace["steps"].append({
            "step": len(trace["steps"]) + 1,
            "kind": "error",
            "message": str(e),
        })
        logger.exception("orchestrator failed for %s", path)
        return _finalise(result, started)


def _finalise(result: dict, started_at: float) -> dict:
    result["trace"]["wall_time_s"] = round(time.time() - started_at, 3)
    return result


def _build_initial_messages(path: Path, requirements_data: dict, valid_categories: list[str]) -> list[dict]:
    req_lines = [
        f'- "{d["name"]}": {d.get("description", "")}'
        for d in requirements_data.get("documents", [])
    ]
    category_list = ", ".join(f'"{c}"' for c in valid_categories) + ', "unknown"'

    system = (
        "You classify ONE document into one of the visa-application requirement categories.\n"
        "\n"
        "Workflow:\n"
        "  1. Read the document's text with the appropriate tool.\n"
        "     - .pdf: call extract_pdf_text (start with first_page_only=true; if the text is "
        "sparse or only contains headers/account numbers, call it again with first_page_only=false).\n"
        "     - .jpg/.jpeg/.png: call ocr_image.\n"
        "     - Only use check_mrz if you think it may be a passport image.\n"
        "  2. Compare the CONTENT of the text against the requirement DESCRIPTIONS below. "
        "Match on meaning, not just exact keywords. Examples:\n"
        "     - A utility/gas/electricity/council-tax bill with a home address → proof_of_address.\n"
        "     - A letter inviting someone to travel or stating travel plans → cover_letter.\n"
        "     - A flight/train/hotel booking confirmation → travel_tickets.\n"
        "     - An insurance certificate/schedule covering travel → travel_insurance.\n"
        "     - A bank statement with transactions and balances → bank_statement.\n"
        "     - A letter from an employer confirming employment → employment_letter.\n"
        "  3. keyword_score is a SANITY CHECK using a small hardcoded keyword list that does NOT "
        "cover every requirement category. Never return 'unknown' just because keyword_score is all zero — "
        "judge from the actual text content.\n"
        "  4. Only return 'unknown' if the text content genuinely does not match any requirement.\n"
        "\n"
        f"You have at most {MAX_TOOL_ROUNDS} tool calls. When finished, respond with ONLY a JSON object "
        f"on its own, no markdown fences:\n"
        f"{{\"classification\": <one of: {category_list}>, \"reason\": \"<one sentence\"}}"
    )
    user = (
        f"File: {path.resolve()}\nExtension: {path.suffix.lower()}\n\n"
        "Requirement categories:\n" + "\n".join(req_lines)
    )
    return [
        {"role": "system", "content": system},
        {"role": "user", "content": user},
    ]


def _coerce_args(raw) -> dict:
    """Ollama returns tool args as a dict, but some models send a JSON string."""
    if isinstance(raw, dict):
        return raw
    if isinstance(raw, str):
        try:
            return json.loads(raw)
        except json.JSONDecodeError:
            return {}
    return {}


def _dispatch_tool(name: str, args: dict) -> dict:
    fn = TOOL_DISPATCH.get(name)
    if fn is None:
        return {"error": f"unknown tool: {name}"}
    try:
        return fn(**args)
    except TypeError as e:
        return {"error": f"bad args for {name}: {e}"}
    except Exception as e:
        return {"error": f"{name} raised: {e}"}


def _excerpt_result(result) -> str:
    """Compact representation of a tool result for the trace."""
    if isinstance(result, dict):
        if "text" in result:
            return (result["text"] or "")[:300]
        return json.dumps(result, default=str)[:300]
    return str(result)[:300]


def _parse_final(content: str, valid_categories: list[str]) -> dict:
    """Extract {classification, reason} from the LLM's final message. Fall back to 'unknown'."""
    text = (content or "").strip()
    # Strip code fences if present.
    if text.startswith("```"):
        lines = [l for l in text.split("\n") if not l.strip().startswith("```")]
        text = "\n".join(lines).strip()

    # Try to locate a JSON object anywhere in the content.
    candidate = text
    if not text.startswith("{"):
        start = text.find("{")
        end = text.rfind("}")
        if start != -1 and end != -1 and end > start:
            candidate = text[start:end + 1]

    try:
        data = json.loads(candidate)
    except (json.JSONDecodeError, ValueError):
        return {"classification": "unknown", "reason": "LLM final response was not valid JSON"}

    cls = data.get("classification", "unknown")
    if cls not in valid_categories and cls != "unknown":
        return {"classification": "unknown", "reason": f"LLM returned unknown category: {cls!r}"}
    reason = data.get("reason", "") or ""
    return {"classification": cls, "reason": reason}
