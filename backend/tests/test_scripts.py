"""
Tests for utility scripts in backend/scripts/.

Validates that path-resolution logic in each script correctly locates
files regardless of the current working directory at runtime.
"""
from __future__ import annotations

import os
from pathlib import Path

# backend/ root, derived the same way conftest.py does it
_BACKEND_DIR = Path(__file__).resolve().parent.parent


class TestRunSchemaPathResolution:
    """Hosted changes use versioned SQL files; the old printer is retired."""

    def test_scripts_directory_exists(self):
        """scripts/ must exist at backend root."""
        assert (_BACKEND_DIR / "scripts").is_dir()

    def test_run_schema_script_exists(self):
        """The Postgres schema scripts live under scripts/postgres/.

        They sat in scripts/ next to init_db.py, reading as the setup path they
        stopped being when storage moved to local SQLite.
        """
        assert (_BACKEND_DIR / "scripts" / "postgres" / "run_schema.py").is_file()
        assert (_BACKEND_DIR / "scripts" / "postgres" / "create_schema.py").is_file()
        assert not (_BACKEND_DIR / "scripts" / "run_schema.py").exists()

    def test_versioned_migrations_cover_baseline_and_reliability(self):
        migrations = _BACKEND_DIR.parent / "supabase" / "migrations"
        baseline = migrations / "20260910173949_saaf_baat_initial_schema.sql"
        reliability = migrations / "20260924000000_reliable_daily_brief.sql"
        assert "CREATE TABLE IF NOT EXISTS raw_articles" in baseline.read_text()
        assert len(list(migrations.glob("2026091*.sql"))) == 4
        sql = reliability.read_text()
        for name in ("publish_brief", "persist_embeddings", "persist_triage_metadata",
                     "replace_recent_clusters"):
            assert f"CREATE OR REPLACE FUNCTION {name}" in sql

    def test_create_schema_script_exists(self):
        """create_schema.py moved with it."""
        assert (_BACKEND_DIR / "scripts" / "postgres" / "create_schema.py").is_file()


class TestE2EPipelinePathResolution:
    """Regression: test_e2e_pipeline.py must resolve backend/.env and backend/src."""

    def test_e2e_pipeline_script_exists(self):
        """tests/test_e2e_pipeline.py must exist."""
        assert (_BACKEND_DIR / "tests" / "test_e2e_pipeline.py").is_file()

    def test_e2e_pipeline_path_logic(self):
        """
        Validate path logic used in test_e2e_pipeline.py:
        - load_dotenv from backend/.env
        - sys.path includes backend/src
        """
        e2e_file = str(_BACKEND_DIR / "tests" / "test_e2e_pipeline.py")

        backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(e2e_file)))
        env_path = os.path.join(backend_dir, ".env")
        src_path = os.path.join(backend_dir, "src")

        # The regression is the path arithmetic landing on backend/, not the
        # presence of .env — that file is gitignored and never exists in CI.
        assert env_path == str(_BACKEND_DIR / ".env"), f"Resolved .env to {env_path}"
        assert os.path.isdir(src_path), f"Expected src/ at {src_path}"
