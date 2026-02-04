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
    """Regression: run_schema.py must resolve schema.sql relative to its own location."""

    def test_scripts_directory_exists(self):
        """scripts/ must exist at backend root."""
        assert (_BACKEND_DIR / "scripts").is_dir()

    def test_run_schema_script_exists(self):
        """scripts/run_schema.py must exist."""
        assert (_BACKEND_DIR / "scripts" / "run_schema.py").is_file()

    def test_schema_sql_reachable_via_run_schema_path_logic(self):
        """Replicate the exact path logic from run_schema.py and verify the target exists.

        run_schema.py computes:
            _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(__file__)))
            schema_path  = os.path.join(_backend_dir, 'src', 'db', 'schema.sql')

        We simulate __file__ as the real script path and assert the result is a file.
        """
        run_schema_file = str(_BACKEND_DIR / "scripts" / "run_schema.py")

        # Mirror the two os.path.dirname calls that run_schema.py executes
        _backend_dir = os.path.dirname(os.path.dirname(os.path.abspath(run_schema_file)))
        schema_path = os.path.join(_backend_dir, "src", "db", "schema.sql")

        assert os.path.isfile(schema_path), (
            f"run_schema.py path logic resolves to {schema_path}, but the file does not exist"
        )

    def test_create_schema_script_exists(self):
        """scripts/create_schema.py must also exist (moved alongside run_schema.py)."""
        assert (_BACKEND_DIR / "scripts" / "create_schema.py").is_file()
