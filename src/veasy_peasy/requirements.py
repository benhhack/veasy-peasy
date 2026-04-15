from pathlib import Path

import yaml


def load_requirements(path: Path) -> dict:
    """Load and validate a requirements YAML file."""
    data = yaml.safe_load(path.read_text())
    if not isinstance(data, dict):
        raise ValueError(f"Requirements file must be a YAML mapping, got {type(data).__name__}")
    if "visa_type" not in data or not isinstance(data["visa_type"], str):
        raise ValueError("Requirements must have a 'visa_type' string field")
    if "documents" not in data or not isinstance(data["documents"], list):
        raise ValueError("Requirements must have a 'documents' list field")
    return data
