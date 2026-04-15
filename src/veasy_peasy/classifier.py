RULES: dict[str, list[str]] = {
    "passport": [
        "passport", "p<", "passeport", "passport no",
        "type p", "date of issue", "date of expiry",
    ],
    "bank_statement": [
        "statement", "account number", "sort code", "iban",
        "opening balance", "closing balance", "transaction",
    ],
    "proof_of_address": [
        "utility", "council tax", "electricity", "gas bill",
        "water bill", "billing address", "service address",
    ],
    "employment_letter": [
        "to whom it may concern", "employment", "salary",
        "hereby confirm", "employed", "position", "annual",
    ],
}


def classify(text: str, has_mrz: bool = False, mrz_type: str = "") -> str:
    """Return the document type with the most keyword hits, or 'unknown'."""
    text_lower = text.lower()
    scores = {
        category: sum(1 for kw in keywords if kw in text_lower)
        for category, keywords in RULES.items()
    }
    # MRZ type "P" is a signal (not proof) that this is a passport
    if has_mrz and mrz_type.startswith("P"):
        scores["passport"] = scores.get("passport", 0) + 1
    best = max(scores, key=scores.get)
    if scores[best] == 0:
        return "unknown"
    # Check for tie at the top
    top_score = scores[best]
    tied = [k for k, v in scores.items() if v == top_score]
    if len(tied) > 1:
        return "unknown"
    return best
