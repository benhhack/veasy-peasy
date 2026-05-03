"""Tool implementations exposed to the LLM orchestrator.

Each tool is a plain Python function that takes JSON-serialisable args and
returns a JSON-serialisable result. `TOOL_SCHEMAS` mirrors the Ollama
tool-calling format (`/api/chat` with `tools=[...]`).
"""

import json
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Callable

from veasy_peasy.classifier import RULES


# ---------------------------------------------------------------------------
# Tool functions
# ---------------------------------------------------------------------------

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


# ---------------------------------------------------------------------------
# Tool dataclass + registry
# ---------------------------------------------------------------------------

@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: dict           # JSON schema for the tool's parameters
    fn: Callable[..., dict]
    # When True, dispatch may merge results into state["artifacts"]. Per-tool merge
    # logic in ToolRegistry.dispatch is name-dispatched — adding a new artifact-
    # producing tool requires updating dispatch as well as setting this flag.
    writes_artifacts: bool = False


def _excerpt(result) -> str:
    """Compact 300-char representation of a tool result for timing records."""
    if isinstance(result, dict):
        if "text" in result:
            return (result["text"] or "")[:300]
        return json.dumps(result, default=str)[:300]
    return str(result)[:300]


class ToolRegistry:
    def __init__(self, tools: list[Tool]):
        self._tools = tools
        self._by_name: dict[str, Tool] = {t.name: t for t in tools}

    def schemas(self) -> list[dict]:
        """Return tool schemas in Ollama tool-calling format (type=function)."""
        return [
            {
                "type": "function",
                "function": {
                    "name": t.name,
                    "description": t.description,
                    "parameters": t.params,
                },
            }
            for t in self._tools
        ]

    def dispatch(self, name: str, args: dict, state: dict) -> dict:
        """Run the tool, record timing into state['tool_timings'],
        merge artifacts into state['artifacts'] for writes_artifacts=True tools.
        Returns the tool's result dict, or {'error': '...'} on bad name/args/raises.
        Never raises.
        """
        state.setdefault("tool_timings", [])
        state.setdefault("artifacts", {})

        t0 = time.time()
        tool = self._by_name.get(name)

        if tool is None:
            result = {"error": f"unknown tool: {name}"}
        else:
            try:
                result = tool.fn(**args)
            except TypeError as e:
                result = {"error": f"bad args for {name}: {e}"}
            except Exception as e:
                result = {"error": f"{name} raised: {e}"}

        elapsed = round(time.time() - t0, 3)

        state["tool_timings"].append({
            "round": state.get("_current_round", 0),
            "name": name,
            "args": dict(args),
            "elapsed_s": elapsed,
            "result_excerpt": _excerpt(result),
        })

        # Merge artifacts for writes_artifacts tools when result is clean (no error).
        if (
            tool is not None
            and tool.writes_artifacts
            and isinstance(result, dict)
            and "error" not in result
        ):
            artifacts = state["artifacts"]
            # Text-producing tools: only cache if nothing cached yet.
            if name in {"extract_pdf_text", "ocr_image"} and result.get("text"):
                if not artifacts.get("text_excerpt"):
                    artifacts["text_excerpt"] = result["text"][:500]
                    artifacts["text_length"] = result.get("text_length", len(result["text"]))
            # MRZ tool: always update extracted_fields.
            if name == "check_mrz" and result.get("mrz"):
                artifacts["extracted_fields"] = result["mrz"]

        return result


# ---------------------------------------------------------------------------
# Module-level registry (single source of truth)
# ---------------------------------------------------------------------------

TOOL_REGISTRY = ToolRegistry([
    Tool(
        name="extract_pdf_text",
        description="Extract embedded text from a PDF file. Use this first for .pdf files. Prefer first_page_only=true to keep context small.",
        params={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the PDF file."},
                "first_page_only": {"type": "boolean", "description": "If true, read only the first page."},
            },
            "required": ["path"],
        },
        fn=extract_pdf_text,
        writes_artifacts=True,
    ),
    Tool(
        name="ocr_image",
        description="OCR an image (.jpg/.png) or an image-only PDF. Use when extract_pdf_text returns little or no text.",
        params={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the image or PDF file."},
            },
            "required": ["path"],
        },
        fn=ocr_image_tool,
        writes_artifacts=True,
    ),
    Tool(
        name="keyword_score",
        description="Count keyword hits per built-in category for a chunk of text. Cheap sanity check on ambiguous documents.",
        params={
            "type": "object",
            "properties": {
                "text": {"type": "string", "description": "Text to score."},
            },
            "required": ["text"],
        },
        fn=keyword_score,
        writes_artifacts=False,
    ),
    Tool(
        name="check_mrz",
        description="Run MRZ (machine-readable zone) extraction. Returns {mrz: null} if no MRZ is detected.",
        params={
            "type": "object",
            "properties": {
                "path": {"type": "string", "description": "Absolute path to the image or PDF."},
            },
            "required": ["path"],
        },
        fn=check_mrz,
        writes_artifacts=True,
    ),
])


# ---------------------------------------------------------------------------
# Backward-compat shims — orchestrator still imports these today (Task 6 removes them)
# ---------------------------------------------------------------------------

TOOL_SCHEMAS: list[dict] = TOOL_REGISTRY.schemas()
TOOL_DISPATCH: dict[str, Callable] = {tool.name: tool.fn for tool in TOOL_REGISTRY._tools}
