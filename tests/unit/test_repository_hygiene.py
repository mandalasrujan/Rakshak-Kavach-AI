"""Guards against committed secrets and insecure configuration."""

import re
from pathlib import Path

ROOT = Path(__file__).resolve().parents[2]
SECRET_PATTERNS = [
    re.compile(r"AIza[0-9A-Za-z_\-]{30,}"),  # Google API key
    re.compile(r"sk-[A-Za-z0-9]{20,}"),
    re.compile(r"-----BEGIN [A-Z ]*PRIVATE KEY-----"),
    re.compile(r"eyJ[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}\.[A-Za-z0-9_-]{10,}"),  # JWT
]
SCANNED_SUFFIXES = {".py", ".yml", ".yaml", ".toml", ".ini", ".md", ".txt", ".example", ""}
SKIP_DIRS = {".git", ".venv", "venv", "node_modules", "__pycache__", ".pytest_cache", "data"}


def _files() -> list[Path]:
    return [
        p
        for p in ROOT.rglob("*")
        if p.is_file()
        and not SKIP_DIRS.intersection(p.relative_to(ROOT).parts)
        and p.suffix in SCANNED_SUFFIXES
    ]


def test_no_secret_patterns_in_repository() -> None:
    offenders = [
        str(path.relative_to(ROOT))
        for path in _files()
        for pattern in SECRET_PATTERNS
        if pattern.search(path.read_text(errors="ignore"))
    ]
    assert offenders == []


def test_env_example_contains_placeholders_only() -> None:
    values = dict(
        line.split("=", 1)
        for line in (ROOT / ".env.example").read_text().splitlines()
        if line and not line.startswith("#")
    )
    for key in ("JWT_SECRET_KEY", "POSTGRES_PASSWORD"):
        assert "change-me" in values[key]
    for key in ("GEMINI_API_KEY", "LANGFUSE_SECRET_KEY"):
        assert values[key].startswith("<")
    assert values["COOKIE_SECURE"] == "true"


def test_env_files_are_ignored() -> None:
    gitignore = (ROOT / ".gitignore").read_text().splitlines()
    assert ".env" in gitignore
    assert ".env" in (ROOT / ".dockerignore").read_text().splitlines()


def test_compose_requires_secrets_from_environment() -> None:
    compose = (ROOT / "docker-compose.yml").read_text()
    assert "${JWT_SECRET_KEY:?" in compose
    assert "${POSTGRES_PASSWORD:?" in compose
