import json
import shutil
from collections import Counter
from datetime import datetime
from pathlib import Path

from veasy_peasy.summary import write_summary


def assemble_output(
    folder: Path,
    file_results: list[dict],
    requirements_data: dict,
    summary_data: dict,
    started_at: datetime,
) -> Path:
    """Create a report folder with LLM-matched file copies, summary.json, and report.md."""
    timestamp = started_at.strftime("%d-%m-%H-%M")
    report_dir = folder / f"VzPz_Report_{timestamp}"
    report_dir.mkdir(exist_ok=True)

    matching = summary_data.get("matching")
    llm_ok = bool(matching and matching.get("parse_ok") and matching.get("result"))

    if llm_ok:
        copied = _copy_matched_files(report_dir, matching["result"], file_results)
    else:
        copied = _copy_classified_files(report_dir, file_results)

    write_summary(report_dir, summary_data)
    _write_traces(report_dir, file_results)

    md = _build_markdown(requirements_data, file_results, copied, matching, llm_ok)
    (report_dir / "report.md").write_text(md)

    return report_dir


def _write_traces(report_dir: Path, file_results: list[dict]) -> None:
    """Write one trace JSON per scanned file into `<report_dir>/traces/`."""
    traces_dir = report_dir / "traces"
    any_trace = False
    seen: Counter[str] = Counter()
    for r in file_results:
        trace = r.get("trace")
        if not trace:
            continue
        if not any_trace:
            traces_dir.mkdir(exist_ok=True)
            any_trace = True
        stem = Path(r["path"]).stem
        seen[stem] += 1
        name = f"{stem}.trace.json" if seen[stem] == 1 else f"{stem}_{seen[stem]}.trace.json"
        (traces_dir / name).write_text(json.dumps(trace, indent=2, default=str) + "\n")


def _by_path(file_results: list[dict]) -> dict[str, dict]:
    return {r["path"]: r for r in file_results}


def _passport_expiry_suffix(file_result: dict) -> str:
    """Return `_exp_YYYYMMDD` suffix if MRZ expiry is present, else ''."""
    expiry = file_result.get("extracted_fields", {}).get("expiry", "")
    if len(expiry) != 6:
        return ""
    dd, mm, yy = expiry[:2], expiry[2:4], expiry[4:6]
    yyyy = f"20{yy}" if int(yy) < 80 else f"19{yy}"
    return f"_exp_{yyyy}{mm}{dd}"


def _copy_matched_files(
    report_dir: Path, matching_result: dict, file_results: list[dict]
) -> list[dict]:
    """Copy each LLM-matched file into report_dir, named after its requirement."""
    path_to_result = _by_path(file_results)

    # Count extra candidates per requirement from conflicts_resolved entries that expose them.
    extra_candidates_by_req: dict[str, list[str]] = {}
    for c in matching_result.get("conflicts_resolved", []) or []:
        if isinstance(c, dict) and c.get("requirement"):
            candidates = c.get("candidates") or c.get("other_files") or []
            if isinstance(candidates, list):
                names = [Path(str(p)).name for p in candidates]
                if names:
                    extra_candidates_by_req[c["requirement"]] = names

    copied: list[dict] = []
    req_seen: Counter[str] = Counter()
    for m in matching_result.get("matched", []) or []:
        if not isinstance(m, dict):
            continue
        requirement = m.get("requirement") or ""
        file_path = m.get("file") or ""
        if not requirement or not file_path:
            continue
        src = Path(file_path)
        if not src.exists():
            continue

        ext = src.suffix.lower()
        file_result = path_to_result.get(str(src.resolve())) or path_to_result.get(file_path) or {}

        req_seen[requirement] += 1
        suffix = _passport_expiry_suffix(file_result) if requirement == "passport" else ""
        if suffix:
            new_name = f"{requirement}{suffix}{ext}"
        elif req_seen[requirement] == 1:
            new_name = f"{requirement}{ext}"
        else:
            new_name = f"{requirement}_{req_seen[requirement]}{ext}"

        shutil.copy2(src, report_dir / new_name)
        copied.append({
            "requirement": requirement,
            "original": src.name,
            "new_name": new_name,
            "reason": m.get("reason", ""),
            "extra_candidates": extra_candidates_by_req.get(requirement, []),
        })

    return copied


def _copy_classified_files(report_dir: Path, file_results: list[dict]) -> list[dict]:
    """Fallback: copy non-unknown files into report_dir using classifier output."""
    cls_counts: Counter[str] = Counter(
        r["classification"] for r in file_results if r["classification"] != "unknown"
    )
    cls_seen: Counter[str] = Counter()
    copied = []

    for r in file_results:
        cls = r["classification"]
        if cls == "unknown":
            continue

        ext = r["ext"]
        src = Path(r["path"])

        if cls_counts[cls] == 1:
            new_name = f"{cls}{ext}"
        else:
            suffix = _passport_expiry_suffix(r) if cls == "passport" else ""
            if suffix:
                new_name = f"{cls}{suffix}{ext}"
            else:
                cls_seen[cls] += 1
                new_name = f"{cls}_{cls_seen[cls]}{ext}"

        shutil.copy2(src, report_dir / new_name)
        copied.append({
            "requirement": cls,
            "original": src.name,
            "new_name": new_name,
            "reason": "",
            "extra_candidates": [],
        })

    return copied


