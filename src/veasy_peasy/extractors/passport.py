import logging
from pathlib import Path

logger = logging.getLogger(__name__)


def try_passport(path: Path) -> dict | None:
    """Attempt to extract MRZ data from a passport image. Returns dict or None."""
    from passporteye import read_mrz

    try:
        mrz = read_mrz(str(path))
        if mrz is None:
            return None
        mrz_data = mrz.to_dict()
        return {
            "mrz_type": mrz_data.get("type", ""),
            "name": mrz_data.get("names", ""),
            "surname": mrz_data.get("surname", ""),
            "dob": mrz_data.get("date_of_birth", ""),
            "expiry": mrz_data.get("expiration_date", ""),
            "number": mrz_data.get("personal_number", mrz_data.get("document_number", "")),
            "nationality": mrz_data.get("nationality", ""),
        }
    except Exception as e:
        logger.debug("MRZ extraction failed for %s: %s", path, e)
        return None
