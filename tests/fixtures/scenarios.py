"""Test scenarios with synthetic pre-extracted data and ground truth."""

# ---------------------------------------------------------------------------
# Scenario 1: Happy path — all documents present, clear matches
# ---------------------------------------------------------------------------
HAPPY_PATH = {
    "name": "happy_path",
    "description": "All required documents present with clear matches",
    "requirements": {
        "visa_type": "UK Standard Visitor",
        "documents": [
            {"name": "passport", "description": "Valid passport with at least 6 months remaining"},
            {"name": "bank_statement", "description": "Bank statement from the last 3 months"},
            {"name": "employment_letter", "description": "Letter from employer confirming role and salary"},
        ],
    },
    "files": [
        {
            "path": "/docs/passport_scan.jpg",
            "ext": ".jpg",
            "classification": "passport",
            "extracted_fields": {
                "mrz_type": "P",
                "name": "JOHN",
                "surname": "SMITH",
                "dob": "850315",
                "expiry": "280901",
                "number": "AB1234567",
                "nationality": "GBR",
            },
            "text_excerpt": "PASSPORT P GBR SMITH JOHN 850315 M 280901 AB1234567",
            "text_length": 51,
            "error": None,
        },
        {
            "path": "/docs/hsbc_march_2026.pdf",
            "ext": ".pdf",
            "classification": "bank_statement",
            "extracted_fields": {},
            "text_excerpt": "HSBC UK\nStatement of Account\nAccount Number: 12345678\nSort Code: 40-01-02\nStatement Period: 01 Mar 2026 - 31 Mar 2026\nOpening Balance: £3,200.00\nClosing Balance: £4,150.75\nTransaction details...",
            "text_length": 1200,
            "error": None,
        },
        {
            "path": "/docs/employer_letter.pdf",
            "ext": ".pdf",
            "classification": "employment_letter",
            "extracted_fields": {},
            "text_excerpt": "Acme Corp Ltd\n10 Downing Street, London\n\nTo Whom It May Concern\n\nThis letter is to confirm that John Smith has been employed as a Senior Engineer since January 2020. His annual salary is £65,000.\n\nYours faithfully,\nHR Department",
            "text_length": 320,
            "error": None,
        },
    ],
    "ground_truth": {
        "matched": [
            {"requirement": "passport", "file": "/docs/passport_scan.jpg"},
            {"requirement": "bank_statement", "file": "/docs/hsbc_march_2026.pdf"},
            {"requirement": "employment_letter", "file": "/docs/employer_letter.pdf"},
        ],
        "missing": [],
        "conflicts_resolved": [],
        "validation_warnings": [],
    },
}


# ---------------------------------------------------------------------------
# Scenario 2: Missing documents — passport and employment letter present,
#              bank statement missing
# ---------------------------------------------------------------------------
MISSING_DOCS = {
    "name": "missing_docs",
    "description": "Bank statement is missing from the folder",
    "requirements": {
        "visa_type": "UK Standard Visitor",
        "documents": [
            {"name": "passport", "description": "Valid passport with at least 6 months remaining"},
            {"name": "bank_statement", "description": "Bank statement from the last 3 months"},
            {"name": "proof_of_address", "description": "Utility bill or council tax bill from the last 3 months"},
            {"name": "employment_letter", "description": "Letter from employer confirming role and salary"},
        ],
    },
    "files": [
        {
            "path": "/docs/my_passport.jpg",
            "ext": ".jpg",
            "classification": "passport",
            "extracted_fields": {
                "mrz_type": "P",
                "name": "JANE",
                "surname": "DOE",
                "dob": "900722",
                "expiry": "290415",
                "number": "CD9876543",
                "nationality": "GBR",
            },
            "text_excerpt": "PASSPORT P GBR DOE JANE 900722 F 290415 CD9876543",
            "text_length": 50,
            "error": None,
        },
        {
            "path": "/docs/employment_confirmation.pdf",
            "ext": ".pdf",
            "classification": "employment_letter",
            "extracted_fields": {},
            "text_excerpt": "TechStart Ltd\nShoreditch, London\n\nTo Whom It May Concern\n\nWe hereby confirm that Jane Doe is employed as a Product Manager. Her annual salary is £72,000. She has been in this position since March 2021.",
            "text_length": 280,
            "error": None,
        },
    ],
    "ground_truth": {
        "matched": [
            {"requirement": "passport", "file": "/docs/my_passport.jpg"},
            {"requirement": "employment_letter", "file": "/docs/employment_confirmation.pdf"},
        ],
        "missing": ["bank_statement", "proof_of_address"],
        "conflicts_resolved": [],
        "validation_warnings": [],
    },
}