def _build_markdown(
    requirements_data: dict,
    file_results: list[dict],
    copied_files: list[dict],
    matching: dict | None,
    llm_ok: bool,
) -> str:
    """Build a human-readable markdown report."""
    lines = ["# VzPz Report", ""]

    if not llm_ok:
        if matching and not matching.get("parse_ok"):
            model = matching.get("model", "?")
            lines.append(f"> Matcher ({model}) did not return parseable JSON — showing classifier-only view.")
        else:
            lines.append("> LLM matching unavailable — showing classifier-only view.")
        lines.append("")

    # Requirements table: one row per requirement, LLM-driven when available.
    req_to_copy: dict[str, dict] = {c["requirement"]: c for c in copied_files}

    lines.append("## Requirements")
    lines.append("")
    lines.append("| Requirement | Status | Original File | Report File |")
    lines.append("|---|---|---|---|")
    for doc in requirements_data.get("documents", []):
        name = doc["name"]
        match = req_to_copy.get(name)
        if match:
            status = "satisfied"
            extras = match["extra_candidates"]
            if extras:
                status = f"satisfied ({len(extras)} other candidate(s) — see Conflicts)"
            lines.append(f"| {name} | {status} | {match['original']} | {match['new_name']} |")
        else:
            lines.append(f"| {name} | missing | — | — |")
    lines.append("")

    lines.extend(_build_matching_section(matching, llm_ok))

    # Unmatched documents: files not referenced by the LLM (or not copied, in fallback mode).
    used_original_names = {c["original"] for c in copied_files}
    if llm_ok and matching:
        for c in matching["result"].get("conflicts_resolved", []) or []:
            if isinstance(c, dict) and c.get("chosen_file"):
                used_original_names.add(Path(str(c["chosen_file"])).name)

    unmatched = [r for r in file_results if Path(r["path"]).name not in used_original_names]
    any_errors = any(r.get("error") for r in unmatched)

    lines.append("## Unmatched Documents")
    lines.append("")
    if unmatched:
        if any_errors:
            lines.append("| File | Classification | Error |")
            lines.append("|---|---|---|")
            for r in unmatched:
                err = (r.get("error") or "").splitlines()[0].strip() if r.get("error") else ""
                err = err.replace("|", "\\|")
                lines.append(f"| {Path(r['path']).name} | {r['classification']} | {err} |")
        else:
            lines.append("| File | Classification |")
            lines.append("|---|---|")
            for r in unmatched:
                lines.append(f"| {Path(r['path']).name} | {r['classification']} |")
    else:
        lines.append("None")
    lines.append("")

    return "\n".join(lines)


def _render_entry(entry) -> str:
    """Render a conflict_resolved / validation_warning entry as readable markdown."""
    if isinstance(entry, str):
        return entry
    if not isinstance(entry, dict):
        return str(entry)

    if "requirement" in entry and ("description" in entry or "chosen_file" in entry):
        req = entry["requirement"]
        desc = entry.get("description", "")
        chosen = entry.get("chosen_file")
        parts = [f"**{req}**"]
        if desc:
            parts.append(f": {desc}")
        if chosen:
            parts.append(f" (chosen: {Path(str(chosen)).name})")
        return "".join(parts)

    if "file" in entry and "reason" in entry:
        return f"**{Path(str(entry['file'])).name}**: {entry['reason']}"

    return ", ".join(f"{k}: {v}" for k, v in entry.items())


def _build_matching_section(matching: dict | None, llm_ok: bool) -> list[str]:
    """Render the LLM matching output as markdown. Empty if matching is absent/failed."""
    if not matching or not llm_ok:
        return []

    result = matching["result"]
    model = matching.get("model", "?")
    lines = ["## Matching (LLM)", "", f"_Model: {model}_", ""]

    matched = result.get("matched", []) or []
    lines.append(f"### Matched ({len(matched)})")
    lines.append("")
    if matched:
        lines.append("| Requirement | File | Reason |")
        lines.append("|---|---|---|")
        for m in matched:
            if not isinstance(m, dict):
                continue
            file_name = Path(str(m.get("file", ""))).name or "—"
            reason = (m.get("reason") or "").replace("|", "\\|").strip() or "—"
            lines.append(f"| {m.get('requirement', '—')} | {file_name} | {reason} |")
    else:
        lines.append("None")
    lines.append("")

    matched_reqs = {m.get("requirement") for m in matched if isinstance(m, dict)}
    missing = [m for m in (result.get("missing", []) or []) if m not in matched_reqs]
    lines.append(f"### Missing ({len(missing)})")
    lines.append("")
    if missing:
        for m in missing:
            lines.append(f"- {m}")
    else:
        lines.append("None")
    lines.append("")

    conflicts = result.get("conflicts_resolved", []) or []
    lines.append(f"### Conflicts Resolved ({len(conflicts)})")
    lines.append("")
    if conflicts:
        for c in conflicts:
            lines.append(f"- {_render_entry(c)}")
    else:
        lines.append("None")
    lines.append("")

    warnings = result.get("validation_warnings", []) or []
    lines.append(f"### Validation Warnings ({len(warnings)})")
    lines.append("")
    if warnings:
        for w in warnings:
            lines.append(f"- {_render_entry(w)}")
    else:
        lines.append("None")
    lines.append("")

    return lines
