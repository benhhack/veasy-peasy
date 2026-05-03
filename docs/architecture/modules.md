# Modules

Design spec for the Engine-seam refactor. Each entry locks one **Module** by its **Interface** so a future Adapter (e.g. a LangGraph-based Engine) drops in without rewriting tests.

Vocabulary: see `CONTEXT.md` (domain terms) and the `improve-codebase-architecture` skill's LANGUAGE.md (Module / Interface / Seam / Adapter / Depth).

> **Status:** spec, not yet implemented. The current code still has `classify_document` doing the loop and trace-mutation inline; this doc describes the post-refactor shape.

---

## Pipeline

```
cli.scan
  └── for each Document:
        classify_document(path, reqs, llm, engine, max_rounds)
          ├── Fast Path (extractors/passport)
          ├── build_initial_messages(path, reqs)        ← orchestrator-private
          ├── engine.run(state, tools, llm, max_rounds) ← Engine seam
          ├── parse_final(final_state, valid_categories)
          ├── extract_artifacts(final_state)
          └── Tracer.from_state(final_state, fast_path_step)
        → ClassificationResult
  └── matcher.match(reqs, file_results, llm)            ← LLM seam (shared)
  └── output.assemble_output(...)                       ← unchanged this PR
```

Two seams introduced: **Engine** and **LLM**. Tools fused into one **Tool registry** Module. Tracing becomes a pure derivation (`Tracer.from_state`).

---

## Engine — `src/veasy_peasy/engine.py`

Swappable LLM tool-call loop. The orchestrator hands it an initial state and gets a final state back. Knows nothing about Documents, Requirements, or Trace JSON shape.

### Interface

```python
class Engine(Protocol):
    def run(
        self,
        state: EngineState,
        tools: ToolRegistry,
        llm: LLM,
        max_rounds: int,
    ) -> EngineState: ...
```

### EngineState (lean dict — the seam payload)

```python
EngineState = TypedDict("EngineState", {
    "messages":       list[dict],   # [{role, content, tool_calls?}, ...]
    "tool_timings":   list[dict],   # [{round, name, args, elapsed_s, result_excerpt}]
    "llm_timings":    list[dict],   # [{round, wall_time_s}]
    "artifacts":      dict,         # {extracted_fields, text_excerpt, text_length}
    "stop_reason":    str,          # "final" | "max_rounds" | "error"
    "error":          str | None,
})
```

`messages` uses plain dicts (no `BaseMessage`) so a future `LangGraphEngine` translates internally; the seam stays library-agnostic.

### Adapters

| Adapter | Where | Used by |
|---|---|---|
| `ManualEngine` | `engine.py` | production (current loop, extracted) |
| `ScriptedEngine` | `tests/fixtures/engines.py` | orchestrator tests that don't care about loop internals |
| _LangGraphEngine_ | _future_ | _drop-in via same Interface_ |

### Invariants

- Always returns; LLM/Tool errors set `state["error"]` + `stop_reason="error"`, never raise.
- Honours `max_rounds`; hitting it sets `stop_reason="max_rounds"` and returns last-known state.
- Appends to `tool_timings` / `llm_timings` exactly once per call. Wrapping is provided by `ToolRegistry.dispatch` and `LLM.chat` — engines must not re-time.
- Mutates **only** the state it owns. Doesn't reach into `artifacts` directly — `ToolRegistry.dispatch` writes there for known artifact-producing tools (see Tool registry below).

### Contract test

`tests/test_engine_contract.py`. One scripted scenario set runs against every Adapter. Same script in → same `EngineState` out (modulo wall-time).

---

## LLM — `src/veasy_peasy/llm.py`

Thin Adapter over the chat / generate calls. Used by **both** the Engine and the Matcher so neither talks to `ollama_client` directly.

### Interface

```python
class LLM(Protocol):
    def chat(self, messages: list[dict], tools: list[dict]) -> ChatResponse: ...
    def generate(self, prompt: str, temperature: float = 0.0) -> GenerateResponse: ...

ChatResponse     = TypedDict(..., {"message": dict, "wall_time_s": float})
GenerateResponse = TypedDict(..., {"response": str, "wall_time_s": float})
```

### Adapters

| Adapter | Where |
|---|---|
| `OllamaLLM(model)` | `llm.py` — wraps `ollama_client.chat_with_tools` + `generate` |
| `ScriptedLLM(script)` | `tests/fixtures/llms.py` — yields next scripted response per call |

### Invariants

- `wall_time_s` always populated.
- No retries, no fallback. Caller decides.
- Constructed once per run; carries the model name.

---

## Tool registry — `src/veasy_peasy/tools.py`

Replaces today's parallel `TOOL_SCHEMAS` + `TOOL_DISPATCH` dicts. One source of truth per Tool.

### Interface

```python
@dataclass(frozen=True)
class Tool:
    name: str
    description: str
    params: dict           # JSON schema
    fn: Callable[..., dict]
    writes_artifacts: bool = False  # if True, dispatch merges result into state["artifacts"]

class ToolRegistry:
    def __init__(self, tools: list[Tool]): ...
    def schemas(self) -> list[dict]: ...                          # for LLM.chat
    def dispatch(self, name: str, args: dict, state: EngineState) -> dict: ...
```

### Invariants

- `dispatch` always returns a JSON-serialisable dict; never raises. Unknown tool / bad args / fn raising → `{"error": "..."}`.
- `dispatch` appends one entry to `state["tool_timings"]` per call.
- For `writes_artifacts=True` tools, `dispatch` updates `state["artifacts"]` from the result (text excerpt for text-producing tools, `extracted_fields` for `check_mrz`). Engines no longer need to know which tools cache what.

### Tools registered today

