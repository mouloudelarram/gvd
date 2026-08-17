"""Observability primitives for GVD (F-16).

This module is intentionally dependency-free so it can run everywhere the app
runs (including hosts where new packages cannot be installed). It provides:

* Structured JSON logging for production and human-readable logging for dev,
  with automatic redaction of credentials/tokens.
* A tiny thread-safe metrics registry that renders the Prometheus text
  exposition format, exposed by the app at ``/metrics``.

Nothing here stores personal data or secrets; log records are scrubbed by a
regex-based redactor before formatting.
"""

from __future__ import annotations

import json
import logging
import os
import re
import threading
import time
from typing import Dict, Iterable, Tuple

# --------------------------------------------------------------------------- #
# Redaction
# --------------------------------------------------------------------------- #

# Patterns that must never reach a log sink. Keep these conservative: match the
# credential shape, not arbitrary text, to avoid corrupting legitimate output.
_REDACTION_PATTERNS = [
    # GitHub tokens: ghp_, gho_, ghu_, ghs_, ghr_ + 36+ base62 chars.
    re.compile(r"\bgh[posur]_[A-Za-z0-9]{20,}\b"),
    # Legacy 40-hex OAuth tokens.
    re.compile(r"\b[0-9a-f]{40}\b"),
    # Authorization: Bearer / token <value>.
    re.compile(r"(?i)\b(bearer|token)\s+[A-Za-z0-9._\-]+"),
    # key/token/secret/password = value  (query-string or kv form).
    re.compile(
        r"(?i)\b(access_token|client_secret|token|secret|password|authorization)\b"
        r"(\s*[=:]\s*)([^\s&'\"]+)"
    ),
    # user:pass@host embedded credentials in URLs.
    re.compile(r"(?i)(https?://)([^/\s:@]+):([^/\s@]+)@"),
]

_REDACTED = "***REDACTED***"


def redact(text: str) -> str:
    """Return ``text`` with any credential-shaped substrings replaced."""
    if not text:
        return text
    out = text
    out = _REDACTION_PATTERNS[0].sub(_REDACTED, out)
    out = _REDACTION_PATTERNS[1].sub(_REDACTED, out)
    out = _REDACTION_PATTERNS[2].sub(lambda m: f"{m.group(1)} {_REDACTED}", out)
    out = _REDACTION_PATTERNS[3].sub(lambda m: f"{m.group(1)}{m.group(2)}{_REDACTED}", out)
    out = _REDACTION_PATTERNS[4].sub(lambda m: f"{m.group(1)}{m.group(2)}:{_REDACTED}@", out)
    return out


# --------------------------------------------------------------------------- #
# Logging
# --------------------------------------------------------------------------- #

_RESERVED = set(
    logging.makeLogRecord({}).__dict__.keys()
) | {"message", "asctime"}


class JsonFormatter(logging.Formatter):
    """Render log records as single-line JSON with redaction."""

    def format(self, record: logging.LogRecord) -> str:
        payload: Dict[str, object] = {
            "ts": time.strftime("%Y-%m-%dT%H:%M:%S", time.gmtime(record.created))
            + f".{int(record.msecs):03d}Z",
            "level": record.levelname,
            "logger": record.name,
            "msg": redact(record.getMessage()),
        }
        # Attach the request correlation id if present.
        cid = getattr(record, "correlation_id", None)
        if cid:
            payload["correlation_id"] = cid
        # Include any structured extras passed via logger(..., extra={...}).
        for key, value in record.__dict__.items():
            if key not in _RESERVED and key != "correlation_id":
                try:
                    json.dumps(value)
                    payload[key] = value
                except (TypeError, ValueError):
                    payload[key] = redact(str(value))
        if record.exc_info:
            payload["exc"] = redact(self.formatException(record.exc_info))
        return json.dumps(payload, ensure_ascii=False)


class RedactingFormatter(logging.Formatter):
    """Human-readable dev formatter that still redacts credentials."""

    def format(self, record: logging.LogRecord) -> str:
        return redact(super().format(record))


