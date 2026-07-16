"""Tests for enterprise GitHub network configuration."""

import os

from network_config import configure_github_network, git_environment


def test_pac_mode_adds_github_without_removing_existing_no_proxy(monkeypatch):
    monkeypatch.setenv("GITHUB_FOLLOW_WINDOWS_PAC", "true")
    monkeypatch.setenv("HTTP_PROXY", "http://127.0.0.1:3128")
    monkeypatch.setenv("HTTPS_PROXY", "http://127.0.0.1:3128")
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("no_proxy", "localhost")

    configure_github_network()

    assert os.environ["HTTP_PROXY"] == "http://127.0.0.1:3128"
    assert "localhost" in os.environ["NO_PROXY"]
    assert "github.com" in os.environ["NO_PROXY"]
    assert "api.github.com" in os.environ["NO_PROXY"]
    assert "github.com" in os.environ["no_proxy"]


def test_disabled_pac_mode_does_not_change_no_proxy(monkeypatch):
    monkeypatch.setenv("GITHUB_FOLLOW_WINDOWS_PAC", "false")
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("no_proxy", "localhost")

    configure_github_network()

    assert os.environ["NO_PROXY"] == "localhost"
    assert os.environ["no_proxy"] == "localhost"


def test_git_environment_is_a_copy_with_github_exception(monkeypatch):
    monkeypatch.setenv("GITHUB_FOLLOW_WINDOWS_PAC", "true")
    monkeypatch.setenv("NO_PROXY", "localhost")
    monkeypatch.setenv("no_proxy", "localhost")

    environment = git_environment()

    assert environment is not os.environ
    assert "github.com" in environment["NO_PROXY"]
    proxy_bypass = environment.get("no_proxy", environment.get("NO_PROXY", ""))
    assert "github.com" in proxy_bypass


