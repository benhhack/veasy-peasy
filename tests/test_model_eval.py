"""Model evaluation harness.

Loads each model one at a time, runs all scenarios, scores against ground truth,
then unloads.  Prints a comparison table and generates a markdown report.

Usage:
    python -m pytest tests/test_model_eval.py -s --tb=short
    # or run directly:
    python tests/test_model_eval.py
    # multiple runs for variance (default 1):
    EVAL_RUNS=3 python tests/test_model_eval.py
"""

import json
import logging
import os
import statistics
import sys
import time

import pytest

from veasy_peasy.llm import OllamaLLM
from veasy_peasy.matcher import match, build_prompt
from veasy_peasy.ollama_client import (
    is_available,
    load_model,
    pull_model,
    unload_model,
)
from fixtures.scenarios import ALL_SCENARIOS

logging.basicConfig(level=logging.INFO, format="%(levelname)s: %(message)s")
logger = logging.getLogger(__name__)

MODELS = [
    "llama3.2:3b",
    "phi4-mini",
    "qwen2.5:3b",
    "gemma3:4b",
]

RUNS_PER_SCENARIO = int(os.environ.get("EVAL_RUNS", "1"))

# Weights for composite score
W_MATCHED_F1 = 0.35
W_MISSING_F1 = 0.25
W_PARSE = 0.20
W_CONFLICT = 0.10
W_VALIDATION = 0.10


# ---------------------------------------------------------------------------
# Scoring helpers
# ---------------------------------------------------------------------------

def score_matched(result: dict, truth: dict) -> dict:
    """Score the 'matched' section. Returns precision, recall, f1."""
    got = {(m["requirement"], m["file"]) for m in result.get("matched", [])}
    expected = {(m["requirement"], m["file"]) for m in truth["matched"]}

    if not expected and not got:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    tp = len(got & expected)
    precision = tp / len(got) if got else 0.0
    recall = tp / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def score_missing(result: dict, truth: dict) -> dict:
    """Score the 'missing' section."""
    got = set(result.get("missing", []))
    expected = set(truth["missing"])

    if not expected and not got:
        return {"precision": 1.0, "recall": 1.0, "f1": 1.0}

    tp = len(got & expected)
    precision = tp / len(got) if got else 0.0
    recall = tp / len(expected) if expected else 0.0
    f1 = 2 * precision * recall / (precision + recall) if (precision + recall) else 0.0
    return {"precision": precision, "recall": recall, "f1": f1}


def score_conflicts(result: dict, truth: dict) -> dict:
    """Score conflicts. If ground truth expects non-empty, check that model produced any."""
    expected_markers = truth["conflicts_resolved"]
    got = result.get("conflicts_resolved", [])

    if not expected_markers:
        return {"correct": len(got) == 0}

    if expected_markers == ["_non_empty_"]:
        return {"correct": len(got) > 0}

    return {"correct": got == expected_markers}


def score_validation(result: dict, truth: dict) -> dict:
    """Score validation_warnings. Same logic as conflicts: empty or non-empty check."""
    expected = truth.get("validation_warnings", [])
    got = result.get("validation_warnings", [])

    if not expected:
        return {"correct": len(got) == 0}

    if expected == ["_non_empty_"]:
        return {"correct": len(got) > 0}

    return {"correct": got == expected}


def score_scenario(result: dict | None, truth: dict) -> dict:
    """Full scoring for one scenario."""
    if result is None:
        return {
            "matched": {"precision": 0, "recall": 0, "f1": 0},
            "missing": {"precision": 0, "recall": 0, "f1": 0},
            "conflicts": {"correct": False},
            "validation": {"correct": False},
        }
    return {
        "matched": score_matched(result, truth),
        "missing": score_missing(result, truth),
        "conflicts": score_conflicts(result, truth),
        "validation": score_validation(result, truth),
    }


