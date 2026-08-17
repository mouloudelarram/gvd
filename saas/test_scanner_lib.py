"""In-process scanner library tests (F-19)."""

import json
import subprocess
from pathlib import Path

import pytest

import scanner_lib


def _git(args, cwd):
    subprocess.run(["git", *args], cwd=str(cwd), check=True, capture_output=True, text=True)


@pytest.fixture
def repo_with_secret(tmp_path):
    repo = tmp_path / "repo"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    # A file containing an AWS access key id (AKIA + 16 upper/alnum).
    (repo / "config.txt").write_text(
        "AWS_ACCESS_KEY_ID=AKIA1234567890ABCDEF\nnothing=here\n", encoding="utf-8"
    )
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "add secret"], repo)
    return repo


def test_match_patterns_detects_aws_key():
    matches = scanner_lib.match_patterns("AKIA1234567890ABCDEF")
    assert any(m["type"] == "aws_key" and m["severity"] == "CRITICAL" for m in matches)


def test_match_patterns_clean_line():
    assert scanner_lib.match_patterns("just a normal line of text") == []


def test_scan_repository_finds_secret(repo_with_secret):
    report = scanner_lib.scan_repository(repo_with_secret, "repo")
    assert report["repo_name"] == "repo"
    assert report["total_findings"] >= 1
    assert report["severity_counts"]["CRITICAL"] >= 1
    types = {f["secret_type"] for f in report["findings"]}
    assert "aws_key" in types


def test_scan_to_dir_writes_report(repo_with_secret, tmp_path):
    out = tmp_path / "out"
    report = scanner_lib.scan_to_dir(repo_with_secret, out, "repo")
    report_path = out / "report.json"
    assert report_path.exists()
    on_disk = json.loads(report_path.read_text(encoding="utf-8"))
    assert on_disk["total_findings"] == report["total_findings"]
    # Schema parity with the rest of the app.
    for key in ("repo_name", "scan_date", "total_findings", "severity_counts", "findings"):
        assert key in on_disk


def test_report_schema_for_clean_repo(tmp_path):
    repo = tmp_path / "clean"
    repo.mkdir()
    _git(["init"], repo)
    _git(["config", "user.email", "t@example.com"], repo)
    _git(["config", "user.name", "Test"], repo)
    (repo / "README.md").write_text("# clean repo\n", encoding="utf-8")
    _git(["add", "-A"], repo)
    _git(["commit", "-m", "init"], repo)

    report = scanner_lib.scan_repository(repo, "clean")
    assert report["total_findings"] == 0
    assert report["severity_counts"] == {"CRITICAL": 0, "HIGH": 0, "MEDIUM": 0, "LOW": 0}


def test_run_repo_scan_inprocess_end_to_end(monkeypatch, tmp_path, repo_with_secret):
    """run_repo_scan uses the in-process scanner and produces a scan result (F-19)."""
    import app as app_module

    monkeypatch.setattr(app_module, "SCANNER_MODE", "inprocess")
    monkeypatch.setattr(app_module, "SCAN_REPORTS_DIR", tmp_path / "reports")
    monkeypatch.setattr(
        app_module, "ensure_repo_cloned",
        lambda repo, token, process_callback=None: repo_with_secret,
    )
    monkeypatch.setattr(app_module, "record_scan_event", lambda *a, **k: None)

    repo = {
        "name": "repo",
        "owner": {"login": "alice"},
        "clone_url": "https://github.com/alice/repo.git",
    }
    result = app_module.run_repo_scan(repo, "token", scanned_by="alice")
    assert result["total_findings"] >= 1
    assert result["severity_counts"]["CRITICAL"] >= 1
    reports = list((tmp_path / "reports").rglob("report.json"))
    assert reports, "report.json should be written"