def configure_logging(force_json: bool | None = None) -> None:
    """Configure the root logger.

    JSON output in production (``ENVIRONMENT``/``FLASK_ENV`` == ``production``
    or ``LOG_FORMAT`` == ``json``); human-readable otherwise. Idempotent.
    """
    if force_json is None:
        env_prod = (
            os.environ.get("ENVIRONMENT") == "production"
            or os.environ.get("FLASK_ENV") == "production"
        )
        force_json = os.environ.get("LOG_FORMAT", "").lower() == "json" or env_prod

    level_name = os.environ.get("LOG_LEVEL", "INFO").upper()
    level = getattr(logging, level_name, logging.INFO)

    handler = logging.StreamHandler()
    if force_json:
        handler.setFormatter(JsonFormatter())
    else:
        handler.setFormatter(
            RedactingFormatter(
                "%(asctime)s - %(name)s - %(levelname)s - %(message)s"
            )
        )

    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)


# --------------------------------------------------------------------------- #
# Metrics (dependency-free Prometheus text exposition)
# --------------------------------------------------------------------------- #

LabelKey = Tuple[Tuple[str, str], ...]

# Default histogram buckets (seconds) for request/scan durations.
_DEFAULT_BUCKETS = (0.05, 0.1, 0.25, 0.5, 1, 2.5, 5, 10, 30, 60, 300)


class _Metric:
    __slots__ = ("name", "help", "type")

    def __init__(self, name: str, help_text: str, mtype: str) -> None:
        self.name = name
        self.help = help_text
        self.type = mtype