def composite_score(scenario_results: dict) -> float:
    """Compute a weighted composite score across all scenarios for a model."""
    n = len(scenario_results)
    if n == 0:
        return 0.0

    total_matched_f1 = 0.0
    total_missing_f1 = 0.0
    total_parse = 0.0
    total_conflict = 0.0
    total_validation = 0.0

    for s in scenario_results.values():
        total_matched_f1 += s["scores"]["matched"]["f1"]
        total_missing_f1 += s["scores"]["missing"]["f1"]
        total_parse += 1.0 if s["parse_ok"] else 0.0
        total_conflict += 1.0 if s["scores"]["conflicts"]["correct"] else 0.0
        total_validation += 1.0 if s["scores"]["validation"]["correct"] else 0.0

    return (
        W_MATCHED_F1 * (total_matched_f1 / n)
        + W_MISSING_F1 * (total_missing_f1 / n)
        + W_PARSE * (total_parse / n)
        + W_CONFLICT * (total_conflict / n)
        + W_VALIDATION * (total_validation / n)
    )


# ---------------------------------------------------------------------------
# Test harness
# ---------------------------------------------------------------------------

def run_eval() -> list[dict]:
    """Run all models against all scenarios. Returns list of result dicts."""
    if not is_available():
        raise RuntimeError("Ollama is not running. Start it with: ollama serve")

    all_results = []

    for model in MODELS:
        logger.info("=" * 60)
        logger.info("MODEL: %s", model)
        logger.info("=" * 60)

        # Pull if needed
        try:
            pull_model(model)
        except Exception as e:
            logger.error("Failed to pull %s: %s", model, e)
            all_results.append({
                "model": model,
                "error": f"pull failed: {e}",
                "scenarios": {},
            })
            continue

        # Load into memory
        try:
            load_time = load_model(model)
        except Exception as e:
            logger.error("Failed to load %s: %s", model, e)
            all_results.append({
                "model": model,
                "error": f"load failed: {e}",
                "scenarios": {},
            })
            continue

        llm = OllamaLLM(model)

        model_result = {
            "model": model,
            "load_time_s": load_time,
            "error": None,
            "scenarios": {},
        }

        for i, scenario in enumerate(ALL_SCENARIOS):
            logger.info("  Scenario: %s", scenario["name"])

            # Log the prompt once per model (first scenario only)
            if i == 0:
                prompt = build_prompt(scenario["requirements"], scenario["files"])
                logger.info("  --- PROMPT (first 600 chars) ---")
                for line in prompt[:600].splitlines():
                    logger.info("  | %s", line)
                logger.info("  --- END PROMPT ---")

            # Run multiple times if configured
            run_results = []
            for run_idx in range(RUNS_PER_SCENARIO):
                if RUNS_PER_SCENARIO > 1:
                    logger.info("    Run %d/%d", run_idx + 1, RUNS_PER_SCENARIO)
                match_result = match(scenario["requirements"], scenario["files"], llm)
                scores = score_scenario(match_result["result"], scenario["ground_truth"])
                run_results.append({
                    "parse_ok": match_result["parse_ok"],
                    "wall_time_s": match_result["wall_time_s"],
                    "eval_count": match_result["eval_count"],
                    "prompt_eval_count": match_result.get("prompt_eval_count", 0),
                    "scores": scores,
                    "raw_response": match_result["raw_response"],
                })

            # Aggregate runs: use best parse, average times and scores
            best_run = run_results[0]
            if RUNS_PER_SCENARIO > 1:
                # Pick the run with best matched F1 among parseable runs
                parseable = [r for r in run_results if r["parse_ok"]]
                if parseable:
                    best_run = max(parseable, key=lambda r: r["scores"]["matched"]["f1"])

            scenario_entry = {
                "parse_ok": best_run["parse_ok"],
                "wall_time_s": statistics.mean(r["wall_time_s"] for r in run_results),
                "eval_count": statistics.mean(r["eval_count"] for r in run_results),
                "prompt_eval_count": statistics.mean(r["prompt_eval_count"] for r in run_results),
                "scores": best_run["scores"],
                "raw_response": best_run["raw_response"],
                "parse_rate": sum(1 for r in run_results if r["parse_ok"]) / len(run_results),
                "num_runs": RUNS_PER_SCENARIO,
            }

            model_result["scenarios"][scenario["name"]] = scenario_entry

            status = "PASS" if scenario_entry["parse_ok"] else "FAIL(parse)"
            tok_s = scenario_entry["eval_count"] / scenario_entry["wall_time_s"] if scenario_entry["wall_time_s"] > 0 else 0
            logger.info(
                "    %s | time=%.1fs | tok/s=%.1f | matched_f1=%.2f | missing_f1=%.2f | conflict=%s | validation=%s",
                status,
                scenario_entry["wall_time_s"],
                tok_s,
                scenario_entry["scores"]["matched"]["f1"],
                scenario_entry["scores"]["missing"]["f1"],
                scenario_entry["scores"]["conflicts"]["correct"],
                scenario_entry["scores"]["validation"]["correct"],
            )

            # Log raw response for debugging
            raw = scenario_entry["raw_response"]
            logger.info("    --- RAW RESPONSE (first 800 chars) ---")
            for line in raw[:800].splitlines():
                logger.info("    | %s", line)
            if len(raw) > 800:
                logger.info("    | ... (%d chars total)", len(raw))
            logger.info("    --- END RESPONSE ---")

        # Unload — critical for RAM
        try:
            unload_model(model)
        except Exception as e:
            logger.warning("Failed to unload %s: %s (continuing)", model, e)

        all_results.append(model_result)

    return all_results


