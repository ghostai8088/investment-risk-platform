#!/usr/bin/env python3
"""Secret-scanning placeholder (BR-10).

A lightweight regex scan for obviously-committed secrets. This is a stand-in for a
full scanner (e.g., gitleaks) wired into CI as later-hardening; it intentionally errs
toward few false positives. Exits non-zero if a likely secret is found.
"""

from __future__ import annotations

import re
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]

EXCLUDE_DIRS = {
    ".git",
    ".venv",
    "node_modules",
    "dist",
    "build",
    "__pycache__",
    ".mypy_cache",
    ".ruff_cache",
    ".pytest_cache",
}
EXCLUDE_FILES = {".env.example"}

PATTERNS = {
    "AWS access key id": re.compile(r"AKIA[0-9A-Z]{16}"),
    "Private key block": re.compile(r"-----BEGIN (?:RSA |EC |OPENSSH )?PRIVATE KEY-----"),
    "Slack token": re.compile(r"xox[baprs]-[0-9A-Za-z-]{10,}"),
    "Google API key": re.compile(r"AIza[0-9A-Za-z\-_]{35}"),
}

TEXT_SUFFIXES = {
    ".py",
    ".ts",
    ".tsx",
    ".js",
    ".jsx",
    ".json",
    ".yml",
    ".yaml",
    ".toml",
    ".ini",
    ".md",
    ".env",
    ".sh",
    ".cfg",
    ".mako",
    ".html",
}


def iter_files() -> list[Path]:
    files: list[Path] = []
    for path in ROOT.rglob("*"):
        if path.is_dir():
            continue
        if any(part in EXCLUDE_DIRS for part in path.parts):
            continue
        if path.name in EXCLUDE_FILES:
            continue
        if path.suffix.lower() not in TEXT_SUFFIXES:
            continue
        files.append(path)
    return files


def main() -> int:
    findings: list[str] = []
    for file in iter_files():
        try:
            text = file.read_text(encoding="utf-8")
        except (UnicodeDecodeError, OSError):
            continue
        for name, pattern in PATTERNS.items():
            if pattern.search(text):
                findings.append(f"{name} in {file.relative_to(ROOT)}")

    if findings:
        print("Secret scan FAILED (possible secrets committed):")
        for finding in findings:
            print(f"  - {finding}")
        return 1

    print("Secret scan passed (no obvious secrets found).")
    return 0


if __name__ == "__main__":
    sys.exit(main())
