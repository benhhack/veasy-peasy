# Veasy Peasy

A local-first CLI tool that scans a folder of visa application documents, extracts structured data using specialized OCR, and matches them against a requirements checklist using a local LLM. No data leaves your machine.

## Why This Exists

For someone like me (a South African living in the UK who travels a bunch) I spend way too much time looking for specific documents from different sources and manually cross-referencing them against a checklist. Since I do this a lot I already have all the documents, I just never remember where I put them. This tool automates that: point it at a folder of scans and a requirements file, and it tells you what's matched, what's missing, and resolves conflicts (e.g., two passports — which one is valid?).

## Next Steps
- [ ] Wire it up end to end
- [ ] Allow it to search through emails as well
- [ ] Enhance local search by giving it multiple folders and nested directory tooling
- [ ] Improve step 1: give the LLM a requirement sheet which it parses into the requirements.yaml
- [ ] I never know which file is which. Get the LLM to save copies of the necessary files in a common space, renamed properly.
- [x] Make it installable as a standalone tool

## Installation (note: not wired up yet so won't actually do anything)

<p align="center">
  <img src="docs/vzpz-init.svg" alt="vzpz init" width="600">
</p>

### curl (macOS)

```bash
curl -fsSL https://raw.githubusercontent.com/benhhack/veasy-peasy/main/install.sh | bash
```

This downloads the latest release binary to `~/.local/bin/vzpz`. Make sure `~/.local/bin` is on your `PATH`.

### Manual download

Grab the binary for your architecture from the [latest release](https://github.com/benhhack/veasy-peasy/releases/latest), make it executable, and put it somewhere on your `PATH`:

```bash
chmod +x vzpz-aarch64-darwin
mv vzpz-aarch64-darwin /usr/local/bin/vzpz
```

### Usage

```bash
vzpz --version
vzpz --help
vzpz init        # initialise a new workspace
```

## Privacy
Since these are sensitive documents, I wanted to keep everything completely local: no external API calls for LLMs. Goal is for it to fit quite comfortably in 8GB RAM and to cleanup totally and immediately upon completion.

## Architecture

The pipeline deliberately uses the **right tool for each job** rather than throwing an LLM at everything:

```
Input: folder/ + requirements.yaml
         │
         ▼
┌─────────────────────────┐
│  File Discovery         │  Walk dir, filter pdf/jpg/png
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Specialized Extractors │  passporteye (MRZ) + EasyOCR (general)
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  Keyword Classifier     │  Rule-based doc type detection
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  LLM Matcher (Ollama)   │  Match docs → requirements, resolve conflicts
└─────────────────────────┘
         │
         ▼
Output: report.json + summary.md
```

| Stage | Tool | Why not an LLM? |
|-------|------|-----------------|
| Passport parsing | `passporteye` (MRZ reader) | MRZ is a standardized machine-readable format — deterministic parsing beats probabilistic generation |
| Text extraction | `EasyOCR` with MPS acceleration | OCR is a solved problem with mature models; LLM adds latency and cost for no accuracy gain |
| Doc classification | Keyword rules | Simple heuristics (e.g., "sort code" → bank statement) are fast, interpretable, and > 95% accurate for this domain |
| Requirement matching | Local LLM via Ollama | This is where reasoning is actually needed: fuzzy matching, conflict resolution, validation of classifications |

## Model Evaluation

Choosing the right small language model for the matching step is critical — it needs to run locally, produce valid JSON, and handle edge cases. I built an evaluation harness that tests 4 models across 6 scenarios.

### Models Tested

| Model | Parameters | Notes |
|-------|-----------|-------|
| llama3.2:3b | 3B | Meta's compact model |
| phi4-mini | 3.8B | Microsoft's reasoning-focused model |
| qwen2.5:3b | 3B | Alibaba's instruction-tuned model |
| gemma3:4b | 4B | Google's lightweight model |

### Evaluation Scenarios

| Scenario | What it tests |
|----------|--------------|
| **happy_path** | All required documents present with clear matches |
| **missing_docs** | Some requirements have no matching document |
| **conflicts** | Two passports found (one expired) — must pick the valid one |
| **bad_classification** | Employment letter misclassified as bank statement — LLM should flag it |
| **noisy_ocr** | Documents with garbled OCR text (character substitutions, partial reads) |
| **extra_documents** | 6 files for 3 requirements — must match correctly and ignore irrelevant docs |

### Results

| Model | Tok/s | Parse % | Match F1 | Miss F1 | Conflict % | Valid % | **Score** |
|-------|-------|---------|----------|---------|------------|---------|-----------|
| llama3.2:3b | 34.6 | 100% | 1.00 | 0.28 | 17% | 83% | 0.72 |
| phi4-mini | 27.4 | 100% | 0.97 | 0.50 | 33% | 83% | 0.78 |
| qwen2.5:3b | 32.7 | 100% | 1.00 | 0.67 | 50% | 83% | **0.85** |
| gemma3:4b | 26.9 | 100% | 0.97 | 0.50 | 67% | 83% | 0.81 |

*Composite score weights: match F1 (35%), missing F1 (25%), parse rate (20%), conflict detection (10%), validation (10%)*

### Key Findings

- **All models achieve 100% JSON parse rate** — the prompt template with explicit schema works well
- **Document matching is the easy part** — all models score >= 0.97 F1 on matching documents to requirements
- **Missing document detection separates the field** — llama3.2 frequently hallucinates missing docs that aren't actually missing (0.28 F1), while qwen2.5 correctly identifies gaps (0.67 F1)
- **Conflict resolution is the hardest task** — only gemma3 (67%) and qwen2.5 (50%) reliably detect when two documents compete for the same requirement. llama3.2 invents conflicts that don't exist
- **OCR noise is a non-issue** — all models handle garbled text gracefully, matching through character-level corruption
- **phi4-mini and gemma3 are the only models that flag misclassified documents** — both correctly identified an employment letter wrongly labelled as a bank statement

### Model Choice: qwen2.5:3b

**qwen2.5:3b** scores highest overall (0.85) with the best balance of accuracy and speed:
- Perfect document matching (F1 = 1.00)
- Best missing document detection (F1 = 0.67)
- Second-fastest inference (32.7 tok/s)
- Reliable JSON output (100% parse rate)

Its main weakness is validation — it doesn't flag misclassified documents. Since the keyword classifier handles classification well for this domain, this is an acceptable trade-off. For applications where upstream classification is less reliable, gemma3:4b would be the better choice despite being slower.

## Prerequisites

- macOS (Apple Silicon recommended for MPS acceleration)
- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Tesseract: `brew install tesseract`
- [Ollama](https://ollama.ai) running locally

## Quickstart

```bash
uv sync
ollama pull qwen2.5:3b
uv run veasy-peasy ./example_documents --requirements example_requirements/visa_schengen.yaml
```

## Running the Model Evaluation

```bash
# Single run (fast)
.venv/bin/python tests/test_model_eval.py

# Multiple runs for variance estimation
EVAL_RUNS=3 .venv/bin/python tests/test_model_eval.py

# Via pytest
.venv/bin/python -m pytest tests/test_model_eval.py -s --tb=short
```

Results are saved to `tests/eval_results.json` and `eval_report.md`.

## Tech Stack

| Component | Tool |
|-----------|------|
| CLI | `typer` |
| Passport OCR | `passporteye` |
| General OCR | `easyocr` (MPS accelerated) |
| PDF handling | `pymupdf` |
| Doc classification | Keyword rules |
| Local LLM | Ollama + qwen2.5:3b |
