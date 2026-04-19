import re
from typing import List, Dict, Pattern
from cli.core.models import Severity

class PatternEngine:
    def __init__(self):
        self.patterns: Dict[str, Dict] = {
            "aws_key": {
                "regex": r"AKIA[0-9A-Z]{16}",
                "severity": Severity.CRITICAL,
                "fix": "Rotate AWS credentials immediately"
            },
            "generic_api_key": {
                "regex": r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
                "severity": Severity.HIGH,
                "fix": "Rotate API key and review usage"
            },
            "token": {
                "regex": r"token\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
                "severity": Severity.HIGH,
                "fix": "Rotate token and check for exposure"
            },
            "secret": {
                "regex": r"secret\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
                "severity": Severity.HIGH,
                "fix": "Remove secret from repository"
            },
            "database_url": {
                "regex": r"DATABASE_URL\s*[:=]\s*['\"]?[^\s'\"]*:[^\s'\"]*@[^\s'\"]*['\"]?",
                "severity": Severity.CRITICAL,
                "fix": "Rotate database credentials"
            },
            "private_key": {
                "regex": r"-----BEGIN PRIVATE KEY-----",
                "severity": Severity.CRITICAL,
                "fix": "Remove private key from repository"
            },
            "password": {
                "regex": r"(password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]+['\"]?",
                "severity": Severity.CRITICAL,
                "fix": "Change password immediately"
            }
        }

    def get_combined_regex(self) -> str:
        """Combine all patterns into one regex with named groups."""
        parts = []
        for name, data in self.patterns.items():
            parts.append(f"(?P<{name}>{data['regex']})")
        return "|".join(parts)

    def match_pattern(self, content: str) -> List[Dict]:
        """Find all matches in content."""
        combined = self.get_combined_regex()
        pattern = re.compile(combined, re.IGNORECASE)
        matches = []
        for match in pattern.finditer(content):
            for name, group in match.groupdict().items():
                if group:
                    matches.append({
                        "type": name,
                        "content": group,
                        "severity": self.patterns[name]["severity"],
                        "fix": self.patterns[name]["fix"]
                    })
        return matches