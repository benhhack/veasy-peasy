# Veasy Peasy: Local Document Matcher for Visa Applications

## What It Is
A CLI tool that scans a folder of documents, extracts structured data using specialized OCR, and matches them against a visa/passport application checklist using a local LLM.

## Why It's Good for Your Resume
- Shows you know when NOT to use an LLM (specialized extractors for passports)
- Local-first, privacy-conscious architecture
- Full pipeline: file I/O → OCR → structured extraction → LLM orchestration
- Solves a real problem people actually have

---

## Scope (2 Days)

### Day 1: Extraction Pipeline
- [ ] CLI skeleton with `typer` (takes folder path + requirements file)
- [ ] Passport extractor using `passporteye` → `{name, dob, expiry, number}`
- [ ] Generic text extractor using `EasyOCR` for other docs
- [ ] Simple classifier: detect doc type from extracted text (keyword rules)

### Day 2: LLM Matching + Polish
- [ ] Wire up Ollama (Phi-3 or Llama 3.2 3B)
- [ ] Matching prompt: requirements + extracted docs → matches/missing
- [ ] Tiebreak logic (e.g., pick non-expired passport)
- [ ] JSON + Markdown output
- [ ] README + demo recording

---

## Architecture

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
│  Specialized Extractors │  passporteye (MRZ), EasyOCR (general)
└─────────────────────────┘
         │
         ▼
┌─────────────────────────┐
│  LLM Orchestrator       │  Ollama local model
│  - Match docs to reqs   │
│  - Handle conflicts     │
└─────────────────────────┘
         │
         ▼
Output: report.json + summary.md
```

---

## Tech Stack
| Component | Tool |
|-----------|------|
| CLI | `typer` |
| Passport OCR | `passporteye` |
| General OCR | `easyocr` |
| PDF handling | `pymupdf` |
| Local LLM | Ollama + Phi-3 / Llama 3.2 3B |

---

## Example Output

```json
{
  "matched": [
    {"requirement": "passport", "file": "scan_001.jpg", "expiry": "2028-03-15"}
  ],
  "missing": ["proof of address", "bank statement"],
  "conflicts_resolved": [
    "Found 2 driver's licenses; selected license_new.pdf (expires 2027) over license_old.pdf (expired 2023)"
  ]
}
```

---

## Out of Scope (for now)
- Native macOS GUI (CLI only)
- Full-disk search / indexing
- Cover letter generation
- Multi-country ID format support (start with passports only)

---

## Demo Script (for recording)
1. Show requirements.yaml with 4-5 common visa docs
2. Run `docmatch ./my_documents --requirements visa_uk.yaml`
3. Show it finding passport, flagging missing docs
4. Show conflict resolution in output