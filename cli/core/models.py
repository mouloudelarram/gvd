from dataclasses import dataclass
from typing import Optional
from enum import Enum

class Severity(Enum):
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