import logging
from datetime import datetime
from pathlib import Path

import typer

app = typer.Typer(help="Veasy Peasy — local document scanner for visa applications")


@app.command()
def scan(
    folder: Path = typer.Argument(..., help="Folder containing documents to scan"),
    requirements: Path = typer.Option(..., help="Path to requirements YAML file"),
    output_name: str = typer.Option("summary.json", help="Output filename"),
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

    classify, discover, ocr_image, try_passport, extract_pdf, load_requirements, build_summary, write_summary = _load_pipeline()

    started_at = datetime.now()

    requirements_data = load_requirements(requirements)
    log.info("Loaded requirements: %s", requirements_data["visa_type"])

    files = discover(folder, skip_filename=output_name)
    typer.echo(f"Scanning {len(files)} document(s) in {folder}...")

    file_results = []
    for i, path in enumerate(files, 1):
        typer.echo(f"  [{i}/{len(files)}] {path.name}...", nl=False)
        result = _process_file(path, try_passport, extract_pdf, ocr_image, classify, log)
        typer.echo(f" {result['classification']}")
        file_results.append(result)

    finished_at = datetime.now()
    summary = build_summary(folder, requirements_data, file_results, started_at, finished_at)
    out_path = write_summary(folder, summary, output_name)
    typer.echo(f"Summary written to {out_path}")


def _load_pipeline():
    """Import heavy modules lazily so --help stays fast."""
    from veasy_peasy.classifier import classify
    from veasy_peasy.discovery import discover
    from veasy_peasy.extractors.ocr import ocr_image
    from veasy_peasy.extractors.passport import try_passport
    from veasy_peasy.extractors.pdf import extract_pdf
    from veasy_peasy.requirements import load_requirements
    from veasy_peasy.summary import build_summary, write_summary

    return classify, discover, ocr_image, try_passport, extract_pdf, load_requirements, build_summary, write_summary


def _process_file(path, try_passport, extract_pdf, ocr_image, classify, log):
    """Extract and classify a single file. Errors are captured, never raised."""
    ext = path.suffix.lower()
    result = {
        "path": str(path.resolve()),
        "ext": ext,
        "classification": "unknown",
        "extracted_fields": {},
        "text_excerpt": "",
        "text_length": 0,
        "error": None,
    }

    try:
        # Try MRZ extraction — useful structured data, but not a classification
        passport_data = try_passport(path)
        has_mrz = passport_data is not None
        mrz_type = ""
        if has_mrz:
            result["extracted_fields"] = passport_data
            mrz_type = passport_data.get("mrz_type", "")
            log.debug("  %s: MRZ detected (type=%s)", path.name, mrz_type)

        # Always extract text for classification
        if ext == ".pdf":
            text = extract_pdf(path)
        else:
            text = ocr_image(path)

        result["text_excerpt"] = text[:500]
        result["text_length"] = len(text)
        result["classification"] = classify(text, has_mrz=has_mrz, mrz_type=mrz_type)
        log.debug("  %s → %s", path.name, result["classification"])

    except Exception as e:
        result["error"] = str(e)
        log.error("  %s → error: %s", path.name, e)

    return result
