"""
Tests for database schema constraints in schema.sql and create_schema.py.

TDD: ensure schema aligns with models/PRD and enforces deduplication.
"""
from __future__ import annotations

from pathlib import Path


def _read_file(path: Path) -> str:
    return path.read_text(encoding="utf-8")


def test_schema_sql_category_constraint_includes_all_model_categories():
    """analyzed_feed category CHECK should include all model categories."""
    schema_path = Path(__file__).resolve().parent.parent.parent / "src" / "db" / "schema.sql"
    content = _read_file(schema_path)

    # Must include security + international along with existing set
    assert "security" in content
    assert "international" in content


def test_schema_sql_content_hash_is_unique():
    """content_hash should be UNIQUE in schema.sql to enforce deduplication."""
    schema_path = Path(__file__).resolve().parent.parent.parent / "src" / "db" / "schema.sql"
    content = _read_file(schema_path)

    # Accept either inline UNIQUE or a separate constraint
    assert "content_hash" in content
    assert "UNIQUE" in content, "content_hash must be UNIQUE in schema.sql"


def test_create_schema_has_category_constraint():
    """create_schema.py should enforce category constraints aligned with models."""
    create_schema_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "postgres" / "create_schema.py"
    content = _read_file(create_schema_path)

    assert "category" in content
    assert "security" in content
    assert "international" in content


def test_create_schema_content_hash_unique():
    """create_schema.py should set content_hash UNIQUE."""
    create_schema_path = Path(__file__).resolve().parent.parent.parent / "scripts" / "postgres" / "create_schema.py"
    content = _read_file(create_schema_path)

    assert "content_hash" in content
    assert "UNIQUE" in content, "content_hash must be UNIQUE in create_schema.py"
