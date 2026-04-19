import re
from pathlib import Path
from typing import List, Set
from cli.core.git_utils import run_git_command
from cli.core.models import Severity, Finding

class FileScanner:
    def __init__(self):
        self.sensitive_patterns = [
            r"\.env$",
            r"\.env\..*",
            r"id_rsa$",
            r"id_dsa$",
            r".*\.pem$",
            r".*\.key$",
            r"credentials\.json$",
            r"secrets\.json$",
            r"config\.production\..*"
        ]

    def scan_sensitive_files(self, repo_path: Path, repo_name: str) -> List[Finding]:
        """Scan for sensitive files in git history."""
        findings = []
        # Get all files ever in history
        try:
            output = run_git_command(["log", "--all", "--full-history", "--name-only", "--pretty=format:"], repo_path)
            files = set()
            for line in output.split('\n'):
                line = line.strip()
                if line and not line.startswith('commit '):
                    files.add(line)
            
            for file in files:
                if self._is_sensitive_file(file):
                    # Find the commit that added this file
                    commit = self._find_adding_commit(repo_path, file)
                    if commit:
                        findings.append(Finding(
                            repo_name=repo_name,
                            commit_hash=commit,
                            file_path=file,
                            line_number=None,
                            secret_type="sensitive_file",
                            severity=Severity.HIGH,
                            content=f"Sensitive file: {file}",
                            fix_recommendation="Remove sensitive file from repository history using git filter-repo"
                        ))
        except Exception as e:
            print(f"Error scanning files: {e}")
        return findings

    def _is_sensitive_file(self, filename: str) -> bool:
        """Check if filename matches sensitive patterns."""
        for pattern in self.sensitive_patterns:
            if re.match(pattern, filename, re.IGNORECASE):
                return True
        return False

    def _find_adding_commit(self, repo_path: Path, file: str) -> str:
        """Find the commit that added the file."""
        try:
            output = run_git_command(["log", "--all", "--full-history", "--diff-filter=A", "--pretty=format:%H", "--", file], repo_path)
            commits = output.strip().split('\n')
            return commits[0] if commits and commits[0] else ""
        except:
            return ""