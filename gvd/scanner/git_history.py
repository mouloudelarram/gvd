import subprocess
import re
from pathlib import Path
from typing import List, Generator
from gvd.core.models import Finding
from gvd.scanner.pattern_engine import PatternEngine

class GitHistoryScanner:
    def __init__(self, pattern_engine: PatternEngine):
        self.pattern_engine = pattern_engine

    def scan_history(self, repo_path: Path, repo_name: str) -> Generator[Finding, None, None]:
        """Scan git history for patterns using git log -p."""
        cmd = ["git", "log", "-p", "--all", "--full-history", "--no-merges"]
        result = subprocess.run(
            cmd,
            cwd=repo_path,
            capture_output=True,
            text=True,
            check=True,
            errors="replace"
        )
        
        current_commit = None
        current_file = None
        for line in result.stdout.split('\n'):
            if line.startswith('commit '):
                current_commit = line.split()[1]
            elif line.startswith('diff --git'):
                parts = line.split()
                if len(parts) >= 3:
                    current_file = parts[2][2:]  # a/file -> file
            elif line.startswith('+') and not line.startswith('+++') and current_file:
                content = line[1:].strip()
                if content:
                    matches = self.pattern_engine.match_pattern(content)
                    for match in matches:
                        yield Finding(
                            repo_name=repo_name,
                            commit_hash=current_commit,
                            file_path=current_file,
                            line_number=None,
                            secret_type=match["type"],
                            severity=match["severity"],
                            content=content,
                            fix_recommendation=match["fix"]
                        )