"""Tool implementations exposed to the LLM orchestrator.

Each tool is a plain Python function that takes JSON-serialisable args and
returns a JSON-serialisable result. `TOOL_SCHEMAS` mirrors the Ollama
tool-calling format (`/api/chat` with `tools=[...]`).
"""

from pathlib import Path

from veasy_peasy.classifier import RULES


def extract_pdf_text(path: str, first_page_only: bool = True) -> dict:
    """Extract embedded text from a PDF. Does NOT fall back to OCR."""
    import fitz

    p = Path(path)
    if not p.is_file() or p.suffix.lower() != ".pdf":
        return {"error": f"{path} is not a PDF file", "text": "", "text_length": 0}

    doc = fitz.open(str(p))
    try:
        pages = [doc[0]] if first_page_only and len(doc) > 0 else list(doc)
        text = "\n".join(page.get_text() for page in pages).strip()
    finally:
        doc.close()
    return {
        "text": text[:2000],
        "text_length": len(text),
        "page_count_read": len(pages),
    }


def ocr_image_tool(path: str) -> dict:
    """OCR an image or image-only PDF page."""
    from veasy_peasy.extractors.ocr import ocr_image
    from veasy_peasy.extractors.pdf import extract_pdf

    p = Path(path)
    if not p.is_file():
        return {"error": f"{path} not found", "text": "", "text_length": 0}

    ext = p.suffix.lower()
    if ext == ".pdf":
        text = extract_pdf(p)
    else:
        text = ocr_image(p)
    return {"text": text[:2000], "text_length": len(text)}


def keyword_score(text: str) -> dict:
    """Return per-category keyword hit counts from the built-in RULES dict."""
    tl = text.lower()
    return {
        category: sum(1 for kw in keywords if kw in tl)
        for category, keywords in RULES.items()
    }


def check_mrz(path: str) -> dict:
    """Run passporteye MRZ extraction. Returns fields or {'mrz': null}."""
    from veasy_peasy.extractors.passport import try_passport

    data = try_passport(Path(path))
    return {"mrz": data}


TOOL_SCHEMAS: list[dict] = [
    {
        "type": "function",
        "function": {
            "name": "extract_pdf_text",
            "description": "Extract embedded text from a PDF file. Use this first for .pdf files. Prefer first_page_only=true to keep context small.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the PDF file."},
                    "first_page_only": {"type": "boolean", "description": "If true, read only the first page."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "ocr_image",
            "description": "OCR an image (.jpg/.png) or an image-only PDF. Use when extract_pdf_text returns little or no text.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the image or PDF file."},
                },
                "required": ["path"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "keyword_score",
            "description": "Count keyword hits per built-in category for a chunk of text. Cheap sanity check on ambiguous documents.",
            "parameters": {
                "type": "object",
                "properties": {
                    "text": {"type": "string", "description": "Text to score."},
                },
                "required": ["text"],
            },
        },
    },
    {
        "type": "function",
        "function": {
            "name": "check_mrz",
            "description": "Run MRZ (machine-readable zone) extraction. Returns {mrz: null} if no MRZ is detected.",
            "parameters": {
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "Absolute path to the image or PDF."},
                },
                "required": ["path"],
            },
        },
    },
]


TOOL_DISPATCH = {
    "extract_pdf_text": extract_pdf_text,
    "ocr_image": ocr_image_tool,
    "keyword_score": keyword_score,
    "check_mrz": check_mrz,
}
