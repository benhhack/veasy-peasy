"""Tests for the Tool dataclass, ToolRegistry, and backward-compat shims."""

import pytest

from veasy_peasy.tools import (
    Tool,
    ToolRegistry,
    TOOL_REGISTRY,
    TOOL_SCHEMAS,
    TOOL_DISPATCH,
)


# ---------------------------------------------------------------------------
# Helpers
# ---------------------------------------------------------------------------

def _make_registry(*tool_list: Tool) -> ToolRegistry:
    return ToolRegistry(list(tool_list))


def _text_tool(name: str = "fake_text") -> Tool:
    return Tool(
        name=name,
        description="fake text extractor",
        params={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        fn=lambda path: {"text": "hello world", "text_length": 11},
        writes_artifacts=True,
    )


def _mrz_tool() -> Tool:
    return Tool(
        name="check_mrz",
        description="fake mrz",
        params={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        fn=lambda path: {"mrz": {"mrz_type": "P", "name": "DOE"}},
        writes_artifacts=True,
    )


def _keyword_tool() -> Tool:
    return Tool(
        name="keyword_score",
        description="fake keyword score",
        params={"type": "object", "properties": {"text": {"type": "string"}}, "required": ["text"]},
        fn=lambda text: {"passport": 1},
        writes_artifacts=False,
    )


# ---------------------------------------------------------------------------
# 1. Tool dataclass instantiation
# ---------------------------------------------------------------------------

def test_tool_dataclass_all_fields():
    t = Tool(
        name="my_tool",
        description="does something",
        params={"type": "object", "properties": {}, "required": []},
        fn=lambda: {},
        writes_artifacts=True,
    )
    assert t.name == "my_tool"
    assert t.description == "does something"
    assert t.writes_artifacts is True


def test_tool_writes_artifacts_default_is_false():
    t = Tool(
        name="no_art",
        description="no artifacts",
        params={},
        fn=lambda: {},
    )
    assert t.writes_artifacts is False


def test_tool_is_frozen():
    t = Tool(name="x", description="y", params={}, fn=lambda: {})
    with pytest.raises((AttributeError, TypeError)):
        t.name = "z"  # type: ignore[misc]


# ---------------------------------------------------------------------------
# 2. ToolRegistry.schemas()
# ---------------------------------------------------------------------------

def test_schemas_length_and_names():
    schemas = TOOL_REGISTRY.schemas()
    assert len(schemas) == 4
    names = {s["function"]["name"] for s in schemas}
    assert names == {"extract_pdf_text", "ocr_image", "keyword_score", "check_mrz"}


def test_schemas_type_is_function():
    for s in TOOL_REGISTRY.schemas():
        assert s["type"] == "function"
        assert "function" in s
        assert "name" in s["function"]
        assert "description" in s["function"]
        assert "parameters" in s["function"]


def test_schemas_matches_tool_schemas_shim():
    # The shim must be structurally identical to a fresh call.
    assert TOOL_SCHEMAS == TOOL_REGISTRY.schemas()


# ---------------------------------------------------------------------------
# 3. dispatch happy path (mocked fn)
# ---------------------------------------------------------------------------

def test_dispatch_happy_path():
    reg = _make_registry(_text_tool("extract_pdf_text"))
    state: dict = {}
    result = reg.dispatch("extract_pdf_text", {"path": "/fake.pdf"}, state)
    assert result == {"text": "hello world", "text_length": 11}


# ---------------------------------------------------------------------------
# 4. dispatch records timing
# ---------------------------------------------------------------------------

def test_dispatch_records_timing():
    reg = _make_registry(_text_tool("extract_pdf_text"))
    state: dict = {}
    reg.dispatch("extract_pdf_text", {"path": "/fake.pdf"}, state)

    assert len(state["tool_timings"]) == 1
    entry = state["tool_timings"][0]
    assert entry["name"] == "extract_pdf_text"
    assert entry["args"] == {"path": "/fake.pdf"}
    assert entry["elapsed_s"] >= 0
    assert isinstance(entry["result_excerpt"], str)
    assert len(entry["result_excerpt"]) <= 300


# ---------------------------------------------------------------------------
# 5. dispatch merges text artifact (empty state)
# ---------------------------------------------------------------------------

def test_dispatch_merges_text_artifact_when_empty():
    reg = _make_registry(_text_tool("extract_pdf_text"))
    state: dict = {}
    reg.dispatch("extract_pdf_text", {"path": "/fake.pdf"}, state)

    assert state["artifacts"]["text_excerpt"] == "hello world"
    assert state["artifacts"]["text_length"] == 11


def test_dispatch_merges_text_artifact_for_ocr_image():
    reg = _make_registry(_text_tool("ocr_image"))
    state: dict = {}
    reg.dispatch("ocr_image", {"path": "/fake.jpg"}, state)

    assert state["artifacts"]["text_excerpt"] == "hello world"
    assert state["artifacts"]["text_length"] == 11


# ---------------------------------------------------------------------------
# 6. dispatch does NOT overwrite already-cached text_excerpt
# ---------------------------------------------------------------------------

def test_dispatch_does_not_overwrite_cached_text_excerpt():
    reg = _make_registry(_text_tool("extract_pdf_text"))
    state: dict = {"artifacts": {"text_excerpt": "first cached text", "text_length": 17}}
    reg.dispatch("extract_pdf_text", {"path": "/fake.pdf"}, state)

    assert state["artifacts"]["text_excerpt"] == "first cached text"
    assert state["artifacts"]["text_length"] == 17


# ---------------------------------------------------------------------------
# 7. dispatch merges MRZ artifact
# ---------------------------------------------------------------------------

def test_dispatch_merges_mrz_artifact():
    reg = _make_registry(_mrz_tool())
    state: dict = {}
    reg.dispatch("check_mrz", {"path": "/fake.jpg"}, state)

    assert state["artifacts"]["extracted_fields"] == {"mrz_type": "P", "name": "DOE"}


# ---------------------------------------------------------------------------
# 8. dispatch skips artifact merge when result has error
# ---------------------------------------------------------------------------

def test_dispatch_skips_artifact_merge_on_error():
    error_tool = Tool(
        name="extract_pdf_text",
        description="always errors",
        params={"type": "object", "properties": {"path": {"type": "string"}}, "required": ["path"]},
        fn=lambda path: {"error": "something broke", "text": "", "text_length": 0},
        writes_artifacts=True,
    )
    reg = _make_registry(error_tool)
    state: dict = {}
    reg.dispatch("extract_pdf_text", {"path": "/bad.pdf"}, state)

    # artifacts dict exists but text_excerpt was not written
    assert "text_excerpt" not in state["artifacts"]


# ---------------------------------------------------------------------------
# 9. dispatch with unknown tool name
# ---------------------------------------------------------------------------

def test_dispatch_unknown_tool_returns_error_dict():
    reg = _make_registry(_text_tool())
    state: dict = {}
    result = reg.dispatch("foo", {}, state)

    assert result == {"error": "unknown tool: foo"}
    # Still records a timing entry.
    assert len(state["tool_timings"]) == 1
    assert "unknown tool: foo" in state["tool_timings"][0]["result_excerpt"]


def test_dispatch_unknown_tool_never_raises():
    reg = _make_registry()
    state: dict = {}
    result = reg.dispatch("nonexistent", {"x": 1}, state)
    assert "error" in result


# ---------------------------------------------------------------------------
# 10. dispatch with bad args (missing required arg)
# ---------------------------------------------------------------------------

def test_dispatch_bad_args_returns_error_dict():
    reg = _make_registry(_text_tool("extract_pdf_text"))
    state: dict = {}
    # extract_pdf_text requires `path`; pass nothing.
    result = reg.dispatch("extract_pdf_text", {}, state)

    assert "error" in result
    assert "bad args for extract_pdf_text" in result["error"]


def test_dispatch_bad_args_never_raises():
    reg = _make_registry(_text_tool("extract_pdf_text"))
    state: dict = {}
    result = reg.dispatch("extract_pdf_text", {}, state)
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 11. dispatch when fn raises
# ---------------------------------------------------------------------------

def test_dispatch_fn_raises_returns_error_dict():
    exploding = Tool(
        name="exploder",
        description="blows up",
        params={},
        fn=lambda: (_ for _ in ()).throw(RuntimeError("kaboom")),
        writes_artifacts=False,
    )
    reg = _make_registry(exploding)
    state: dict = {}
    result = reg.dispatch("exploder", {}, state)

    assert "error" in result
    assert "exploder raised" in result["error"]
    assert "kaboom" in result["error"]


def test_dispatch_fn_raises_never_raises():
    exploding = Tool(
        name="exploder",
        description="blows up",
        params={},
        fn=lambda: (_ for _ in ()).throw(ValueError("boom")),
        writes_artifacts=False,
    )
    reg = _make_registry(exploding)
    result = reg.dispatch("exploder", {}, {})
    assert isinstance(result, dict)


# ---------------------------------------------------------------------------
# 12. dispatch round tracking
# ---------------------------------------------------------------------------

def test_dispatch_round_tracking():
    reg = _make_registry(_keyword_tool())
    state: dict = {"_current_round": 3}
    reg.dispatch("keyword_score", {"text": "hello"}, state)

    assert state["tool_timings"][0]["round"] == 3


def test_dispatch_round_defaults_to_zero():
    reg = _make_registry(_keyword_tool())
    state: dict = {}
    reg.dispatch("keyword_score", {"text": "hi"}, state)

    assert state["tool_timings"][0]["round"] == 0


# ---------------------------------------------------------------------------
# 13. dispatch initialises missing state keys
# ---------------------------------------------------------------------------

def test_dispatch_initialises_empty_state():
    reg = _make_registry(_keyword_tool())
    state: dict = {}
    reg.dispatch("keyword_score", {"text": "hi"}, state)

    assert "tool_timings" in state
    assert "artifacts" in state


# ---------------------------------------------------------------------------
# 14. Backward-compat: TOOL_SCHEMAS
# ---------------------------------------------------------------------------

def test_tool_schemas_exists_and_has_4_entries():
    assert isinstance(TOOL_SCHEMAS, list)
    assert len(TOOL_SCHEMAS) == 4


def test_tool_schemas_names():
    names = {s["function"]["name"] for s in TOOL_SCHEMAS}
    assert names == {"extract_pdf_text", "ocr_image", "keyword_score", "check_mrz"}


# ---------------------------------------------------------------------------
# 15. Backward-compat: TOOL_DISPATCH
# ---------------------------------------------------------------------------

def test_tool_dispatch_exists_and_has_4_keys():
    assert isinstance(TOOL_DISPATCH, dict)
    assert len(TOOL_DISPATCH) == 4


def test_tool_dispatch_keys():
    assert set(TOOL_DISPATCH.keys()) == {"extract_pdf_text", "ocr_image", "keyword_score", "check_mrz"}


def test_tool_dispatch_values_are_callable():
    for name, fn in TOOL_DISPATCH.items():
        assert callable(fn), f"TOOL_DISPATCH[{name!r}] is not callable"
