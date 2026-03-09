#!/usr/bin/env python3
"""Convert text to URL-safe slug."""
from __future__ import annotations

import hashlib
import re
import sys
import unicodedata


def slugify(text: str, min_length: int = 8) -> str:
    """Convert text to a lowercase, hyphen-separated URL slug.

    For topics that are mostly non-ASCII (e.g. Japanese), a short hash suffix
    is appended to ensure uniqueness and minimum length.
    """
    original = text
    has_non_ascii = any(ord(ch) > 127 for ch in original)
    # Normalize unicode (NFKD) and drop non-ASCII
    ascii_text = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode("ascii")
    slug = ascii_text.lower()
    # Remove characters that are not alphanumeric, spaces, or hyphens
    slug = re.sub(r"[^\w\s-]", "", slug)
    # Replace whitespace and underscores with hyphens
    slug = re.sub(r"[\s_]+", "-", slug)
    # Collapse multiple hyphens
    slug = re.sub(r"-{2,}", "-", slug)
    slug = slug.strip("-")

    slug_words = [word for word in slug.split("-") if word]
    generic_words = {"openclaw", "cron"}
    informative_words = [word for word in slug_words if word not in generic_words]

    needs_hash = len(slug) < min_length
    if has_non_ascii and (len(informative_words) < 1 or len(slug) < 16):
        needs_hash = True

    # If slug is too short or lost too much meaning due to ASCII folding, append a short hash.
    if needs_hash:
        short_hash = hashlib.sha1(original.encode()).hexdigest()[:6]
        slug = (slug + "-" + short_hash).strip("-")

    return slug


if __name__ == "__main__":
    if len(sys.argv) < 2:
        print("Usage: slugify.py <text>", file=sys.stderr)
        sys.exit(1)
    print(slugify(" ".join(sys.argv[1:])))
