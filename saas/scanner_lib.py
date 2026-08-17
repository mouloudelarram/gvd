"""In-process secret/vulnerability scanner (F-19).

Removes the dependency on shelling out to ``cli/cli.py`` (a host-path/prebuilt
coupling that also broke in-container scanning). Produces the same ``report.json``
schema the rest of the app already consumes. Uses the system ``git`` binary
(a standard container dependency), never the Python CLI process.

NOTE (tech debt): the detection rules below intentionally mirror
``cli/scanner/pattern_engine.py``. They should be unified into a single shared
package in a later step; until then, keep the two rule sets in sync.
"""

import json
import re
import subprocess
from datetime import datetime, timezone
from pathlib import Path

# Ordered severity buckets used across reports.
SEVERITY_KEYS = ("CRITICAL", "HIGH", "MEDIUM", "LOW")

PATTERNS = {
    "aws_key": {
        "regex": r"AKIA[0-9A-Z]{16}",
        "severity": "CRITICAL",
        "fix": "Rotate AWS credentials immediately",
    },
    "generic_api_key": {
        "regex": r"api[_-]?key\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
        "severity": "HIGH",
        "fix": "Rotate API key and review usage",
    },
    "token": {
        "regex": r"token\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
        "severity": "HIGH",
        "fix": "Rotate token and check for exposure",
    },
    "secret": {
        "regex": r"secret\s*[:=]\s*['\"]?[A-Za-z0-9_\-]{20,}['\"]?",
        "severity": "HIGH",
        "fix": "Remove secret from repository",
    },
    "database_url": {
        "regex": r"DATABASE_URL\s*[:=]\s*['\"]?[^\s'\"]*:[^\s'\"]*@[^\s'\"]*['\"]?",
        "severity": "CRITICAL",
        "fix": "Rotate database credentials",
    },
    "private_key": {
        "regex": r"-----BEGIN PRIVATE KEY-----",
        "severity": "CRITICAL",
        "fix": "Remove private key from repository",
    },
    "password": {
        "regex": r"(password|passwd|pwd)\s*[:=]\s*['\"]?[^\s'\"]+['\"]?",
        "severity": "CRITICAL",
        "fix": "Change password immediately",
    },
}

_COMBINED_RE = re.compile(
    "|".join(f"(?P<{name}>{data['regex']})" for name, data in PATTERNS.items()),
    re.IGNORECASE,
)


def match_patterns(content: str):
    """Return a list of matches ({type, content, severity, fix}) in ``content``."""
    matches = []
    for match in _COMBINED_RE.finditer(content):
        for name, group in match.groupdict().items():
            if group:
                data = PATTERNS[name]
                matches.append(
                    {
                        "type": name,
                        "content": group,
                        "severity": data["severity"],
                        "fix": data["fix"],
                    }
                )
    return matches


def _run_git(args, cwd, timeout=300):
    """Run a git command in ``cwd`` and return stdout (raises on failure)."""
    result = subprocess.run(
        ["git", *args],
        cwd=str(cwd),
        capture_output=True,
        text=True,
        check=True,
        errors="replace",
        timeout=timeout,
    )
    return result.stdout


def scan_git_history(repo_path, repo_name, timeout=300):
    """Scan added lines across all commit history for secret patterns."""
    output = _run_git(
        ["log", "-p", "--all", "--full-history", "--no-merges"],
        cwd=repo_path,
        timeout=timeout,
    )
    findings = []
    current_commit = None
    current_file = None
    for line in output.split("\n"):
        if line.startswith("commit "):
            parts = line.split()
            current_commit = parts[1] if len(parts) > 1 else None
        elif line.startswith("diff --git"):
            parts = line.split()
            current_file = parts[2][2:] if len(parts) >= 3 else None
        elif line.startswith("+") and not line.startswith("+++") and current_file:
            content = line[1:].strip()
            if not content:
                continue
            for match in match_patterns(content):
                findings.append(
                    {
                        "commit_hash": current_commit,
                        "file_path": current_file,
                        "line_number": None,
                        "secret_type": match["type"],
                        "severity": match["severity"],
                        "content": content,
                        "fix_recommendation": match["fix"],
                    }
                )
    return findings


def build_json_report(findings, repo_name):
    """Build the canonical report dict (same schema as the CLI report builder)."""
    severity_counts = {key: 0 for key in SEVERITY_KEYS}
    for finding in findings:
        sev = finding.get("severity")
        if sev in severity_counts:
            severity_counts[sev] += 1
    return {
        "repo_name": repo_name,
        "scan_date": datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
        "total_findings": len(findings),
        "severity_counts": severity_counts,
        "findings": findings,
    }


def scan_repository(repo_path, repo_name, timeout=300):
    """Scan a cloned repository in-process; return the report dict."""
    findings = scan_git_history(repo_path, repo_name, timeout=timeout)
    return build_json_report(findings, repo_name)


def scan_to_dir(repo_path, output_dir, repo_name, timeout=300):
    """Scan a repository and write ``report.json`` into ``output_dir``.

    Returns the report dict. Mirrors what the CLI subprocess used to produce.
    """
    report = scan_repository(repo_path, repo_name, timeout=timeout)
    output_dir = Path(output_dir)
    output_dir.mkdir(parents=True, exist_ok=True)
    with open(output_dir / "report.json", "w", encoding="utf-8") as report_file:
        json.dump(report, report_file, indent=2)
    return report