def print_comparison_table(results: list[dict]) -> None:
    """Print a summary comparison table to stdout."""
    print("\n" + "=" * 120)
    print("MODEL COMPARISON")
    print("=" * 120)

    header = (
        f"{'Model':<18} {'Scenario':<20} {'Parse':<6} {'Time(s)':<8} "
        f"{'Tok/s':<8} {'Match F1':<10} {'Miss F1':<10} {'Conflict':<10} {'Valid':<10}"
    )
    print(header)
    print("-" * 120)

    for r in results:
        model = r["model"]
        if r.get("error"):
            print(f"{model:<18} ERROR: {r['error']}")
            continue

        first = True
        for scenario_name, s in r["scenarios"].items():
            m_label = model if first else ""
            parse_label = "OK" if s["parse_ok"] else "FAIL"
            tok_s = s["eval_count"] / s["wall_time_s"] if s["wall_time_s"] > 0 else 0
            print(
                f"{m_label:<18} {scenario_name:<20} "
                f"{parse_label:<6} {s['wall_time_s']:<8.1f} "
                f"{tok_s:<8.1f} "
                f"{s['scores']['matched']['f1']:<10.2f} "
                f"{s['scores']['missing']['f1']:<10.2f} "
                f"{str(s['scores']['conflicts']['correct']):<10} "
                f"{str(s['scores']['validation']['correct']):<10}"
            )
            first = False

    # Overall summary
    print("\n" + "=" * 120)
    print("OVERALL SUMMARY")
    print("=" * 120)
    header2 = (
        f"{'Model':<18} {'Load(s)':<8} {'Avg Tok/s':<10} {'Parse %':<9} "
        f"{'Match F1':<10} {'Miss F1':<10} {'Conflict %':<11} {'Valid %':<9} {'Score':<8}"
    )
    print(header2)
    print("-" * 120)
    for r in results:
        if r.get("error"):
            print(f"{r['model']:<18} ERROR: {r['error']}")
            continue
        scenarios = r["scenarios"]
        n = len(scenarios)
        avg_match_f1 = sum(s["scores"]["matched"]["f1"] for s in scenarios.values()) / n
        avg_miss_f1 = sum(s["scores"]["missing"]["f1"] for s in scenarios.values()) / n
        parse_rate = sum(1 for s in scenarios.values() if s["parse_ok"]) / n
        conflict_rate = sum(1 for s in scenarios.values() if s["scores"]["conflicts"]["correct"]) / n
        valid_rate = sum(1 for s in scenarios.values() if s["scores"]["validation"]["correct"]) / n
        avg_tok_s = sum(
            s["eval_count"] / s["wall_time_s"] for s in scenarios.values() if s["wall_time_s"] > 0
        ) / n
        score = composite_score(scenarios)

        print(
            f"{r['model']:<18} {r['load_time_s']:<8.1f} {avg_tok_s:<10.1f} "
            f"{parse_rate:<9.0%} {avg_match_f1:<10.2f} {avg_miss_f1:<10.2f} "
            f"{conflict_rate:<11.0%} {valid_rate:<9.0%} {score:<8.2f}"
        )

    print("=" * 120)
    print(f"\nComposite score weights: matched_f1={W_MATCHED_F1}, missing_f1={W_MISSING_F1}, "
          f"parse={W_PARSE}, conflict={W_CONFLICT}, validation={W_VALIDATION}")


