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
    """Create a report folder with classified file copies, summary.json, and report.md."""
    timestamp = started_at.strftime("%d-%m-%H-%M")
    report_dir = folder / f"VzPz_Report_{timestamp}"
    report_dir.mkdir(exist_ok=True)

    copied_files = _copy_classified_files(report_dir, file_results)

    write_summary(report_dir, summary_data)

    md = _build_markdown(requirements_data, file_results, copied_files, summary_data.get("matching"))
    (report_dir / "report.md").write_text(md)

    return report_dir


def _copy_classified_files(report_dir: Path, file_results: list[dict]) -> list[dict]:
    """Copy non-unknown files into report_dir with classification-based names."""
    # Count classifications to decide naming strategy
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
            expiry = r.get("extracted_fields", {}).get("expiry")
            if expiry and len(expiry) == 6:
                # DDMMYY -> YYYYMMDD
                dd, mm, yy = expiry[:2], expiry[2:4], expiry[4:6]
                yyyy = f"20{yy}" if int(yy) < 80 else f"19{yy}"
                new_name = f"{cls}_exp_{yyyy}{mm}{dd}{ext}"
            else:
                cls_seen[cls] += 1
                new_name = f"{cls}_{cls_seen[cls]}{ext}"

        shutil.copy2(src, report_dir / new_name)
        copied.append({"original": src.name, "new_name": new_name, "classification": cls})

    return copied


def _build_markdown(
    requirements_data: dict,
    file_results: list[dict],
    copied_files: list[dict],
    matching: dict | None = None,
) -> str:
    """Build a human-readable markdown report."""
    lines = ["# VzPz Report", ""]

    # Build classification -> copied files mapping
    cls_to_copies: dict[str, list[dict]] = {}
    for c in copied_files:
        cls_to_copies.setdefault(c["classification"], []).append(c)

    # Requirements table
    lines.append("## Requirements")
    lines.append("")
    lines.append("| Requirement | Status | Original File | Report File |")
    lines.append("|---|---|---|---|")
    for doc in requirements_data.get("documents", []):
        name = doc["name"]
        matches = cls_to_copies.get(name, [])
        if matches:
            for m in matches:
                lines.append(f"| {name} | satisfied | {m['original']} | {m['new_name']} |")
        else:
            lines.append(f"| {name} | missing | — | — |")
    lines.append("")

    # LLM matching (matched / missing / conflicts / warnings)
    lines.extend(_build_matching_section(matching))

    # Unmatched documents: files not copied into the report folder
    copied_originals = {c["original"] for c in copied_files}
    unmatched = [r for r in file_results if Path(r["path"]).name not in copied_originals]
    lines.append("## Unmatched Documents")
    lines.append("")
    if unmatched:
        lines.append("| File | Classification |")
        lines.append("|---|---|")
        for r in unmatched:
            lines.append(f"| {Path(r['path']).name} | {r['classification']} |")
    else:
        lines.append("None")
    lines.append("")

    return "\n".join(lines)


def _build_matching_section(matching: dict | None) -> list[str]:
    """Render the LLM matching output as markdown. Empty list if matching is absent/failed."""
    if not matching:
        return []
    lines = ["## Matching (LLM)", ""]
    if not matching.get("parse_ok") or not matching.get("result"):
        model = matching.get("model", "?")
        lines.append(f"_Matcher ({model}) did not return parseable JSON._")
        lines.append("")
        return lines

    result = matching["result"]
    model = matching.get("model", "?")
    lines.append(f"_Model: {model}_")
    lines.append("")

    matched = result.get("matched", [])
    lines.append(f"### Matched ({len(matched)})")
    lines.append("")
    if matched:
        lines.append("| Requirement | File | Reason |")
        lines.append("|---|---|---|")
        for m in matched:
            file_name = Path(m.get("file", "")).name or "—"
            reason = (m.get("reason") or "").replace("|", "\\|")
            lines.append(f"| {m.get('requirement', '—')} | {file_name} | {reason} |")
    else:
        lines.append("None")
    lines.append("")

    missing = result.get("missing", [])
    lines.append(f"### Missing ({len(missing)})")
    lines.append("")
    if missing:
        for m in missing:
            lines.append(f"- {m}")
    else:
        lines.append("None")
    lines.append("")

    conflicts = result.get("conflicts_resolved", [])
    lines.append(f"### Conflicts Resolved ({len(conflicts)})")
    lines.append("")
    if conflicts:
        for c in conflicts:
            lines.append(f"- {c}")
    else:
        lines.append("None")
    lines.append("")

    warnings = result.get("validation_warnings", [])
    lines.append(f"### Validation Warnings ({len(warnings)})")
    lines.append("")
    if warnings:
        for w in warnings:
            lines.append(f"- {w}")
    else:
        lines.append("None")
    lines.append("")

    return lines
