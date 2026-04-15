import logging
import tempfile
from pathlib import Path

logger = logging.getLogger(__name__)


def extract_pdf(path: Path) -> str:
    """Extract text from a PDF. Falls back to OCR for image-only PDFs."""
    import fitz

    doc = fitz.open(str(path))
    text_parts = []
    for page in doc:
        text_parts.append(page.get_text())
    text = "\n".join(text_parts).strip()

    if len(text) < 20:
        logger.info("PDF %s appears image-only, falling back to OCR", path.name)
        from veasy_peasy.extractors.ocr import ocr_image

        ocr_parts = []
        for page in doc:
            pix = page.get_pixmap()
            with tempfile.NamedTemporaryFile(suffix=".png", delete=False) as tmp:
                pix.save(tmp.name)
                ocr_parts.append(ocr_image(Path(tmp.name)))
        text = "\n".join(ocr_parts).strip()

    doc.close()
    return text
