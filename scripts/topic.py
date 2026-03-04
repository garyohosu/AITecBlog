#!/usr/bin/env python3
"""Topic selection using local LLM (Ollama) with deduplication."""
from __future__ import annotations

import argparse
import json
import logging
import re
import sys
from datetime import datetime, timedelta
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))
from slugify import slugify

log = logging.getLogger(__name__)


def load_config() -> dict:
    return json.loads((ROOT / "data/config.json").read_text())


def load_state() -> dict:
    state_file = ROOT / "data/state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {"seen_topics": [], "last_run": None}


def load_seed_topics() -> list[str]:
    seed_file = ROOT / "data/topics_seed.md"
    if not seed_file.exists():
        return []
    text = seed_file.read_text(encoding="utf-8")
    return [m.strip() for m in re.findall(r"^-\s+(.+)$", text, re.MULTILINE) if m.strip()]


def call_ollama(endpoint: str, model: str, prompt: str, timeout: int = 120) -> str:
    resp = requests.post(
        f"{endpoint}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def generate_topics_llm(config: dict) -> list[str]:
    llm = config["local_llm"]
    prompt = (
        "Generate exactly 10 technical blog post topics about OpenClaw.\n"
        "OpenClaw is a workflow automation and cron scheduling platform.\n\n"
        "Each topic must:\n"
        "1. Be specific and actionable (not vague)\n"
        "2. Have a concrete demo possible (commands, config, or workflow)\n"
        "3. Be suitable for a step-by-step technical tutorial\n\n"
        "Output format: numbered list 1-10, one topic per line, in Japanese or English.\n"
        "Example: 1. OpenClaw でシェルスクリプトを定期実行する方法\n"
        "Return ONLY the numbered list, no explanations."
    )
    try:
        raw = call_ollama(llm["endpoint"], llm["model"], prompt)
        topics = re.findall(r"^\d+[.)]\s*(.+)$", raw, re.MULTILINE)
        return [t.strip() for t in topics if len(t.strip()) > 10]
    except Exception as e:
        log.warning("Ollama topic generation failed: %s", e)
        return []


def is_duplicate(topic: str, seen_topics: list[dict], dedupe_days: int) -> bool:
    slug = slugify(topic)
    cutoff = datetime.now() - timedelta(days=dedupe_days)
    for seen in seen_topics:
        try:
            seen_date = datetime.fromisoformat(seen["date"])
        except (KeyError, ValueError):
            continue
        if seen_date < cutoff:
            continue
        if slug == seen.get("slug") or topic.lower() == seen.get("topic", "").lower():
            return True
    return False


def select_topic(config: dict) -> tuple[str, str]:
    """Return (topic, slug) for today's post."""
    state = load_state()
    seen = state.get("seen_topics", [])
    dedupe_days = config.get("dedupe_days", 60)

    candidates: list[str] = []
    candidates.extend(generate_topics_llm(config))
    candidates.extend(load_seed_topics())

    for topic in candidates:
        if not topic or len(topic) < 10:
            continue
        if is_duplicate(topic, seen, dedupe_days):
            log.debug("Skipping duplicate topic: %s", topic)
            continue
        slug = slugify(topic)
        if not slug:
            continue
        log.info("Selected topic: %s  (slug: %s)", topic, slug)
        return topic, slug

    raise RuntimeError(
        "No valid topic found. All candidates are duplicates or invalid. "
        "Add more topics to data/topics_seed.md or reduce dedupe_days."
    )


def main() -> None:
    parser = argparse.ArgumentParser(description="Select today's blog topic")
    parser.add_argument("--out", help="Write JSON result to this file")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    config = load_config()
    topic, slug = select_topic(config)

    result = {"topic": topic, "slug": slug}
    output = json.dumps(result, ensure_ascii=False, indent=2)

    if args.out:
        Path(args.out).write_text(output, encoding="utf-8")
        log.info("Topic written to %s", args.out)
    else:
        print(output)


if __name__ == "__main__":
    main()
