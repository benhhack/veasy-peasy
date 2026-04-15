import logging
from pathlib import Path

logger = logging.getLogger(__name__)

_reader = None


def get_reader():
    """Lazily initialize the EasyOCR reader (downloads models on first use)."""
    global _reader
    if _reader is None:
        import typer
        import torch
        import easyocr

        model_dir = Path.home() / ".EasyOCR" / "model"
        if not model_dir.exists() or not any(model_dir.iterdir()):
            typer.echo("Downloading OCR models (first run only, this may take a minute)...")

        if torch.backends.mps.is_available():
            logger.info("EasyOCR using MPS (Apple Silicon GPU)")
        else:
            logger.warning("MPS not available — EasyOCR falling back to CPU")

        _reader = easyocr.Reader(["en"], gpu=True)
    return _reader


def ocr_image(path: Path) -> str:
    """Extract text from an image file using EasyOCR."""
    reader = get_reader()
    results = reader.readtext(str(path))
    return "\n".join(text for _, text, _ in results)
