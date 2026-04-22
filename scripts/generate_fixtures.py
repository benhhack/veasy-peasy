"""Generate synthetic fixture PDFs for example_documents/.

Usage: uv run python scripts/generate_fixtures.py

Produces small text-only PDFs whose contents exercise the keyword classifier
so the README Quickstart scan command has something real to work with.
"""
from __future__ import annotations

from pathlib import Path

import fitz  # pymupdf


OUT_DIR = Path(__file__).resolve().parent.parent / "example_documents"


FIXTURES: dict[str, list[str]] = {
    "passport.pdf": [
        "PASSPORT",
        "UNITED KINGDOM OF GREAT BRITAIN",
        "Type P   Country Code GBR   Passport No. 123456789",
        "Surname: SMITH",
        "Given Names: JOHN",
        "Nationality: BRITISH CITIZEN",
        "Date of Birth: 15 MAR 1985",
        "Date of Issue: 01 JAN 2020",
        "Date of Expiry: 01 JAN 2030",
    ],
    "bank_statement.pdf": [
        "HSBC UK — Statement of Account",
        "Account Holder: John Smith",
        "Account Number: 12345678",
        "Sort Code: 40-01-02",
        "IBAN: GB29 HSBC 4001 0212 3456 78",
        "Statement Period: 01 Mar 2026 — 31 Mar 2026",
        "Opening Balance: £3,200.00",
        "Closing Balance: £4,150.75",
        "",
        "Transaction details",
        "02 Mar  Tesco               -£42.10",
        "05 Mar  Salary Acme Corp  +£3,800.00",
        "17 Mar  TfL                 -£28.00",
    ],
    "council_tax.pdf": [
        "London Borough of Camden — Council Tax Bill 2025/2026",
        "Billing Address: 42 Elm Road, London NW3 4QP",
        "Service Address: 42 Elm Road, London NW3 4QP",
        "Utility: council tax, electricity, gas bill, water bill",
        "Amount due: £1,850.00",
    ],
    "employment_letter.pdf": [
        "Acme Corp Ltd",
        "10 Downing Street, London SW1A 2AA",
        "",
        "To Whom It May Concern",
        "",
        "We hereby confirm that John Smith has been employed",
        "as a Senior Engineer since January 2020.",
        "His position is permanent and his annual salary is £65,000.",
        "",
        "Yours faithfully,",
        "HR Department",
    ],
}


def write_pdf(path: Path, lines: list[str]) -> None:
    doc = fitz.open()
    page = doc.new_page()
    text = "\n".join(lines)
    page.insert_text((72, 72), text, fontsize=11)
    doc.save(str(path))
    doc.close()


def main() -> None:
    OUT_DIR.mkdir(exist_ok=True)
    for name, lines in FIXTURES.items():
        out = OUT_DIR / name
        write_pdf(out, lines)
        print(f"wrote {out}")


if __name__ == "__main__":
    main()
