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

    md = _build_markdown(requirements_data, file_results, copied_files)
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
    requirements_data: dict, file_results: list[dict], copied_files: list[dict]
) -> str:
    """Build a human-readable markdown report."""
    lines = ["# VzPz Report", ""]

    lines.append("## Documents Searched")
    for r in file_results:
        lines.append(f"- **{Path(r['path']).name}** — {r['classification']}")
    lines.append("")

    lines.append("## Documents Found")
    for c in copied_files:
        lines.append(f"- **{c['new_name']}** (was {c['original']})")
    lines.append("")

    unknowns = [r for r in file_results if r["classification"] == "unknown"]
    lines.append("## Unknown Documents")
    if unknowns:
        for r in unknowns:
            lines.append(f"- {Path(r['path']).name}")
    else:
        lines.append("- None")
    lines.append("")

    found_cls = {r["classification"] for r in file_results if r["classification"] != "unknown"}
    lines.append("## Requirements Status")
    for doc in requirements_data.get("documents", []):
        name = doc["name"]
        status = "satisfied" if name in found_cls else "missing"
        lines.append(f"- **{name}**: {status}")
    lines.append("")

    return "\n".join(lines)
