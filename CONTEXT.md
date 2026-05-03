# Veasy Peasy

Local-first CLI that scans a folder of visa-application Documents, classifies each one against a Requirements Sheet using an Ollama LLM, and writes a Report Folder of renamed copies plus a machine- and human-readable summary.

> Module-level Interfaces and seam contracts: see [`docs/architecture/modules.md`](docs/architecture/modules.md).

## Language

**Document**:
A single file (.pdf / .png / .jpg / .jpeg) on disk being scanned. "Doc" is fine as a short form.
_Avoid_: file, scan, item

**Requirements Sheet**:
The YAML file declaring the `visa_type` and the list of Requirements for one application.
_Avoid_: requirements file, checklist, manifest

**Requirement**:
One entry in the Requirements Sheet — `{name, description, required}`. The `name` is the canonical label a Document can be Classified into.
_Avoid_: category, item, type

**Classification**:
The Requirement name a Document was sorted into by the Orchestrator, or `unknown`.
_Avoid_: category, label, doc type

**Match**:
A pairing of one Document to one Requirement, decided by the Matcher.
_Avoid_: assignment, mapping, link

**Conflict**:
More than one Document satisfies the same Requirement; the Matcher picks one.
_Avoid_: duplicate, collision, clash

**Missing**:
A Requirement with no matched Document.
_Avoid_: unmet, gap, absent

**Validation Warning**:
A Matcher-flagged suspicious Classification (e.g. employment letter labelled as bank statement).
_Avoid_: misclass, error, mistake

**Orchestrator**:
The per-Document coordinator: runs the deterministic Fast Path, delegates the LLM tool-call loop to an Engine, then derives a Trace from the result. Lives in `orchestrator.py`.
_Avoid_: classifier (ambiguous), pipeline, agent

**Engine**:
The swappable LLM tool-call loop. Consumes an initial state + Tool registry + LLM, returns a final state. Adapter today: `ManualEngine`. Lives in `engine.py`. The seam is shaped so a future LangGraph-based Adapter drops in unchanged. See [`docs/architecture/modules.md`](docs/architecture/modules.md).
_Avoid_: agent, runner, loop

**LLM**:
Adapter Module wrapping the chat-with-tools and plain-generate calls. Used by both Engine and Matcher so neither talks to `ollama_client` directly. Single Adapter today: `OllamaLLM`. Lives in `llm.py`.
_Avoid_: model, client, ollama

**Matcher**:
The second LLM pass that pairs Documents to Requirements across the whole run, resolves Conflicts, and emits Validation Warnings. Lives in `matcher.py`.
_Avoid_: matcher LLM, validator, reconciler

**Extractor**:
A specialised reader that turns a Document into text or structured fields (passport MRZ, EasyOCR, PyMuPDF). Lives under `extractors/`.
_Avoid_: parser, reader, ingester

**Tool**:
A function exposed to the Orchestrator LLM via Ollama tool-calling — `extract_pdf_text`, `ocr_image`, `keyword_score`, `check_mrz`. Lives in `tools.py`.
_Avoid_: function, action, capability

**MRZ**:
Machine-Readable Zone on a passport. Standardised, deterministically parseable.
_Avoid_: passport zone, passport code

**Fast Path**:
The deterministic branch in the Orchestrator that bypasses the LLM entirely (a valid MRZ → Classification `passport`).
_Avoid_: shortcut, bypass, deterministic mode

**Trace**:
Per-Document log of every Orchestrator step — Tool calls with args/elapsed, LLM messages, decisions. Persisted as `traces/<doc>.trace.json` inside the Report Folder.
_Avoid_: log, history, audit

**Report Folder**:
The per-run output directory `VzPz_Report_<ts>/` containing renamed Document copies, the Summary, the Report, and the Traces folder.
_Avoid_: output dir, results dir

**Summary**:
`summary.json` inside the Report Folder — full machine-readable run record (requirements loaded, Matcher result, file results minus Traces).
_Avoid_: manifest, output json

**Report**:
`report.md` inside the Report Folder — human-readable markdown view of Requirements status, Matches, Missing, Conflicts, Validation Warnings, and Unmatched Documents.
_Avoid_: summary md, output md

## Relationships

- A **Requirements Sheet** declares one or more **Requirements** for a single visa type.
- The **Orchestrator** processes one **Document** at a time and produces a **Classification** plus a **Trace**.
- The **Orchestrator** uses **Extractors** indirectly — by calling **Tools** that wrap them.
- The **Fast Path** sits inside the **Orchestrator** and may resolve a **Classification** without ever invoking the LLM.
- The **Matcher** consumes all Classified **Documents** + the **Requirements Sheet** and produces **Matches**, **Missing**, **Conflicts**, and **Validation Warnings**.
- One run produces one **Report Folder** containing the **Summary**, the **Report**, renamed **Document** copies (one per **Match**), and one **Trace** per scanned **Document**.

## Example dialogue

> **Dev:** "If a passport has a clean **MRZ**, does the **Orchestrator** still call the LLM?"
> **Domain expert:** "No — the **Fast Path** sets **Classification** to `passport` and we skip straight to the next **Document**. The **Trace** records `decision_path: deterministic_mrz`."
>
> **Dev:** "And if the **Matcher** sees two passports?"
> **Domain expert:** "That's a **Conflict**. The **Matcher** picks the non-expired one and writes a **Conflict** entry; the loser shows up under Unmatched in the **Report**."

## Flagged ambiguities

- **"category"** appears in `orchestrator.py` (`valid_categories`, `category_list`) for what is really a **Requirement** name. The seam is internal but the term is wrong — prefer **Requirement** in new code.
- **"classifier"** is overloaded: `classifier.py` exists, but `classify()` is dead code; only the `RULES` dict survives, exposed via the `keyword_score` **Tool**. The new system is the **Orchestrator**, not "the classifier". (See ADR-0003.)
- **"matched" vs "satisfied"** drift in `report.md`: the **Match** is the act of pairing; a **Requirement** is "satisfied" when a Match exists for it. Don't use them interchangeably.