# ---------------------------------------------------------------------------
# Scenario 3: Conflicting documents — two passports, one expired
# ---------------------------------------------------------------------------
CONFLICTS = {
    "name": "conflicts",
    "description": "Two passports found: one expired, one valid. Model should pick the valid one.",
    "requirements": {
        "visa_type": "UK Standard Visitor",
        "documents": [
            {"name": "passport", "description": "Valid passport with at least 6 months remaining"},
            {"name": "bank_statement", "description": "Bank statement from the last 3 months"},
        ],
    },
    "files": [
        {
            "path": "/docs/old_passport.jpg",
            "ext": ".jpg",
            "classification": "passport",
            "extracted_fields": {
                "mrz_type": "P",
                "name": "ALEX",
                "surname": "TAYLOR",
                "dob": "880110",
                "expiry": "230501",
                "number": "EF1111111",
                "nationality": "GBR",
            },
            "text_excerpt": "PASSPORT P GBR TAYLOR ALEX 880110 M 230501 EF1111111 DATE OF EXPIRY 01 MAY 2023",
            "text_length": 80,
            "error": None,
        },
        {
            "path": "/docs/new_passport.jpg",
            "ext": ".jpg",
            "classification": "passport",
            "extracted_fields": {
                "mrz_type": "P",
                "name": "ALEX",
                "surname": "TAYLOR",
                "dob": "880110",
                "expiry": "330501",
                "number": "EF2222222",
                "nationality": "GBR",
            },
            "text_excerpt": "PASSPORT P GBR TAYLOR ALEX 880110 M 330501 EF2222222 DATE OF EXPIRY 01 MAY 2033",
            "text_length": 80,
            "error": None,
        },
        {
            "path": "/docs/barclays_statement.pdf",
            "ext": ".pdf",
            "classification": "bank_statement",
            "extracted_fields": {},
            "text_excerpt": "Barclays Bank UK PLC\nStatement of Account\nAccount Number: 20456789\nSort Code: 20-00-00\nStatement Period: 01 Feb 2026 - 28 Feb 2026\nOpening Balance: £5,800.00\nClosing Balance: £6,230.40",
            "text_length": 950,
            "error": None,
        },
    ],
    "ground_truth": {
        "matched": [
            {"requirement": "passport", "file": "/docs/new_passport.jpg"},
            {"requirement": "bank_statement", "file": "/docs/barclays_statement.pdf"},
        ],
        "missing": [],
        # We just check that conflicts_resolved is non-empty for this scenario
        "conflicts_resolved": ["_non_empty_"],
        "validation_warnings": [],
    },
}


