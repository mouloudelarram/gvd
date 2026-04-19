import subprocess
import os
from pathlib import Path
from typing import List, Optional

def run_git_command(command: List[str], cwd: Path) -> str:
    """Run a git command and return stdout."""
    result = subprocess.run(
        ["git"] + command,
        cwd=cwd,
        capture_output=True,
        text=True,
        check=True
    )
    return result.stdout

def is_git_repo(path: Path) -> bool:
    """Check if path is a git repository."""
    try:
        run_git_command(["rev-parse", "--git-dir"], path)
        return True
    except subprocess.CalledProcessError:
        return False

def get_repo_root(path: Path) -> Path:
    """Get the root of the git repository."""
    output = run_git_command(["rev-parse", "--show-toplevel"], path)
    return Path(output.strip())

def get_repo_name(path: Path) -> str:
    """Get repository name from path."""
    root = get_repo_root(path)
    return root.name

def get_all_commits(path: Path) -> List[str]:
    """Get all commit hashes."""
    output = run_git_command(["rev-list", "--all"], path)
    return output.strip().split('\n') if output.strip() else []