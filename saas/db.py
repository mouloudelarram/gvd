"""Persistence foundation for the GVD SaaS service.

Uses SQLAlchemy 2.0 with a lazily-created engine so importing this module has no
side effects (no database file, no connection) — important for fast, isolated
tests. The database URL is read from ``DATABASE_URL`` and defaults to a local
SQLite file under ``saas/data/gvd.db``.

Schema is managed by Alembic (see ``migrations/``). ``ensure_schema()`` runs the
migrations on first use at runtime; tests can inject their own session factory to
stay fully isolated.
"""

import os
from contextlib import contextmanager
from pathlib import Path

from sqlalchemy import create_engine, text
from sqlalchemy.orm import DeclarativeBase, sessionmaker

BASE_DIR = Path(__file__).resolve().parent
DEFAULT_DB_PATH = BASE_DIR / "data" / "gvd.db"


class Base(DeclarativeBase):
    """Declarative base for all ORM models."""


def get_database_url() -> str:
    """Return the configured database URL (defaults to local SQLite)."""
    url = os.environ.get("DATABASE_URL")
    if url:
        return url
    DEFAULT_DB_PATH.parent.mkdir(parents=True, exist_ok=True)
    return f"sqlite:///{DEFAULT_DB_PATH.as_posix()}"


_engine = None
_session_factory = None
_schema_ready = False


def get_engine():
    """Return a process-wide SQLAlchemy engine (created on first use)."""
    global _engine
    if _engine is None:
        url = get_database_url()
        # SQLite + multiple worker threads: allow cross-thread use.
        connect_args = {"check_same_thread": False} if url.startswith("sqlite") else {}
        _engine = create_engine(
            url, future=True, pool_pre_ping=True, connect_args=connect_args
        )
    return _engine


def get_session_factory():
    """Return a process-wide session factory (created on first use)."""
    global _session_factory
    if _session_factory is None:
        _session_factory = sessionmaker(
            bind=get_engine(), expire_on_commit=False, future=True
        )
    return _session_factory


@contextmanager
def session_scope(session_factory=None):
    """Transactional scope: commit on success, rollback on error, always close."""
    factory = session_factory or get_session_factory()
    session = factory()
    try:
        yield session
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()


def _alembic_cfg(database_url: str = None):
    from alembic.config import Config

    cfg = Config(str(BASE_DIR / "alembic.ini"))
    cfg.set_main_option("script_location", str(BASE_DIR / "migrations"))
    cfg.set_main_option("sqlalchemy.url", database_url or get_database_url())
    return cfg


def run_migrations(database_url: str = None) -> None:
    """Apply all Alembic migrations up to ``head`` for the given (or default) URL.

    If the database was created by an earlier ``create_all`` call (i.e. at least
    one application table exists but the ``alembic_version`` tracking table is
    absent), the schema is stamped at ``head`` so subsequent calls skip already-
    applied migrations.  A fully empty database runs the normal upgrade path.
    """
    from alembic import command
    from sqlalchemy import inspect

    cfg = _alembic_cfg(database_url)
    engine = get_engine() if database_url is None else create_engine(
        database_url, future=True, pool_pre_ping=True,
        connect_args={"check_same_thread": False} if (database_url or get_database_url()).startswith("sqlite") else {},
    )
    inspector = inspect(engine)
    existing_tables = set(inspector.get_table_names())
    if "alembic_version" not in existing_tables and existing_tables:
        # Pre-Alembic schema: application tables already exist from create_all.
        # Stamp at head so Alembic skips DDL it cannot re-apply.
        command.stamp(cfg, "head")
        return
    command.upgrade(cfg, "head")


def check_db_ready(engine=None) -> bool:
    """Lightweight readiness probe: can we execute a trivial query?"""
    try:
        eng = engine or get_engine()
        with eng.connect() as conn:
            conn.execute(text("SELECT 1"))
        return True
    except Exception:
        return False


def ensure_schema() -> None:
    """Ensure the runtime schema exists (idempotent, runs migrations once).

    Falls back to ``create_all`` only if Alembic is unavailable, so the app keeps
    working while still logging the problem. Intended for the default app engine;
    tests that inject their own session factory bypass this entirely.
    """
    global _schema_ready
    if _schema_ready:
        return
    try:
        run_migrations()
    except Exception:  # pragma: no cover - defensive fallback
        import logging

        import models_db  # noqa: F401  (register models on Base.metadata)

        logging.getLogger(__name__).exception(
            "Alembic migration failed; falling back to create_all"
        )
        Base.metadata.create_all(get_engine())
    _schema_ready = True
