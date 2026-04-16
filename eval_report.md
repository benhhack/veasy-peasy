# Model Evaluation Report

**Models tested:** llama3.2:3b, phi4-mini, qwen2.5:3b, gemma3:4b
**Scenarios:** happy_path, missing_docs, conflicts, bad_classification, noisy_ocr, extra_documents
**Runs per scenario:** 10

## Summary

| Model | Load (s) | Avg Tok/s | Parse % | Match F1 | Miss F1 | Conflict % | Valid % | **Score** |
|-------|----------|-----------|---------|----------|---------|------------|---------|-----------|
| llama3.2:3b | 2.8 | 41.9 | 100% | 1.00 | 0.28 | 17% | 83% | **0.72** |
| phi4-mini | 2.9 | 34.6 | 100% | 0.97 | 0.50 | 33% | 83% | **0.78** |
| qwen2.5:3b | 2.1 | 43.6 | 100% | 1.00 | 0.67 | 50% | 83% | **0.85** |
| gemma3:4b | 3.2 | 29.6 | 100% | 0.97 | 0.50 | 67% | 83% | **0.81** |

*Composite score weights: matched_f1=0.35, missing_f1=0.25, parse=0.2, conflict=0.1, validation=0.1*

## Per-Scenario Breakdown

### happy_path
*All required documents present with clear matches*

| Model | Parse | Time (s) | Tok/s | Match F1 | Miss F1 | Conflict | Validation |
|-------|-------|----------|-------|----------|---------|----------|------------|
| llama3.2:3b | OK | 4.6 | 42.3 | 1.00 | 0.00 | no | yes |
| phi4-mini | OK | 5.2 | 34.4 | 1.00 | 1.00 | no | yes |
| qwen2.5:3b | OK | 4.3 | 44.1 | 1.00 | 1.00 | no | yes |
| gemma3:4b | OK | 5.8 | 32.5 | 1.00 | 1.00 | yes | yes |

### missing_docs
*Bank statement is missing from the folder*

| Model | Parse | Time (s) | Tok/s | Match F1 | Miss F1 | Conflict | Validation |
|-------|-------|----------|-------|----------|---------|----------|------------|
| llama3.2:3b | OK | 3.3 | 41.9 | 1.00 | 0.67 | no | yes |
| phi4-mini | OK | 3.8 | 34.6 | 1.00 | 0.00 | no | yes |
| qwen2.5:3b | OK | 2.5 | 43.7 | 1.00 | 1.00 | yes | yes |
| gemma3:4b | OK | 3.9 | 31.7 | 1.00 | 0.00 | yes | yes |

### conflicts
*Two passports found: one expired, one valid. Model should pick the valid one.*

| Model | Parse | Time (s) | Tok/s | Match F1 | Miss F1 | Conflict | Validation |
|-------|-------|----------|-------|----------|---------|----------|------------|
| llama3.2:3b | OK | 3.0 | 40.2 | 1.00 | 0.00 | yes | yes |
| phi4-mini | OK | 4.9 | 34.6 | 1.00 | 1.00 | yes | yes |
| qwen2.5:3b | OK | 3.0 | 43.2 | 1.00 | 1.00 | yes | yes |
| gemma3:4b | OK | 5.2 | 31.8 | 1.00 | 1.00 | no | yes |

### bad_classification
*An employment letter is misclassified as a bank statement. Model should flag the mismatch.*

| Model | Parse | Time (s) | Tok/s | Match F1 | Miss F1 | Conflict | Validation |
|-------|-------|----------|-------|----------|---------|----------|------------|
| llama3.2:3b | OK | 3.2 | 42.4 | 1.00 | 1.00 | no | no |
| phi4-mini | OK | 5.2 | 35.1 | 1.00 | 0.00 | no | yes |
| qwen2.5:3b | OK | 2.4 | 43.7 | 1.00 | 0.00 | no | no |
| gemma3:4b | OK | 7.7 | 32.9 | 0.80 | 0.00 | no | yes |

### noisy_ocr
*Documents with realistic OCR noise (garbled chars, partial reads). Tests model robustness.*

| Model | Parse | Time (s) | Tok/s | Match F1 | Miss F1 | Conflict | Validation |
|-------|-------|----------|-------|----------|---------|----------|------------|
| llama3.2:3b | OK | 4.8 | 42.3 | 1.00 | 0.00 | no | yes |
| phi4-mini | OK | 5.2 | 34.5 | 1.00 | 1.00 | no | yes |
| qwen2.5:3b | OK | 4.5 | 44.2 | 1.00 | 1.00 | no | yes |
| gemma3:4b | OK | 8.4 | 25.6 | 1.00 | 1.00 | yes | yes |

### extra_documents
*6 files for 3 requirements. Model must match correctly and ignore irrelevant docs.*

| Model | Parse | Time (s) | Tok/s | Match F1 | Miss F1 | Conflict | Validation |
|-------|-------|----------|-------|----------|---------|----------|------------|
| llama3.2:3b | OK | 4.1 | 42.1 | 1.00 | 0.00 | no | yes |
| phi4-mini | OK | 6.1 | 34.4 | 0.80 | 0.00 | yes | no |
| qwen2.5:3b | OK | 3.3 | 42.7 | 1.00 | 0.00 | yes | yes |
| gemma3:4b | OK | 8.1 | 23.0 | 1.00 | 0.00 | yes | no |

## Recommendation

Based on composite scoring across all scenarios, **qwen2.5:3b** (score: 0.85) is the best fit for this task.
