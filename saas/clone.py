import base64
import os
import re
import shutil
import subprocess
from pathlib import Path
from urllib.parse import urlsplit

from network_config import git_environment


BASE_DIR = Path(__file__).resolve().parent
REPOS_DIR = BASE_DIR / "repos"
WINDOWS_CREATION_FLAGS = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)

# GitHub repository and owner names use this character set. Anything else is
# rejected rather than silently rewritten, so that path components cannot be
# used for directory traversal or collision attacks.
_VALID_COMPONENT = re.compile(r"^[A-Za-z0-9][A-Za-z0-9._-]*$")
_DEFAULT_ALLOWED_CLONE_HOSTS = ("github.com", "www.github.com")


def sanitize_path_component(component: str) -> str:
    """Validate a single path component (owner or repo name).

    Rejects (raises ``ValueError``) empty values, ``.``/``..``, path separators,
    and any character outside the GitHub-safe allow-list. Returns the value
    unchanged when valid. This is strict-by-design: silent rewriting could map
    two distinct repositories onto the same on-disk path.
    """
    if not component:
        raise ValueError("Path component cannot be empty")
    if component in (".", ".."):
        raise ValueError(f"Invalid path component: {component!r}")
    if "/" in component or "\\" in component or "\x00" in component:
        raise ValueError(f"Path component must not contain separators: {component!r}")
    if not _VALID_COMPONENT.match(component):
        raise ValueError(f"Invalid characters in path component: {component!r}")
    return component


def _allowed_clone_hosts() -> set:
    """Approved GitHub hosts (exact hostname match), configurable for GHE."""
    configured = os.environ.get("GITHUB_ALLOWED_CLONE_HOSTS", "")
    hosts = {host.strip().lower() for host in configured.split(",") if host.strip()}
    hosts.update(_DEFAULT_ALLOWED_CLONE_HOSTS)
    return hosts


def validate_github_clone_url(clone_url: str) -> str:
    """Validate and normalize a clone URL to an approved GitHub HTTPS URL.

    Uses a parsed hostname (not a substring check) and rejects embedded
    credentials, non-HTTPS schemes, and non-approved hosts. Returns a clean URL
    with no userinfo/query/fragment so no secret can be smuggled into ``argv``.
    """
    if not clone_url:
        raise ValueError("Clone URL cannot be empty")

    parts = urlsplit(clone_url.strip())
    if parts.scheme != "https":
        raise ValueError("Only HTTPS clone URLs are supported.")
    if parts.username or parts.password:
        raise ValueError("Clone URL must not contain embedded credentials.")

    host = (parts.hostname or "").lower()
    if host not in _allowed_clone_hosts():
        raise ValueError(f"Clone host '{host}' is not an approved GitHub host.")

    return f"https://{host}{parts.path}"


def git_auth_env(clone_url: str, token: str) -> dict:
    """Return a git environment that authenticates via an HTTP header.

    The token is injected through ``GIT_CONFIG_*`` environment variables
    (an ``http.<origin>.extraHeader`` entry), never via the command line or the
    clone URL, so it cannot leak through process listings. Falls back to the
    plain environment when no token is supplied.
    """
    env = git_environment()
    env["GIT_TERMINAL_PROMPT"] = "0"  # never block on an interactive credential prompt
    if not token:
        return env

    parts = urlsplit(clone_url)
    origin = f"https://{(parts.hostname or '').lower()}/"
    basic = base64.b64encode(f"x-access-token:{token}".encode()).decode()

    env["GIT_CONFIG_COUNT"] = "1"
    env["GIT_CONFIG_KEY_0"] = f"http.{origin}.extraheader"
    env["GIT_CONFIG_VALUE_0"] = f"Authorization: Basic {basic}"
    return env


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
            safe_url = validate_github_clone_url(clone_url)
            subprocess.run(
                ["git", "clone", "--depth", "1", safe_url, str(target_dir)],
                check=True,
                capture_output=True,
                text=True,
                timeout=300,
                env=git_auth_env(safe_url, token),
            )
        except ValueError as e:
            print(f"[{index}/{total}] Skipping {safe_username}/{safe_name}: {e}")
            continue
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
    safe_url = validate_github_clone_url(clone_url)
    process = subprocess.Popen(
        ["git", "clone", "--depth", "1", safe_url, str(target_dir)],
        stdout=subprocess.PIPE,
        stderr=subprocess.PIPE,
        text=True,
        creationflags=WINDOWS_CREATION_FLAGS,
        env=git_auth_env(safe_url, token),
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