class MetricsRegistry:
    """Minimal thread-safe registry: counters, gauges, histograms."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._meta: Dict[str, _Metric] = {}
        self._counters: Dict[str, Dict[LabelKey, float]] = {}
        self._gauges: Dict[str, Dict[LabelKey, float]] = {}
        # name -> labelkey -> {"buckets": {le: count}, "sum": float, "count": int}
        self._hist: Dict[str, Dict[LabelKey, dict]] = {}
        self._hist_buckets: Dict[str, Tuple[float, ...]] = {}

    # -- registration ----------------------------------------------------- #
    def counter(self, name: str, help_text: str) -> None:
        with self._lock:
            self._meta.setdefault(name, _Metric(name, help_text, "counter"))
            self._counters.setdefault(name, {})

    def gauge(self, name: str, help_text: str) -> None:
        with self._lock:
            self._meta.setdefault(name, _Metric(name, help_text, "gauge"))
            self._gauges.setdefault(name, {})

    def histogram(
        self, name: str, help_text: str, buckets: Iterable[float] = _DEFAULT_BUCKETS
    ) -> None:
        with self._lock:
            self._meta.setdefault(name, _Metric(name, help_text, "histogram"))
            self._hist.setdefault(name, {})
            self._hist_buckets[name] = tuple(sorted(buckets))

    # -- mutation --------------------------------------------------------- #
    @staticmethod
    def _key(labels: Dict[str, str] | None) -> LabelKey:
        if not labels:
            return ()
        return tuple(sorted((str(k), str(v)) for k, v in labels.items()))

    def inc(self, name: str, labels: Dict[str, str] | None = None, amount: float = 1.0) -> None:
        key = self._key(labels)
        with self._lock:
            series = self._counters.setdefault(name, {})
            series[key] = series.get(key, 0.0) + amount

    def set_gauge(self, name: str, value: float, labels: Dict[str, str] | None = None) -> None:
        key = self._key(labels)
        with self._lock:
            self._gauges.setdefault(name, {})[key] = float(value)

    def observe(self, name: str, value: float, labels: Dict[str, str] | None = None) -> None:
        key = self._key(labels)
        buckets = self._hist_buckets.get(name, _DEFAULT_BUCKETS)
        with self._lock:
            series = self._hist.setdefault(name, {})
            entry = series.get(key)
            if entry is None:
                entry = {"buckets": {b: 0 for b in buckets}, "sum": 0.0, "count": 0}
                series[key] = entry
            entry["sum"] += value
            entry["count"] += 1
            for b in buckets:
                if value <= b:
                    entry["buckets"][b] += 1

    # -- rendering -------------------------------------------------------- #
    @staticmethod
    def _fmt_labels(key: LabelKey, extra: Tuple[Tuple[str, str], ...] = ()) -> str:
        items = list(key) + list(extra)
        if not items:
            return ""
        inner = ",".join(f'{k}="{_escape(v)}"' for k, v in items)
        return "{" + inner + "}"

    def render(self) -> str:
        lines = []
        with self._lock:
            for name, meta in sorted(self._meta.items()):
                lines.append(f"# HELP {name} {meta.help}")
                lines.append(f"# TYPE {name} {meta.type}")
                if meta.type == "counter":
                    for key, val in sorted(self._counters.get(name, {}).items()):
                        lines.append(f"{name}{self._fmt_labels(key)} {_num(val)}")
                elif meta.type == "gauge":
                    for key, val in sorted(self._gauges.get(name, {}).items()):
                        lines.append(f"{name}{self._fmt_labels(key)} {_num(val)}")
                elif meta.type == "histogram":
                    for key, entry in sorted(self._hist.get(name, {}).items()):
                        cumulative = 0
                        for b in self._hist_buckets.get(name, _DEFAULT_BUCKETS):
                            cumulative = entry["buckets"][b]
                            lines.append(
                                f"{name}_bucket"
                                f"{self._fmt_labels(key, (('le', _num(b)),))} {cumulative}"
                            )
                        lines.append(
                            f"{name}_bucket"
                            f"{self._fmt_labels(key, (('le', '+Inf'),))} {entry['count']}"
                        )
                        lines.append(f"{name}_sum{self._fmt_labels(key)} {_num(entry['sum'])}")
                        lines.append(f"{name}_count{self._fmt_labels(key)} {entry['count']}")
        return "\n".join(lines) + "\n"


def _escape(value: str) -> str:
    return value.replace("\\", "\\\\").replace('"', '\\"').replace("\n", "\\n")


def _num(value: float) -> str:
    if isinstance(value, float) and value.is_integer():
        return str(int(value))
    return repr(value)


# --------------------------------------------------------------------------- #
# Shared registry + standard metric definitions
# --------------------------------------------------------------------------- #

registry = MetricsRegistry()

registry.counter("gvd_http_requests_total", "Total HTTP requests by method/path/status.")
registry.histogram("gvd_http_request_duration_seconds", "HTTP request latency in seconds.")
registry.counter("gvd_github_api_calls_total", "GitHub API calls by outcome.")
registry.counter("gvd_scans_total", "Scan executions by outcome.")
registry.histogram("gvd_scan_duration_seconds", "Scan duration in seconds.")
registry.counter("gvd_findings_total", "Findings discovered by severity.")
registry.counter("gvd_job_retries_total", "Scan job retries.")
registry.gauge("gvd_queue_depth", "Number of scan jobs waiting in the queue.")


def observe_http_request(method: str, path: str, status: int, duration: float) -> None:
    labels = {"method": method, "path": path, "status": str(status)}
    registry.inc("gvd_http_requests_total", labels)
    registry.observe("gvd_http_request_duration_seconds", duration, {"method": method, "path": path})


def observe_github_call(outcome: str) -> None:
    registry.inc("gvd_github_api_calls_total", {"outcome": outcome})


def observe_scan(outcome: str, duration: float | None = None) -> None:
    registry.inc("gvd_scans_total", {"outcome": outcome})
    if duration is not None:
        registry.observe("gvd_scan_duration_seconds", duration)


def observe_findings(severity: str, count: int = 1) -> None:
    if count:
        registry.inc("gvd_findings_total", {"severity": severity}, amount=float(count))


def observe_retry() -> None:
    registry.inc("gvd_job_retries_total")


def set_queue_depth(value: int) -> None:
    registry.set_gauge("gvd_queue_depth", float(value))


def render_metrics() -> str:
    return registry.render()

