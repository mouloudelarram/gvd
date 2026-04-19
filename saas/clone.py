import shutil
import subprocess
from pathlib import Path


BASE_DIR = Path(__file__).resolve().parent
REPOS_DIR = BASE_DIR / "repos"


def build_clone_url(clone_url, token):
    prefix = "https://"
    if not clone_url.startswith(prefix):
        raise ValueError("Only HTTPS clone URLs are supported.")
    return f"{prefix}x-access-token:{token}@{clone_url[len(prefix):]}"


def clone_repos(repos, token):
    REPOS_DIR.mkdir(exist_ok=True)
    total = len(repos)
    for index, repo in enumerate(repos, start=1):
        name = (repo.get("name") or "").strip()
        clone_url = repo.get("clone_url") or ""
        username = ((repo.get("owner") or {}).get("login") or "").strip()
        if not name or not clone_url or not username:
            print(f"skipping {index}/{total}: invalid repo data")
            continue
        user_dir = REPOS_DIR / Path(username).name
        user_dir.mkdir(exist_ok=True)
        target_dir = user_dir / Path(name).name
        if target_dir.exists():
            print(f"skipping {index}/{total}: {username}/{name} already exists")
            continue
        print(f"cloning {index}/{total}: {username}/{name}")
        try:
            subprocess.run(
                ["git", "clone", "--depth", "1", build_clone_url(clone_url, token), str(target_dir)],
                check=True,
                capture_output=True,
                text=True,
            )
        except subprocess.CalledProcessError as e:
            print(f"failed to clone {username}/{name}")
            if e.stderr:
                print(e.stderr.strip().replace(token, "[redacted]"))


def ensure_repo_cloned(repo, token):
    name = (repo.get("name") or "").strip()
    clone_url = repo.get("clone_url") or ""
    username = ((repo.get("owner") or {}).get("login") or "").strip()
    if not name or not clone_url or not username:
        raise ValueError("Invalid repo data.")

    REPOS_DIR.mkdir(exist_ok=True)
    user_dir = REPOS_DIR / Path(username).name
    user_dir.mkdir(exist_ok=True)
    target_dir = user_dir / Path(name).name

    if target_dir.exists():
        git_dir = target_dir / ".git"
        if git_dir.exists():
            return target_dir
        shutil.rmtree(target_dir)

    subprocess.run(
        ["git", "clone", "--depth", "1", build_clone_url(clone_url, token), str(target_dir)],
        check=True,
        capture_output=True,
        text=True,
    )
    return target_dir
