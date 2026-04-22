import logging
import warnings
from datetime import datetime
from pathlib import Path

import typer

# Upstream libs (passporteye → skimage, torch) emit deprecation/user warnings that flood stdout
# during scans. Silence them at import time; actual errors still go through logging.
warnings.filterwarnings("ignore", category=FutureWarning)
warnings.filterwarnings("ignore", category=UserWarning, module="torch")

app = typer.Typer(help="Veasy Peasy — local document scanner for visa applications")


@app.command()
def scan(
    folder: Path = typer.Argument(..., help="Folder containing documents to scan"),
    requirements: Path = typer.Option(..., help="Path to requirements YAML file"),
    output_name: str = typer.Option("summary.json", help="Output filename"),
    model: str = typer.Option("qwen2.5:3b", help="Ollama model used for classification and matching"),
    verbose: bool = typer.Option(False, "--verbose", "-v", help="Enable verbose logging"),
) -> None:
    """Scan a folder of documents, extract data, classify, and write summary."""
    logging.basicConfig(
        level=logging.DEBUG if verbose else logging.INFO,
        format="%(levelname)s: %(message)s",
    )
    log = logging.getLogger(__name__)

    if not folder.is_dir():
        typer.echo(f"Error: {folder} is not a directory", err=True)
        raise typer.Exit(1)
    if not requirements.is_file():
        typer.echo(f"Error: {requirements} is not a file", err=True)
        raise typer.Exit(1)

    _preflight_ollama(model)

    classify_document, discover, load_requirements, build_summary, assemble_output, match = _load_pipeline()

    started_at = datetime.now()

    requirements_data = load_requirements(requirements)
    log.info("Loaded requirements: %s", requirements_data["visa_type"])

    files = discover(folder, skip_filename=output_name)
    typer.echo(f"Scanning {len(files)} document(s) in {folder}...")

    file_results = []
    for i, path in enumerate(files, 1):
        typer.echo(f"  [{i}/{len(files)}] {path.name}...", nl=False)
        result = classify_document(path, requirements_data, model)
        if result["error"]:
            short = result["error"].splitlines()[0].strip()
            typer.echo(f" error: {short[:80]}")
        else:
            decision = result["trace"]["decision_path"]
            typer.echo(f" {result['classification']} ({decision})")
        file_results.append(result)

    typer.echo(f"Matching against {len(requirements_data['documents'])} requirement(s) with {model}...")
    match_result = match(model, requirements_data, file_results)
    if not match_result["parse_ok"]:
        log.warning("LLM response could not be parsed as JSON — matching section will be empty")

    finished_at = datetime.now()
    summary = build_summary(folder, requirements_data, file_results, started_at, finished_at, match_result)
    report_dir = assemble_output(folder, file_results, requirements_data, summary, started_at)
    typer.echo(f"Report written to {report_dir}")


def _load_pipeline():
    """Import heavy modules lazily so --help stays fast."""
    from veasy_peasy.discovery import discover
    from veasy_peasy.requirements import load_requirements
    from veasy_peasy.output import assemble_output
    from veasy_peasy.summary import build_summary
    from veasy_peasy.matcher import match
    from veasy_peasy.orchestrator import classify_document

    return classify_document, discover, load_requirements, build_summary, assemble_output, match


def _preflight_ollama(model: str) -> None:
    """Verify Ollama is running and the requested model is pulled. Exit with remediation if not."""
    from veasy_peasy.ollama_client import is_available, list_models

    if not is_available():
        typer.echo(
            "Error: Ollama is not reachable at http://localhost:11434.\n"
            "  Start it with: ollama serve",
            err=True,
        )
        raise typer.Exit(1)

    installed = list_models()
    # Ollama tags include the variant (e.g. "qwen2.5:3b"); allow prefix match for convenience
    if not any(m == model or m.startswith(f"{model}:") for m in installed):
        typer.echo(
            f"Error: model '{model}' is not installed in Ollama.\n"
            f"  Pull it with: ollama pull {model}",
            err=True,
        )
        raise typer.Exit(1)