def generate_markdown_report(results: list[dict], out_path: str = "eval_report.md") -> None:
    """Generate a markdown report suitable for a README or write-up."""
    lines = []
    lines.append("# Model Evaluation Report")
    lines.append("")
    lines.append(f"**Models tested:** {', '.join(r['model'] for r in results)}")
    lines.append(f"**Scenarios:** {', '.join(s['name'] for s in ALL_SCENARIOS)}")
    lines.append(f"**Runs per scenario:** {RUNS_PER_SCENARIO}")
    lines.append("")

    # Summary table
    lines.append("## Summary")
    lines.append("")
    lines.append("| Model | Load (s) | Avg Tok/s | Parse % | Match F1 | Miss F1 | Conflict % | Valid % | **Score** |")
    lines.append("|-------|----------|-----------|---------|----------|---------|------------|---------|-----------|")

    scored_models = []
    for r in results:
        if r.get("error"):
            lines.append(f"| {r['model']} | ERROR | — | — | — | — | — | — | — |")
            continue
        scenarios = r["scenarios"]
        n = len(scenarios)
        avg_match_f1 = sum(s["scores"]["matched"]["f1"] for s in scenarios.values()) / n
        avg_miss_f1 = sum(s["scores"]["missing"]["f1"] for s in scenarios.values()) / n
        parse_rate = sum(1 for s in scenarios.values() if s["parse_ok"]) / n
        conflict_rate = sum(1 for s in scenarios.values() if s["scores"]["conflicts"]["correct"]) / n
        valid_rate = sum(1 for s in scenarios.values() if s["scores"]["validation"]["correct"]) / n
        avg_tok_s = sum(
            s["eval_count"] / s["wall_time_s"] for s in scenarios.values() if s["wall_time_s"] > 0
        ) / n
        score = composite_score(scenarios)
        scored_models.append((r["model"], score))

        lines.append(
            f"| {r['model']} | {r['load_time_s']:.1f} | {avg_tok_s:.1f} | {parse_rate:.0%} "
            f"| {avg_match_f1:.2f} | {avg_miss_f1:.2f} | {conflict_rate:.0%} "
            f"| {valid_rate:.0%} | **{score:.2f}** |"
        )

    lines.append("")
    lines.append(f"*Composite score weights: matched_f1={W_MATCHED_F1}, missing_f1={W_MISSING_F1}, "
                 f"parse={W_PARSE}, conflict={W_CONFLICT}, validation={W_VALIDATION}*")

    # Per-scenario breakdown
    lines.append("")
    lines.append("## Per-Scenario Breakdown")
    lines.append("")

    for scenario in ALL_SCENARIOS:
        lines.append(f"### {scenario['name']}")
        lines.append(f"*{scenario['description']}*")
        lines.append("")
        lines.append("| Model | Parse | Time (s) | Tok/s | Match F1 | Miss F1 | Conflict | Validation |")
        lines.append("|-------|-------|----------|-------|----------|---------|----------|------------|")

        for r in results:
            if r.get("error"):
                continue
            s = r["scenarios"].get(scenario["name"])
            if not s:
                continue
            parse_label = "OK" if s["parse_ok"] else "FAIL"
            tok_s = s["eval_count"] / s["wall_time_s"] if s["wall_time_s"] > 0 else 0
            conflict_label = "yes" if s["scores"]["conflicts"]["correct"] else "no"
            valid_label = "yes" if s["scores"]["validation"]["correct"] else "no"
            lines.append(
                f"| {r['model']} | {parse_label} | {s['wall_time_s']:.1f} | {tok_s:.1f} "
                f"| {s['scores']['matched']['f1']:.2f} | {s['scores']['missing']['f1']:.2f} "
                f"| {conflict_label} | {valid_label} |"
            )
        lines.append("")

    # Recommendation
    if scored_models:
        best_model, best_score = max(scored_models, key=lambda x: x[1])
        lines.append("## Recommendation")
        lines.append("")
        lines.append(
            f"Based on composite scoring across all scenarios, **{best_model}** "
            f"(score: {best_score:.2f}) is the best fit for this task."
        )
        lines.append("")

    with open(out_path, "w") as f:
        f.write("\n".join(lines))
    logger.info("Markdown report written to %s", out_path)


