from dataclasses import dataclass
from typing import Optional
from enum import Enum

class Severity(str, Enum):
    """Severity levels.

    Subclasses ``str`` so that members compare by value even when this module is
    imported under two different paths (e.g. ``cli.core.models`` vs ``core.models``).
    This keeps equality checks and JSON serialization stable across entrypoints.
    """
    CRITICAL = "CRITICAL"
    HIGH = "HIGH"
    MEDIUM = "MEDIUM"
    LOW = "LOW"

@dataclass
class Finding:
    repo_name: str
    commit_hash: str
    file_path: str
    line_number: Optional[int]
    secret_type: str
    severity: Severity
    content: str
    fix_recommendation: str