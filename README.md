# Veasy Peasy

Local-first CLI that scans visa application documents, extracts structured data using specialized OCR, and classifies them against a requirements checklist.

## Prerequisites

- macOS (Apple Silicon)
- Python 3.13+
- [uv](https://docs.astral.sh/uv/)
- Tesseract: `brew install tesseract`

## Quickstart

```bash
uv sync
uv run veasy-peasy scan ./my_documents --requirements example_requirements/visa_uk.yaml
```

Output is written to `my_documents/summary.json`.

## What it does

1. Walks the target folder for PDFs and images
2. Attempts passport MRZ extraction (passporteye) on each file
3. Falls back to general OCR (EasyOCR with MPS acceleration) for non-passport docs
4. Classifies each document by keyword rules
5. Writes a structured `summary.json` with results