| Tool | writes_artifacts | Notes |
|---|---|---|
| `extract_pdf_text` | yes (text) | |
| `ocr_image` | yes (text) | |
| `check_mrz` | yes (mrz fields) | |
| `keyword_score` | no | sanity-check only — see ADR-0003 |

---

## Tracer — `src/veasy_peasy/tracer.py`

Pure function. Walks a final `EngineState` (plus the optional Fast Path step) and produces the **Trace** JSON shape that `output._write_traces` already writes.

### Interface

```python
@dataclass
class FastPathStep:
    tool: str               # e.g. "try_passport"
    result: dict | None
    elapsed_s: float
    decision: str | None    # e.g. "passport" if matched

def from_state(
    final_state: EngineState,
    fast_path_step: FastPathStep | None,
    model: str,
    file_path: Path,
    wall_time_s: float,
) -> dict: ...
```

### Invariants

- Output JSON schema unchanged from today (`{file, final_classification, decision_path, model, wall_time_s, steps[]}`). `output.py` and `summary.py` consume the same shape; no changes there.
- `decision_path = "deterministic_mrz"` iff `fast_path_step.decision == "passport"`, else `"llm_orchestrator"`.
- Pure: no I/O, no clock reads.

---

## Orchestrator — `src/veasy_peasy/orchestrator.py` (slimmed)

Per-Document coordinator. Was 276 lines of mixed loop + trace mutation; becomes ~80 lines of glue.

### Interface

```python
def classify_document(
    path: Path,
    requirements_data: dict,
    llm: LLM,
    engine: Engine,
    max_rounds: int = 5,
) -> ClassificationResult: ...

ClassificationResult = TypedDict(..., {
    "path": str, "ext": str,
    "classification": str,
    "extracted_fields": dict,
    "text_excerpt": str, "text_length": int,
    "error": str | None,
    "trace": dict,
})
```

Note: `model` argument removed — model lives on the `LLM` Adapter.

### Body shape

```
1. fast_path = run Fast Path; if hit → return early via Tracer.from_state(empty_state, fast_path_step)
2. messages  = build_initial_messages(path, reqs)
3. state     = {messages, tool_timings: [], llm_timings: [], artifacts: {...}, stop_reason: "final", error: None}
4. final     = engine.run(state, TOOL_REGISTRY, llm, max_rounds)
5. cls       = parse_final(final, valid_categories)
6. trace     = Tracer.from_state(final, fast_path_step=None, ...)
7. return ClassificationResult(...)
```

### Private helpers

- `build_initial_messages(path, reqs) -> list[dict]` — system prompt + user message. Owns prompt content (not Engine concern).
- `parse_final(state, valid_categories) -> {classification, reason}` — reads last `messages[-1].content`, delegates to `parse_llm_json`.
- `extract_artifacts(state) -> {...}` — pulls cached artifacts off `state["artifacts"]` into the result shape.

---

## Matcher — `src/veasy_peasy/matcher.py`

Same job as today, but takes the **LLM** seam instead of a `model` string.

### Interface

```python
def match(
    requirements_data: dict,
    file_results: list[ClassificationResult],
    llm: LLM,
) -> MatchResult: ...
```

### Invariants

- Output dict shape unchanged (`model`, `result`, `raw_response`, `parse_ok`, `wall_time_s`, `eval_count`, `prompt_eval_count`).
- JSON parsing delegates to `parse_llm_json`.

---

## parse_llm_json — `src/veasy_peasy/llm_json.py`

Pure helper. Two callers today (`orchestrator.parse_final`, `matcher.parse_response`) duplicate this logic; fuse.

### Interface

```python
def parse_llm_json(
    text: str,
    required_keys: tuple[str, ...] = (),
) -> dict | None: ...
```

Strips ``` fences, locates the outermost `{...}`, `json.loads`. Returns `None` if parse fails or required keys are missing.

---

## What survives the swap to LangGraph

Everything below stays bit-identical when `LangGraphEngine` replaces `ManualEngine`:

- All Tool fns (PDF text, OCR, MRZ, keyword score)
- `ToolRegistry` (registration list)
- `LLM` Adapter (`OllamaLLM` — LangGraph would use a LangChain `ChatOllama` Adapter, but the seam is unchanged)
- `Tracer.from_state` (consumes `EngineState`, agnostic to who built it)
- `parse_final`, `extract_artifacts`, `parse_llm_json`
- `classify_document` body
- `Matcher`
- All tests that use `ScriptedLLM` / `ScriptedEngine`
- `output.py`, `summary.py` (unchanged)

What changes for the swap:

- New file `engine_langgraph.py` implementing `Engine` Protocol
- Internally translates `EngineState["messages"]` ↔ `MessagesState`
- Wires LangGraph nodes: chat node → tools_condition → tool node → loop, terminating when no tool calls or `max_rounds` hit
- CLI wires `LangGraphEngine()` instead of `ManualEngine()` (one-line change in `cli.py`)

---

## Test surface

| Test file | What it exercises | Crosses Engine seam? |
|---|---|---|
| `tests/test_tools.py` | each Tool fn, registry dispatch + timer | no |
| `tests/test_tracer.py` | canned `EngineState` → expected Trace JSON | no |
| `tests/test_llm_json.py` | fence-stripping, brace-finding, validation | no |
| `tests/test_engine_contract.py` | scripted scenarios against every Engine Adapter | yes |
| `tests/test_orchestrator.py` | golden Documents with `ScriptedEngine` + `ScriptedLLM` | indirect |
| `tests/test_matcher.py` | `match(...)` with `ScriptedLLM` | no (no Engine) |
| `tests/test_e2e.py` | full pipeline w/ `ScriptedEngine` | indirect |

The contract test is the swap-safety guarantee: any new Engine Adapter must pass `test_engine_contract.py` unchanged.