# ---------------------------------------------------------------------------
# Scenario 4: Bad classification — a document is misclassified by Day 1,
#              the LLM should flag it via validation_warnings
# ---------------------------------------------------------------------------
BAD_CLASSIFICATION = {
    "name": "bad_classification",
    "description": "An employment letter is misclassified as a bank statement. Model should flag the mismatch.",
    "requirements": {
        "visa_type": "UK Standard Visitor",
        "documents": [
            {"name": "passport", "description": "Valid passport with at least 6 months remaining"},
            {"name": "bank_statement", "description": "Bank statement from the last 3 months"},
            {"name": "employment_letter", "description": "Letter from employer confirming role and salary"},
        ],
    },
    "files": [
        {
            "path": "/docs/passport_scan.jpg",
            "ext": ".jpg",
            "classification": "passport",
            "extracted_fields": {
                "mrz_type": "P",
                "name": "SARAH",
                "surname": "CONNOR",
                "dob": "850612",
                "expiry": "290101",
                "number": "GH5555555",
                "nationality": "GBR",
            },
            "text_excerpt": "PASSPORT P GBR CONNOR SARAH 850612 F 290101 GH5555555",
            "text_length": 53,
            "error": None,
        },
        {
            "path": "/docs/employer_letter.pdf",
            "ext": ".pdf",
            "classification": "bank_statement",  # WRONG — this is actually an employment letter
            "extracted_fields": {},
            "text_excerpt": "Cyberdyne Systems\nLos Angeles, CA\n\nTo Whom It May Concern\n\nWe hereby confirm that Sarah Connor is employed as a Security Consultant. Her annual salary is $95,000. She has held this position since June 2022.",
            "text_length": 290,
            "error": None,
        },
    ],
    "ground_truth": {
        "matched": [
            {"requirement": "passport", "file": "/docs/passport_scan.jpg"},
            # The employment letter should still match employment_letter if the model
            # sees through the bad classification, OR it might match bank_statement
            # based on the classification. Either way we mainly care about the warning.
            {"requirement": "employment_letter", "file": "/docs/employer_letter.pdf"},
        ],
        "missing": ["bank_statement"],
        "conflicts_resolved": [],
        # We check that validation_warnings is non-empty
        "validation_warnings": ["_non_empty_"],
    },
}


# ---------------------------------------------------------------------------
# Scenario 5: Noisy OCR — garbled text from low-quality scans
# ---------------------------------------------------------------------------
NOISY_OCR = {
    "name": "noisy_ocr",
    "description": "Documents with realistic OCR noise (garbled chars, partial reads). Tests model robustness.",
    "requirements": {
        "visa_type": "UK Standard Visitor",
        "documents": [
            {"name": "passport", "description": "Valid passport with at least 6 months remaining"},
            {"name": "bank_statement", "description": "Bank statement from the last 3 months"},
            {"name": "employment_letter", "description": "Letter from employer confirming role and salary"},
        ],
    },
    "files": [
        {
            "path": "/docs/passport_blurry.jpg",
            "ext": ".jpg",
            "classification": "passport",
            "extracted_fields": {
                "mrz_type": "P",
                "name": "MICHAEL",
                "surname": "CHEN",
                "dob": "910203",
                "expiry": "290815",
                "number": "JK3456789",
                "nationality": "GBR",
            },
            "text_excerpt": "PA55PORT P< GBR CHEN<<MICHA3L 9l0203 M 290815 JK34S6789 UNITEO KINGOOM",
            "text_length": 70,
            "error": None,
        },
        {
            "path": "/docs/bank_scan_low_res.pdf",
            "ext": ".pdf",
            "classification": "bank_statement",
            "extracted_fields": {},
            "text_excerpt": "H5BC UK\nStaternent of Acc0unt\nAccount Nurnber: 9876S432\nSort C0de: 40-0l-02\nStaternent Peri0d: 01 Feb 2026 - 28 Feb 2026\n0pening Ba1ance: £2,l00.00\nCl0sing Ba1ance: £3,450.20\nTransacti0n detai1s...",
            "text_length": 1100,
            "error": None,
        },
        {
            "path": "/docs/employer_fax.pdf",
            "ext": ".pdf",
            "classification": "employment_letter",
            "extracted_fields": {},
            "text_excerpt": "Gl0balTech Lfd\nl0 Baker Sfreet, Lond0n\n\nT0 Wh0m lt May C0ncern\n\nThis 1etter is to c0nfirm that Michae1 Chen has been emp1oyed as a Data Scientist since March 2019. His annua1 sa1ary is £58,000.\n\nY0urs faithfu11y,\nHR Deparfment",
            "text_length": 310,
            "error": None,
        },
    ],
    "ground_truth": {
        "matched": [
            {"requirement": "passport", "file": "/docs/passport_blurry.jpg"},
            {"requirement": "bank_statement", "file": "/docs/bank_scan_low_res.pdf"},
            {"requirement": "employment_letter", "file": "/docs/employer_fax.pdf"},
        ],
        "missing": [],
        "conflicts_resolved": [],
        "validation_warnings": [],
    },
}


