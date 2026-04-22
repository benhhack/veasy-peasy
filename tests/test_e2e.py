"""End-to-end smoke test for the scan pipeline.

Skipped automatically if Ollama is not reachable or qwen2.5:3b is not installed.
Otherwise runs the full pipeline against the committed example_documents/
fixtures and verifies the matcher output lands in summary.json.
"""
import json
import shutil
from pathlib import Path

import pytest
from typer.testing import CliRunner

from veasy_peasy.cli import app
from veasy_peasy.ollama_client import is_available, list_models

MODEL = "qwen2.5:3b"
FIXTURES = Path(__file__).resolve().parent.parent / "example_documents"
REQUIREMENTS = Path(__file__).resolve().parent.parent / "example_requirements" / "visa_schengen.yaml"


def _ollama_ready() -> bool:
    if not is_available():
        return False
    installed = list_models()
    return any(m == MODEL or m.startswith(f"{MODEL}:") for m in installed)


@pytest.mark.skipif(not _ollama_ready(), reason="Ollama or required model not available")
def test_scan_end_to_end(tmp_path: Path) -> None:
    scan_dir = tmp_path / "docs"
    scan_dir.mkdir()
    for pdf in FIXTURES.glob("*.pdf"):
        shutil.copy2(pdf, scan_dir / pdf.name)

    runner = CliRunner()
    result = runner.invoke(
        app,
        ["scan", str(scan_dir), "--requirements", str(REQUIREMENTS)],
    )
    assert result.exit_code == 0, result.output

    report_dirs = list(scan_dir.glob("VzPz_Report_*"))
    assert len(report_dirs) == 1, f"expected one report dir, got {report_dirs}"

    summary = json.loads((report_dirs[0] / "summary.json").read_text())
    matching = summary["matching"]
    assert matching is not None, "matching section should be populated"
    assert matching["parse_ok"], f"matcher response failed to parse: {matching}"
    assert matching["result"] is not None
    assert isinstance(matching["result"].get("matched"), list)
    assert isinstance(matching["result"].get("missing"), list)

    report_md = (report_dirs[0] / "report.md").read_text()
    assert "## Matching (LLM)" in report_md
