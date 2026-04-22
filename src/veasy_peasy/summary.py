import json
from datetime import datetime
from pathlib import Path

from veasy_peasy import __version__


def build_summary(
    folder: Path,
    requirements_data: dict,
    file_results: list[dict],
    started_at: datetime,
    finished_at: datetime,
    match_result: dict | None = None,
) -> dict:
    """Build the summary dict. Separate from write so Day 2 can reuse."""
    matching = None
    if match_result is not None:
        matching = {
            "model": match_result.get("model"),
            "parse_ok": match_result.get("parse_ok", False),
            "wall_time_s": match_result.get("wall_time_s", 0),
            "result": match_result.get("result"),
        }
    # Orchestrator traces live as standalone files in the report dir — drop them here.
    slim_files = [{k: v for k, v in r.items() if k != "trace"} for r in file_results]
    return {
        "tool": "veasy-peasy",
        "version": __version__,
        "run": {
            "started_at": started_at.isoformat(),
            "finished_at": finished_at.isoformat(),
            "folder": str(folder.resolve()),
            "file_count": len(file_results),
        },
        "requirements_loaded": requirements_data,
        "matching": matching,
        "files": slim_files,
    }


def write_summary(folder: Path, data: dict, output_name: str = "summary.json") -> Path:
    """Write summary JSON to the target folder."""
    out = folder / output_name
    out.write_text(json.dumps(data, indent=2, ensure_ascii=False) + "\n")
    return out
