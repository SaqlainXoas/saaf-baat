"""
Test suite for Phase 0: Foundation & Environment Setup

These tests validate that the project structure is correctly set up.
"""
import sys
from pathlib import Path


class TestDirectoryStructure:
    """Test that all required directories exist."""

    def test_src_directories_exist(self):
        """Verify all src subdirectories are created."""
        backend_dir = Path(__file__).parent.parent
        required_dirs = [
            "src",
            "src/scrapers",
            "src/processing",
            "src/db",
            "src/utils",
        ]

        for dir_path in required_dirs:
            full_path = backend_dir / dir_path
            assert full_path.exists(), f"Directory {dir_path} does not exist"
            assert full_path.is_dir(), f"{dir_path} is not a directory"

    def test_tests_directories_exist(self):
        """Verify all test subdirectories are created."""
        backend_dir = Path(__file__).parent.parent
        required_dirs = [
            "tests",
            "tests/test_scrapers",
            "tests/test_processing",
            "tests/test_db",
            "tests/test_utils",
        ]

        for dir_path in required_dirs:
            full_path = backend_dir / dir_path
            assert full_path.exists(), f"Directory {dir_path} does not exist"
            assert full_path.is_dir(), f"{dir_path} is not a directory"

    def test_config_directory_exists(self):
        """Verify config directory exists."""
        backend_dir = Path(__file__).parent.parent
        config_dir = backend_dir / "config"
        assert config_dir.exists(), "Config directory does not exist"
        assert config_dir.is_dir(), "Config path is not a directory"

    def test_python_packages_initialized(self):
        """Verify all directories have __init__.py files."""
        backend_dir = Path(__file__).parent.parent
        required_init_files = [
            "src/__init__.py",
            "src/scrapers/__init__.py",
            "src/processing/__init__.py",
            "src/db/__init__.py",
            "src/utils/__init__.py",
            "tests/__init__.py",
        ]

        for init_file in required_init_files:
            full_path = backend_dir / init_file
            assert full_path.exists(), f"{init_file} does not exist"


class TestConfigFiles:
    """Test that configuration files exist and are valid."""

    def test_sources_yaml_exists(self):
        """Verify sources.yaml exists."""
        backend_dir = Path(__file__).parent.parent
        sources_file = backend_dir / "config" / "sources.yaml"
        assert sources_file.exists(), "sources.yaml does not exist"

    def test_sources_yaml_valid(self, sources_config):
        """Verify sources.yaml has valid structure."""
        assert "sources" in sources_config, "sources.yaml missing 'sources' key"
        assert len(sources_config["sources"]) >= 2, "Need at least 2 sources configured"

        for source_name, source_data in sources_config["sources"].items():
            assert "url" in source_data, f"Source {source_name} missing URL"
            assert "method" in source_data, f"Source {source_name} missing method"
            assert "sections" in source_data, f"Source {source_name} missing sections"

    def test_classification_yaml_exists(self):
        """Verify classification_rules.yaml exists."""
        backend_dir = Path(__file__).parent.parent
        classification_file = backend_dir / "config" / "classification_rules.yaml"
        assert classification_file.exists(), "classification_rules.yaml does not exist"

    def test_classification_yaml_valid(self, classification_config):
        """Verify classification_rules.yaml has valid structure."""
        assert "categories" in classification_config, "Missing 'categories' key"
        assert "impact_labels" in classification_config, "Missing 'impact_labels' key"

        assert len(classification_config["categories"]) > 0, "No categories defined"
        assert len(classification_config["impact_labels"]) > 0, "No impact labels defined"

    def test_env_example_exists(self):
        """Verify .env.example exists."""
        backend_dir = Path(__file__).parent.parent
        env_file = backend_dir / ".env.example"
        assert env_file.exists(), ".env.example does not exist"


class TestPythonEnvironment:
    """Test that Python environment is properly configured."""

    def test_requirements_txt_exists(self):
        """Verify requirements.txt exists."""
        backend_dir = Path(__file__).parent.parent
        req_file = backend_dir / "requirements.txt"
        assert req_file.exists(), "requirements.txt does not exist"

    def test_pytest_ini_exists(self):
        """Verify pytest.ini exists."""
        backend_dir = Path(__file__).parent.parent
        pytest_file = backend_dir / "pytest.ini"
        assert pytest_file.exists(), "pytest.ini does not exist"

    def test_pyproject_toml_exists(self):
        """Verify pyproject.toml exists for linting config."""
        backend_dir = Path(__file__).parent.parent
        pyproject_file = backend_dir / "pyproject.toml"
        assert pyproject_file.exists(), "pyproject.toml does not exist"

    def test_pytest_can_run(self):
        """Verify pytest is properly configured."""
        # If we've made it this far, pytest is running successfully
        assert True, "pytest is configured and running"


class TestVirtualEnvironment:
    """Test virtual environment setup."""

    def test_venv_exists(self):
        """Verify virtual environment directory exists."""
        backend_dir = Path(__file__).parent.parent
        venv_dir = backend_dir / "venv"
        assert venv_dir.exists(), "venv directory does not exist"

    def test_running_in_venv(self):
        """Verify tests are running inside virtual environment."""
        # Check if we're in a virtual environment
        in_venv = hasattr(sys, "real_prefix") or (
            hasattr(sys, "base_prefix") and sys.base_prefix != sys.prefix
        )
        assert in_venv, "Not running in virtual environment"
