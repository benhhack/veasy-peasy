"""Per-document classifier orchestrator.

Thin coordinator: runs the deterministic Fast Path, hands off to the Engine's
LLM tool-call loop, then derives a Trace from the final EngineState.
"""

import time
from pathlib import Path

from veasy_peasy.engine import Engine, EngineState, ManualEngine
from veasy_peasy.extractors.passport import try_passport
from veasy_peasy.llm import LLM
from veasy_peasy.llm_json import parse_llm_json
from veasy_peasy.tools import TOOL_REGISTRY
from veasy_peasy.tracer import FastPathStep, from_state as build_trace

DEFAULT_MAX_ROUNDS = 5


def classify_document(
    path: Path,
    requirements_data: dict,
    llm: LLM,
    engine: Engine | None = None,
    max_rounds: int = DEFAULT_MAX_ROUNDS,
) -> dict:
    """Classify one document.

    Runs the deterministic Fast Path first. If it doesn't hit, hands off
    to the Engine's LLM tool-call loop, then derives a Trace from the
    final EngineState. Returns the full file-result dict (incl. trace).
    """
    if engine is None:
        engine = ManualEngine()

    started = time.time()

    result = {
        "path": str(path.resolve()),
        "ext": path.suffix.lower(),
        "classification": "unknown",
        "extracted_fields": {},
        "text_excerpt": "",
        "text_length": 0,
        "error": None,
        "trace": None,
    }

    # 1. Fast Path
    fast_path_step = _run_fast_path(path)

    if fast_path_step.decision == "passport":
        result["classification"] = "passport"
        result["extracted_fields"] = fast_path_step.result or {}
        result["text_excerpt"] = ""
        result["text_length"] = 0
        result["error"] = None
        empty_state: EngineState = {
            "messages": [],
            "tool_timings": [],
            "llm_timings": [],
            "artifacts": {},
        }
        result["trace"] = build_trace(
            final_state=empty_state,
            fast_path_step=fast_path_step,
            model=llm.model_name,
            file_path=path,
            wall_time_s=time.time() - started,
        )
        return result

    # 2. Engine loop
    valid_categories = [d["name"] for d in requirements_data.get("documents", [])]
    initial_messages = _build_initial_messages(path, requirements_data, valid_categories, max_rounds)

    state: EngineState = {
        "messages": initial_messages,
        "tool_timings": [],
        "llm_timings": [],
        "artifacts": {},
    }

    final_state = engine.run(state, TOOL_REGISTRY, llm, max_rounds)

    # 3. Pull artifacts off final state
    artifacts = final_state.get("artifacts", {})
    result["extracted_fields"] = artifacts.get("extracted_fields", {}) or {}
    result["text_excerpt"] = artifacts.get("text_excerpt", "")
    result["text_length"] = artifacts.get("text_length", 0)

    # 4. Parse final classification
    final_classification = "unknown"
    final_reason = ""
    if final_state.get("stop_reason") == "final" and final_state.get("messages"):
        last = final_state["messages"][-1]
        parsed = parse_llm_json(last.get("content", ""))
        if parsed is None:
            final_reason = "LLM final response was not valid JSON"
        else:
            cls = parsed.get("classification", "unknown")
            if cls in valid_categories or cls == "unknown":
                final_classification = cls
                final_reason = parsed.get("reason", "") or ""
            else:
                final_reason = f"LLM returned unknown category: {cls!r}"

    if final_state.get("stop_reason") == "error":
        result["error"] = final_state.get("error")

    result["classification"] = final_classification
    result["trace"] = build_trace(
        final_state=final_state,
        fast_path_step=fast_path_step,
        model=llm.model_name,
        file_path=path,
        wall_time_s=time.time() - started,
        final_classification=final_classification,
        final_reason=final_reason,
    )
    return result


def _run_fast_path(path: Path) -> FastPathStep:
    t0 = time.time()
    mrz = try_passport(path)
    elapsed = round(time.time() - t0, 3)
    decision = "passport" if mrz and str(mrz.get("mrz_type", "")).startswith("P") else None
    return FastPathStep(tool="try_passport", result=mrz, elapsed_s=elapsed, decision=decision)


def _build_initial_messages(
    path: Path,
    requirements_data: dict,
    valid_categories: list[str],
    max_rounds: int,
) -> list[dict]:
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
        f"You have at most {max_rounds} tool calls. When finished, respond with ONLY a JSON object "
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