# ---------------------------------------------------------------------------
# Scenario 6: Extra documents — more files than requirements
# ---------------------------------------------------------------------------
EXTRA_DOCUMENTS = {
    "name": "extra_documents",
    "description": "6 files for 3 requirements. Model must match correctly and ignore irrelevant docs.",
    "requirements": {
        "visa_type": "UK Standard Visitor",
        "documents": [
            {"name": "passport", "description": "Valid passport with at least 6 months remaining"},
            {"name": "bank_statement", "description": "Bank statement from the last 3 months"},
            {"name": "employment_letter", "description": "Letter from employer confirming role and salary"},
        ],
    },
    "files": [
        {
            "path": "/docs/passport_scan.jpg",
            "ext": ".jpg",
            "classification": "passport",
            "extracted_fields": {
                "mrz_type": "P",
                "name": "EMMA",
                "surname": "WILSON",
                "dob": "880930",
                "expiry": "310601",
                "number": "LM7777777",
                "nationality": "GBR",
            },
            "text_excerpt": "PASSPORT P GBR WILSON EMMA 880930 F 310601 LM7777777",
            "text_length": 52,
            "error": None,
        },
        {
            "path": "/docs/natwest_march.pdf",
            "ext": ".pdf",
            "classification": "bank_statement",
            "extracted_fields": {},
            "text_excerpt": "NatWest Bank\nStatement of Account\nAccount Number: 55667788\nSort Code: 60-10-20\nStatement Period: 01 Mar 2026 - 31 Mar 2026\nOpening Balance: £7,200.00\nClosing Balance: £8,100.50",
            "text_length": 980,
            "error": None,
        },
        {
            "path": "/docs/offer_letter.pdf",
            "ext": ".pdf",
            "classification": "employment_letter",
            "extracted_fields": {},
            "text_excerpt": "DataDriven Ltd\nCanary Wharf, London\n\nTo Whom It May Concern\n\nWe hereby confirm that Emma Wilson is employed as a Senior Analyst. Her annual salary is £78,000. She has been in this role since September 2021.",
            "text_length": 295,
            "error": None,
        },
        # --- Extra / irrelevant documents below ---
        {
            "path": "/docs/old_council_tax.pdf",
            "ext": ".pdf",
            "classification": "proof_of_address",
            "extracted_fields": {},
            "text_excerpt": "London Borough of Camden\nCouncil Tax Bill 2024-2025\nProperty: 42 Elm Road, London NW3 4QP\nAmount due: £1,850.00",
            "text_length": 450,
            "error": None,
        },
        {
            "path": "/docs/holiday_photo.jpg",
            "ext": ".jpg",
            "classification": "unknown",
            "extracted_fields": {},
            "text_excerpt": "",
            "text_length": 0,
            "error": "No text detected in image",
        },
        {
            "path": "/docs/driving_licence.jpg",
            "ext": ".jpg",
            "classification": "unknown",
            "extracted_fields": {},
            "text_excerpt": "DRIVING LICENCE DVLA WILSON EMMA 88 09 30 ISSUED 2022 VALID TO 2032",
            "text_length": 67,
            "error": None,
        },
    ],
    "ground_truth": {
        "matched": [
            {"requirement": "passport", "file": "/docs/passport_scan.jpg"},
            {"requirement": "bank_statement", "file": "/docs/natwest_march.pdf"},
            {"requirement": "employment_letter", "file": "/docs/offer_letter.pdf"},
        ],
        "missing": [],
        "conflicts_resolved": [],
        "validation_warnings": [],
    },
}


ALL_SCENARIOS = [
    HAPPY_PATH,
    MISSING_DOCS,
    CONFLICTS,
    BAD_CLASSIFICATION,
    NOISY_OCR,
    EXTRA_DOCUMENTS,
]
