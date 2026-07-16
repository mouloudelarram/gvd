import shutil
import subprocess
from pathlib import Path
import re

from network_config import git_environment


BASE_DIR = Path(__file__).resolve().parent
REPOS_DIR = BASE_DIR / "repos"
WINDOWS_CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)


def sanitize_path_component(component: str) -> str:
    """Sanitize a path component to prevent directory traversal."""
    if not component:
        raise ValueError("Path component cannot be empty")
    
    # Remove dangerous characters and path traversal attempts
    component = component.replace("..", "").replace("~", "")
    # Keep only alphanumeric, hyphens, underscores, and dots
    component = re.sub(r'[^a-zA-Z0-9\-_.]', '_', component)
    
    if not component or component in (".", ".."):
        raise ValueError(f"Invalid path component: {component}")
    
    return component


def build_clone_url(clone_url, token):
    """Build HTTPS clone URL with embedded token (safely)."""
    if not clone_url:
        raise ValueError("Clone URL cannot be empty")
    
    prefix = "https://"
    if not clone_url.startswith(prefix):
        raise ValueError("Only HTTPS clone URLs are supported.")
    
    # Validate that it looks like a GitHub URL
    if "github.com" not in clone_url.lower():
        raise ValueError("Only GitHub clone URLs are supported.")
    
    return f"{prefix}x-access-token:{token}@{clone_url[len(prefix):]}"


def clone_repos(repos, token):
    """Clone multiple repositories."""
    REPOS_DIR.mkdir(exist_ok=True)
    total = len(repos)
    for index, repo in enumerate(repos, start=1):
        name = (repo.get("name") or "").strip()
        clone_url = repo.get("clone_url") or ""
        username = ((repo.get("owner") or {}).get("login") or "").strip()
        
        if not name or not clone_url or not username:
            print(f"[{index}/{total}] Skipping: invalid repo data")
            continue
        
        try:
            # Sanitize path components to prevent traversal
            safe_username = sanitize_path_component(username)
            safe_name = sanitize_path_component(name)
        except ValueError as e:
            print(f"[{index}/{total}] Skipping {username}/{name}: {e}")
            continue
        
        user_dir = REPOS_DIR / safe_username
        user_dir.mkdir(exist_ok=True)
        target_dir = user_dir / safe_name
        
        if target_dir.exists():
            print(f"[{index}/{total}] Skipping: {safe_username}/{safe_name} already exists")
            continue
        
        print(f"[{index}/{total}] Cloning: {safe_username}/{safe_name}")
        try:
            auth_url = build_clone_url(clone_url, token)
            subprocess.run(
                ["git", "clone", "--depth", "1", auth_url, str(target_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
                env=git_environment(),
            )
        except subprocess.TimeoutExpired:
            print(f"[{index}/{total}] Timeout cloning {safe_username}/{safe_name}")
            if target_dir.exists():
                shutil.rmtree(target_dir)
        except subprocess.CalledProcessError as e:
            print(f"[{index}/{total}] Failed to clone {safe_username}/{safe_name}")
            # Sanitize token from error output
            error_msg = (e.stderr or "").replace(token, "[redacted]")
            if error_msg:
                print(f"  Error: {error_msg.strip()}")
            if target_dir.exists():
                shutil.rmtree(target_dir)


def ensure_repo_cloned(repo, token, process_callback=None):
    """Ensure a repository is cloned, return path to clone."""
    name = (repo.get("name") or "").strip()
    clone_url = repo.get("clone_url") or ""
    username = ((repo.get("owner") or {}).get("login") or "").strip()
    
    if not name or not clone_url or not username:
        raise ValueError("Invalid repo data: missing name, clone_url, or owner login")
    
    try:
        # Sanitize path components
        safe_username = sanitize_path_component(username)
        safe_name = sanitize_path_component(name)
    except ValueError as e:
        raise ValueError(f"Invalid repository name: {e}")
    
    REPOS_DIR.mkdir(exist_ok=True)
    user_dir = REPOS_DIR / safe_username
    user_dir.mkdir(exist_ok=True)
    target_dir = user_dir / safe_name
    
    # If directory exists and is a valid git repo, return it
    if target_dir.exists():
        git_dir = target_dir / ".git"
        if git_dir.exists():
            return target_dir
        # If it exists but isn't a git repo, remove it
        shutil.rmtree(target_dir)
    
    # Clone the repository
    auth_url = build_clone_url(clone_url, token)
    process = subprocess.Popen(
        ["git", "clone", "--depth", "1", auth_url, str(target_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=WINDOWS_CREATION_FLAGS,
        env=git_environment(),
    )
    
    if process_callback:
        process_callback(process)
    
    try:
        # Use polling to allow checking if process should be terminated
        import time
        poll_timeout = 300  # 5 minutes total
        chunk_timeout = 2   # Check every 2 seconds
        elapsed = 0
        
        while elapsed < poll_timeout:
            try:
                stdout, stderr = process.communicate(timeout=chunk_timeout)
                # Process completed successfully
                break
            except subprocess.TimeoutExpired:
                # Check if process is still running
                if process.poll() is not None:
                    # Process has finished
                    stdout, stderr = process.communicate()
                    break
                elapsed += chunk_timeout
                # Continue polling - this allows other threads to kill the process if needed
                continue
        else:
            # Timeout occurred
            process.kill()
            process.communicate()
            if target_dir.exists():
                shutil.rmtree(target_dir)
            raise RuntimeError(f"Clone operation timed out for {safe_username}/{safe_name}")
            
    except subprocess.TimeoutExpired:
        process.kill()
        process.communicate()
        if target_dir.exists():
            shutil.rmtree(target_dir)
        raise RuntimeError(f"Clone operation timed out for {safe_username}/{safe_name}")
    
    if process.returncode != 0:
        if target_dir.exists():
            shutil.rmtree(target_dir)
        # Sanitize token from error messages
        error_msg = (stderr or "").replace(token, "[redacted]")
        raise subprocess.CalledProcessError(
            process.returncode,
            process.args,
            output=stdout,
            stderr=error_msg,
        )
    
    return target_dir

