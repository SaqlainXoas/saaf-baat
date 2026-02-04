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

        assert os.path.isfile(env_path), f"Expected .env at {env_path}"
        assert os.path.isdir(src_path), f"Expected src/ at {src_path}"
