#!/usr/bin/env python3
"""Validate a Jekyll post file before publishing."""
from __future__ import annotations

import argparse
import logging
import re
import sys
from pathlib import Path
from typing import Any

import yaml

log = logging.getLogger(__name__)

REQUIRED_FRONTMATTER_KEYS = ["layout", "title", "date", "tags", "description"]

FORBIDDEN_PATTERNS = [
    r"OPENAI_API_KEY\s*[:=]\s*(?!<REDACTED>|<YOUR_KEY>|\$\{?OPENAI_API_KEY\}?)\S+",  # API key var with non-placeholder value
    r"sk-[A-Za-z0-9]{20,}",             # OpenAI API key pattern
    r"ghp_[A-Za-z0-9]{36}",            # GitHub personal access token
    r"-----BEGIN .+? PRIVATE KEY-----",  # Private key
    r"password\s*[:=]\s*\S{8,}",
    r"secret\s*[:=]\s*\S{8,}",
]


def parse_frontmatter(file_path: Path) -> tuple[dict[str, Any], str]:
    """Parse Jekyll-style YAML front matter from a markdown file."""
    text = file_path.read_text(encoding="utf-8")
    if not text.startswith("---"):
        return {}, text
    # Find the closing ---
    end = text.find("\n---", 3)
    if end == -1:
        return {}, text
    yaml_src = text[3:end].strip()
    content = text[end + 4:].lstrip("\n")
    try:
        metadata = yaml.safe_load(yaml_src) or {}
    except yaml.YAMLError as e:
        raise ValueError(f"Invalid YAML front matter: {e}") from e
    return metadata, content


def validate_filename(file_path: Path) -> list[str]:
    """Check filename format: YYYY-MM-DD-<slug>.md"""
    errors = []
    name = file_path.name
    if not re.match(r"^\d{4}-\d{2}-\d{2}-.+\.md$", name):
        errors.append(
            f"Filename '{name}' does not match YYYY-MM-DD-<slug>.md format"
        )
    return errors


def validate_frontmatter(metadata: dict[str, Any]) -> list[str]:
    errors = []
    for key in REQUIRED_FRONTMATTER_KEYS:
        if key not in metadata:
            errors.append(f"Missing front matter key: '{key}'")
        elif not metadata[key]:
            errors.append(f"Front matter key '{key}' is empty")

    # tags must be a list
    if "tags" in metadata and not isinstance(metadata["tags"], list):
        errors.append("Front matter 'tags' must be a YAML list")

    if "layout" in metadata and metadata["layout"] != "post":
        errors.append("Front matter 'layout' must be 'post'")

    # date format check
    if "date" in metadata:
        date_str = str(metadata["date"])
        if not re.match(r"\d{4}-\d{2}-\d{2}", date_str):
            errors.append(f"Front matter 'date' has unexpected format: {date_str!r}")

    return errors


def validate_structure(content: str) -> list[str]:
    errors = []
    h2_sections = re.findall(r"^##\s+.+", content, re.MULTILINE)
    if len(h2_sections) < 2:
        errors.append(
            f"Post must have at least 2 H2 sections (## ...), found {len(h2_sections)}"
        )
    required_sections = ["Background", "Step-by-step", "Common pitfalls", "Summary"]
    for section in required_sections:
        pattern = rf"^##\s+.*{re.escape(section)}.*$"
        if not re.search(pattern, content, re.MULTILINE | re.IGNORECASE):
            log.warning("Missing recommended section: ## %s", section)
    return errors


def validate_no_secrets(content: str) -> list[str]:
    errors = []
    for pattern in FORBIDDEN_PATTERNS:
        if re.search(pattern, content, re.IGNORECASE):
            errors.append(f"Potential secret detected matching pattern: {pattern}")
    return errors


def validate_post(file_path: Path, check_filename: bool = True) -> list[str]:
    all_errors: list[str] = []

    if check_filename:
        all_errors.extend(validate_filename(file_path))

    try:
        metadata, content = parse_frontmatter(file_path)
    except Exception as e:
        all_errors.append(f"Failed to parse front matter: {e}")
        return all_errors

    all_errors.extend(validate_frontmatter(metadata))
    all_errors.extend(validate_structure(content))
    all_errors.extend(validate_no_secrets(content))

    return all_errors


def main() -> None:
    parser = argparse.ArgumentParser(description="Validate Jekyll post before publishing")
    parser.add_argument("--file", required=True, help="Path to markdown post file")
    parser.add_argument("--no-filename-check", action="store_true",
                        help="Skip filename format check (use for tmp/ paths)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    file_path = Path(args.file)
    if not file_path.exists():
        print(f"ERROR: File not found: {file_path}", file=sys.stderr)
        sys.exit(2)

    errors = validate_post(file_path, check_filename=not args.no_filename_check)

    if errors:
        print("VALIDATION FAILED:", file=sys.stderr)
        for err in errors:
            print(f"  ✗ {err}", file=sys.stderr)
        sys.exit(1)
    else:
        log.info("Validation passed: %s", file_path)
        print("OK")
        sys.exit(0)


if __name__ == "__main__":
    main()
