"""Fail safely when repository files contain likely credentials.

The check deliberately reports only the detector name and file location. It
never echoes a suspected secret into CI logs.
"""

from __future__ import annotations

import re
import subprocess
from pathlib import Path

SECRET_PATTERNS = {
    "Google API key": re.compile(rb"AIza[0-9A-Za-z_-]{30,}"),
    "Supabase secret key": re.compile(rb"sb_secret_[0-9A-Za-z_-]{16,}"),
    "GitHub token": re.compile(
        rb"(?:gh[pousr]_[0-9A-Za-z]{36,}|github_pat_[0-9A-Za-z_]{50,})"
    ),
    "OpenAI API key": re.compile(
        rb"(?<![0-9A-Za-z])sk-(?:proj-|svcacct-)?[0-9A-Za-z_-]{40,}"
    ),
    "Slack token": re.compile(rb"xox[baprs]-[0-9A-Za-z-]{20,}"),
    "JWT": re.compile(
        rb"eyJ[0-9A-Za-z_-]{10,}\.eyJ[0-9A-Za-z_-]{10,}\.[0-9A-Za-z_-]{10,}"
    ),
}
ENV_ASSIGNMENT = re.compile(r"^\s*#?\s*([A-Z][A-Z0-9_]*)\s*=\s*(.*?)\s*$")
SENSITIVE_ENV_NAME = re.compile(r"(?:KEY|SECRET|TOKEN|PASSWORD|DATABASE_URL)$")
SAFE_PLACEHOLDER_PREFIXES = (
    "YOUR_",
    "GENERATE_",
    "CHANGEME",
    "EXAMPLE_",
    "${",
)


def _candidate_files(repo_root: Path) -> list[Path]:
    result = subprocess.run(
        ["git", "ls-files", "--cached", "--others", "--exclude-standard", "-z"],
        cwd=repo_root,
        check=True,
        capture_output=True,
    )
    return [repo_root / item.decode() for item in result.stdout.split(b"\0") if item]


def _line_number(content: bytes, offset: int) -> int:
    return content.count(b"\n", 0, offset) + 1


def _looks_like_placeholder(value: str) -> bool:
    normalized = value.strip().strip("'\"")
    return not normalized or normalized.upper().startswith(SAFE_PLACEHOLDER_PREFIXES)


def scan_file(path: Path, repo_root: Path) -> list[tuple[str, int, str]]:
    content = path.read_bytes()
    if b"\0" in content:
        return []

    findings: list[tuple[str, int, str]] = []
    for detector, pattern in SECRET_PATTERNS.items():
        for match in pattern.finditer(content):
            findings.append(
                (
                    str(path.relative_to(repo_root)),
                    _line_number(content, match.start()),
                    detector,
                )
            )

    if path.name == ".env.example":
        lines = content.decode("utf-8", errors="replace").splitlines()
        for line_number, line in enumerate(lines, 1):
            match = ENV_ASSIGNMENT.match(line)
            if not match:
                continue
            name, value = match.groups()
            if SENSITIVE_ENV_NAME.search(name) and not _looks_like_placeholder(value):
                findings.append(
                    (str(path.relative_to(repo_root)), line_number, "non-placeholder example value")
                )

    return findings


def main() -> int:
    repo_root = Path(
        subprocess.run(
            ["git", "rev-parse", "--show-toplevel"],
            check=True,
            capture_output=True,
            text=True,
        ).stdout.strip()
    )
    candidate_files = _candidate_files(repo_root)
    findings: list[tuple[str, int, str]] = []
    for path in candidate_files:
        if path.is_file() and not path.is_symlink():
            findings.extend(scan_file(path, repo_root))

    if findings:
        print("Potential secrets found (values redacted):")
        for file_name, line_number, detector in findings:
            print(f"  {file_name}:{line_number}: {detector}")
        return 1

    print(f"Secret hygiene check passed ({len(candidate_files)} repository files scanned).")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
