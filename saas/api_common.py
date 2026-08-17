"""Shared helpers for the versioned HTTP API (/api/v1) — F-13.

Provides a consistent JSON error envelope that always carries the request
correlation id, plus a tiny dependency-free request validator.
"""

from flask import g, jsonify


def _correlation_id():
    return getattr(g, "correlation_id", None)


def api_error(code, message, status, details=None):
    """Return a consistent error envelope response.

    Shape: {"error": {"code","message","correlation_id","details"?}}
    """
    body = {
        "error": {
            "code": code,
            "message": message,
            "correlation_id": _correlation_id(),
        }
    }
    if details:
        body["error"]["details"] = details
    return jsonify(body), status


def validate_scan_request(payload):
    """Validate a POST /api/v1/scans body.

    Returns (data, errors). ``errors`` is a list of {"field","message"} dicts;
    an empty list means the payload is valid and ``data`` is the normalized input.
    """
    errors = []
    if not isinstance(payload, dict):
        return None, [{"field": "body", "message": "JSON object required"}]

    scan_type = str(payload.get("type", "bulk")).strip().lower()
    if scan_type not in {"bulk", "single"}:
        errors.append({"field": "type", "message": "must be 'bulk' or 'single'"})

    data = {"type": scan_type, "idempotency_key": None}

    key = payload.get("idempotency_key")
    if key is not None:
        if not isinstance(key, str) or len(key) > 255:
            errors.append({"field": "idempotency_key", "message": "must be a string <= 255 chars"})
        else:
            data["idempotency_key"] = key.strip() or None

    if scan_type == "bulk":
        visibility = str(payload.get("visibility", "both")).strip().lower()
        if visibility not in {"public", "private", "both"}:
            errors.append({"field": "visibility", "message": "must be public|private|both"})
        data["visibility"] = visibility
    elif scan_type == "single":
        repo = payload.get("repository")
        if not isinstance(repo, dict):
            errors.append({"field": "repository", "message": "object required for single scans"})
        else:
            for field in ("owner", "name", "clone_url"):
                if not str(repo.get(field, "")).strip():
                    errors.append({"field": f"repository.{field}", "message": "required"})
            data["repository"] = repo

    return (None, errors) if errors else (data, [])


def build_openapi_spec():
    """Return the OpenAPI 3 document describing the v1 API (as a dict)."""
    error_schema = {
        "type": "object",
        "properties": {
            "error": {
                "type": "object",
                "properties": {
                    "code": {"type": "string"},
                    "message": {"type": "string"},
                    "correlation_id": {"type": "string", "nullable": True},
                    "details": {"type": "array", "items": {"type": "object"}},
                },
                "required": ["code", "message"],
            }
        },
    }
    job_schema = {
        "type": "object",
        "properties": {
            "id": {"type": "string"},
            "owner_login": {"type": "string"},
            "job_type": {"type": "string"},
            "status": {"type": "string"},
            "total_repositories": {"type": "integer"},
            "scanned_repositories": {"type": "integer"},
            "failed_repositories": {"type": "integer"},
            "report_id": {"type": "string", "nullable": True},
            "created_at": {"type": "string"},
            "updated_at": {"type": "string"},
        },
    }
    return {
        "openapi": "3.0.3",
        "info": {
            "title": "GVD API",
            "version": "1.0.0",
            "description": "GitHub Vulnerability Detector — versioned HTTP API.",
        },
        "servers": [{"url": "/"}],
        "components": {
            "schemas": {"Error": error_schema, "ScanJob": job_schema},
        },
        "paths": {
            "/livez": {
                "get": {
                    "summary": "Liveness probe",
                    "responses": {"200": {"description": "Process is alive"}},
                }
            },
            "/readyz": {
                "get": {
                    "summary": "Readiness probe",
                    "responses": {
                        "200": {"description": "Ready"},
                        "503": {"description": "Database unavailable"},
                    },
                }
            },
            "/api/v1/scans": {
                "post": {
                    "summary": "Create a scan job",
                    "requestBody": {
                        "required": True,
                        "content": {
                            "application/json": {
                                "schema": {
                                    "type": "object",
                                    "properties": {
                                        "type": {"type": "string", "enum": ["bulk", "single"]},
                                        "visibility": {
                                            "type": "string",
                                            "enum": ["public", "private", "both"],
                                        },
                                        "repository": {"type": "object"},
                                        "idempotency_key": {"type": "string"},
                                    },
                                }
                            }
                        },
                    },
                    "responses": {
                        "202": {"description": "Job accepted"},
                        "200": {"description": "Idempotent replay"},
                        "401": {
                            "description": "Unauthorized",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                        "422": {
                            "description": "Validation failed",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/Error"}
                                }
                            },
                        },
                    },
                }
            },
            "/api/v1/jobs": {
                "get": {
                    "summary": "List the current user's scan jobs",
                    "responses": {
                        "200": {
                            "description": "Jobs",
                            "content": {
                                "application/json": {
                                    "schema": {
                                        "type": "object",
                                        "properties": {
                                            "jobs": {
                                                "type": "array",
                                                "items": {
                                                    "$ref": "#/components/schemas/ScanJob"
                                                },
                                            }
                                        },
                                    }
                                }
                            },
                        }
                    },
                }
            },
            "/api/v1/jobs/{job_id}": {
                "get": {
                    "summary": "Fetch a scan job (owner-only)",
                    "parameters": [
                        {
                            "name": "job_id",
                            "in": "path",
                            "required": True,
                            "schema": {"type": "string"},
                        }
                    ],
                    "responses": {
                        "200": {
                            "description": "Job",
                            "content": {
                                "application/json": {
                                    "schema": {"$ref": "#/components/schemas/ScanJob"}
                                }
                            },
                        },
                        "403": {"description": "Not the owner"},
                        "404": {"description": "Not found"},
                    },
                }
            },
        },
    }