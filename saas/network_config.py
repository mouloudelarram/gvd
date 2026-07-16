"""Enterprise network configuration for GitHub HTTPS traffic."""

import os

import truststore


# Requests normally uses certifi, which does not include enterprise CAs installed
# in Windows. Keep TLS verification enabled while trusting the OS certificate store.
truststore.inject_into_ssl()

_GITHUB_NO_PROXY_HOSTS = ("github.com", ".github.com", "api.github.com")
_TRUE_VALUES = {"1", "true", "yes", "on"}


def _is_enabled(name):
    return os.environ.get(name, "false").strip().lower() in _TRUE_VALUES


def configure_github_network():
    """Follow a corporate PAC rule that sends GitHub directly.

    This only bypasses HTTP_PROXY/HTTPS_PROXY for GitHub hosts. It does not
    disable endpoint network controls such as Netskope.
    """
    if not _is_enabled("GITHUB_FOLLOW_WINDOWS_PAC"):
        return

    for variable in ("NO_PROXY", "no_proxy"):
        current = [item.strip() for item in os.environ.get(variable, "").split(",") if item.strip()]
        known = {item.lower() for item in current}
        current.extend(host for host in _GITHUB_NO_PROXY_HOSTS if host.lower() not in known)
        os.environ[variable] = ",".join(current)


def git_environment():
    """Return an environment in which Git follows the same GitHub PAC rule."""
    configure_github_network()
    return os.environ.copy()