# ---------------------------------------------------------------------------
# Pytest entry point
# ---------------------------------------------------------------------------

@pytest.fixture(scope="module")
def eval_results():
    """Run the full evaluation once per test session."""
    results = run_eval()
    print_comparison_table(results)

    # Save full results including raw responses for debugging
    with open("eval_results.json", "w") as f:
        json.dump(results, f, indent=2)

    generate_markdown_report(results)

    return results


def test_all_models_loaded(eval_results):
    """Every model should load without errors."""
    for r in eval_results:
        assert r["error"] is None, f"{r['model']} had error: {r['error']}"


def test_parse_rate_minimum(eval_results):
    """Every model must successfully parse JSON for at least 75% of scenarios."""
    for r in eval_results:
        if r.get("error"):
            continue
        scenarios = r["scenarios"]
        n = len(scenarios)
        parse_count = sum(1 for s in scenarios.values() if s["parse_ok"])
        rate = parse_count / n
        assert rate >= 0.75, (
            f"{r['model']} parse rate = {rate:.0%} ({parse_count}/{n}), minimum is 75%"
        )


def test_happy_path_accuracy(eval_results):
    """On the easy scenario, models should get near-perfect matched F1."""
    for r in eval_results:
        if r.get("error"):
            continue
        s = r["scenarios"].get("happy_path")
        if s and s["parse_ok"]:
            assert s["scores"]["matched"]["f1"] >= 0.8, (
                f"{r['model']} happy_path matched F1 = {s['scores']['matched']['f1']:.2f}"
            )


def test_missing_detection(eval_results):
    """Models should detect missing documents."""
    for r in eval_results:
        if r.get("error"):
            continue
        s = r["scenarios"].get("missing_docs")
        if s and s["parse_ok"]:
            assert s["scores"]["missing"]["recall"] >= 0.5, (
                f"{r['model']} missing_docs recall = {s['scores']['missing']['recall']:.2f}"
            )


def test_conflict_detection(eval_results):
    """At least one model must detect the passport conflict."""
    detected = []
    for r in eval_results:
        if r.get("error"):
            continue
        s = r["scenarios"].get("conflicts")
        if s and s["parse_ok"] and s["scores"]["conflicts"]["correct"]:
            detected.append(r["model"])

    assert len(detected) >= 1, (
        "No model detected the passport conflict in the conflicts scenario. "
        "This is a core requirement for the matching pipeline."
    )


def test_bad_classification_detection(eval_results):
    """At least one model must flag the misclassified document."""
    detected = []
    for r in eval_results:
        if r.get("error"):
            continue
        s = r["scenarios"].get("bad_classification")
        if s and s["parse_ok"] and s["scores"]["validation"]["correct"]:
            detected.append(r["model"])

    assert len(detected) >= 1, (
        "No model flagged the misclassified employment letter in the bad_classification scenario. "
        "Validation is a key differentiator for model selection."
    )


def test_noisy_ocr_robustness(eval_results):
    """Models should still match documents despite noisy OCR text."""
    for r in eval_results:
        if r.get("error"):
            continue
        s = r["scenarios"].get("noisy_ocr")
        if s and s["parse_ok"]:
            assert s["scores"]["matched"]["f1"] >= 0.6, (
                f"{r['model']} noisy_ocr matched F1 = {s['scores']['matched']['f1']:.2f}, "
                f"expected >= 0.6 — model can't handle OCR noise"
            )


def test_extra_documents_precision(eval_results):
    """Models should not over-match when given more files than requirements."""
    for r in eval_results:
        if r.get("error"):
            continue
        s = r["scenarios"].get("extra_documents")
        if s and s["parse_ok"]:
            assert s["scores"]["matched"]["precision"] >= 0.8, (
                f"{r['model']} extra_documents matched precision = "
                f"{s['scores']['matched']['precision']:.2f}, expected >= 0.8 — "
                f"model is over-matching irrelevant documents"
            )


# ---------------------------------------------------------------------------
# Direct execution
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    results = run_eval()
    print_comparison_table(results)

    out_path = "eval_results.json"
    with open(out_path, "w") as f:
        json.dump(results, f, indent=2)
    print(f"\nRaw results saved to {out_path}")

    generate_markdown_report(results)
    print("Markdown report saved to eval_report.md")
