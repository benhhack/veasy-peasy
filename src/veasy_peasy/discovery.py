from pathlib import Path

SUPPORTED_EXTENSIONS = {".pdf", ".png", ".jpg", ".jpeg"}


def discover(folder: Path, skip_filename: str = "summary.json") -> list[Path]:
    """Recursively find supported document files, skipping hidden files and output."""
    results = []
    for path in sorted(folder.rglob("*")):
        if any(part.startswith(".") for part in path.parts):
            continue
        if path.name == skip_filename:
            continue
        if path.is_file() and path.suffix.lower() in SUPPORTED_EXTENSIONS:
            results.append(path)
    return results
