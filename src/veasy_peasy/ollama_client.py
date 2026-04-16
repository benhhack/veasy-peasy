"""Thin wrapper around the Ollama HTTP API for model management and generation."""

import json
import logging
import time
from urllib import request, error

logger = logging.getLogger(__name__)

OLLAMA_BASE = "http://localhost:11434"


def _post(path: str, body: dict, stream: bool = False, timeout: int = 300) -> dict:
    """Send a POST request to the Ollama API and return the parsed JSON response."""
    data = json.dumps(body).encode()
    req = request.Request(
        f"{OLLAMA_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        if stream:
            # For streaming endpoints, collect the last JSON line (the final response)
            last_line = None
            for line in resp:
                line = line.strip()
                if line:
                    last_line = line
            return json.loads(last_line) if last_line else {}
        return json.loads(resp.read())


def _post_no_stream(path: str, body: dict, timeout: int = 300) -> dict:
    """POST that expects a single JSON response (non-streaming)."""
    data = json.dumps(body).encode()
    req = request.Request(
        f"{OLLAMA_BASE}{path}",
        data=data,
        headers={"Content-Type": "application/json"},
        method="POST",
    )
    with request.urlopen(req, timeout=timeout) as resp:
        return json.loads(resp.read())


def is_available() -> bool:
    """Check if the Ollama server is reachable."""
    try:
        req = request.Request(f"{OLLAMA_BASE}/api/tags")
        with request.urlopen(req, timeout=5):
            return True
    except Exception:
        return False


def pull_model(model: str) -> None:
    """Pull a model if not already present. Blocks until complete."""
    logger.info("Pulling model %s (if not cached)...", model)
    _post("/api/pull", {"name": model, "stream": False}, timeout=600)
    logger.info("Model %s ready.", model)


def load_model(model: str) -> float:
    """Load a model into memory by sending a dummy generate with keep_alive.

    Returns the time in seconds it took to load.
    """
    logger.info("Loading model %s into memory...", model)
    start = time.time()
    _post_no_stream(
        "/api/generate",
        {"model": model, "prompt": "", "keep_alive": "10m"},
        timeout=120,
    )
    elapsed = time.time() - start
    logger.info("Model %s loaded in %.1fs.", model, elapsed)
    return elapsed


def generate(model: str, prompt: str, temperature: float = 0.0) -> dict:
    """Generate a completion. Returns dict with 'response' and timing info."""
    start = time.time()
    result = _post_no_stream(
        "/api/generate",
        {
            "model": model,
            "prompt": prompt,
            "stream": False,
            "options": {"temperature": temperature},
        },
        timeout=300,
    )
    elapsed = time.time() - start
    result["wall_time_s"] = elapsed
    return result


def unload_model(model: str) -> None:
    """Unload a model from memory by setting keep_alive to 0."""
    logger.info("Unloading model %s...", model)
    _post_no_stream(
        "/api/generate",
        {"model": model, "prompt": "", "keep_alive": 0},
        timeout=30,
    )
    logger.info("Model %s unloaded.", model)
