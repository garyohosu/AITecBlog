#!/usr/bin/env python3
"""Generate a rough draft using a local LLM (Ollama)."""
from __future__ import annotations

import argparse
import json
import logging
from pathlib import Path

import requests

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)


def load_config() -> dict:
    return json.loads((ROOT / "data/config.json").read_text())


def call_ollama(endpoint: str, model: str, prompt: str, timeout: int = 300) -> str:
    resp = requests.post(
        f"{endpoint}/api/generate",
        json={"model": model, "prompt": prompt, "stream": False},
        timeout=timeout,
    )
    resp.raise_for_status()
    return resp.json()["response"]


def build_outline_prompt(topic: str) -> str:
    return (
        f"Create a detailed outline for a technical blog post about:\n"
        f"Topic: {topic}\n\n"
        "The outline must include these H2 sections:\n"
        "## Background\n"
        "## Step-by-step\n"
        "## Common pitfalls\n"
        "## Summary\n\n"
        "For the Step-by-step section, list numbered sub-steps.\n"
        "Keep it concise. Return only the outline, no prose."
    )


def build_draft_prompt(topic: str, outline: str) -> str:
    return (
        f"Write a rough draft of a technical blog post.\n\n"
        f"Topic: {topic}\n\n"
        f"Outline:\n{outline}\n\n"
        "Requirements:\n"
        "- Start with a ONE-LINE conclusion (what the reader will learn/achieve)\n"
        "- Use H2 headings: ## Background, ## Step-by-step, ## Common pitfalls, ## Summary\n"
        "- Include at least one code block (shell, python, or yaml) with ``` fences\n"
        "- Use numbered steps in the Step-by-step section\n"
        "- Short paragraphs (2-3 sentences max)\n"
        "- No tables\n"
        "- Do NOT include YAML front matter\n"
        "- Write in Japanese (日本語) or English (consistent throughout)\n\n"
        "Write the complete draft now:"
    )


def generate_draft(topic: str, config: dict) -> str:
    llm = config["local_llm"]
    endpoint = llm["endpoint"]
    model = llm["model"]

    log.info("Generating outline via %s/%s ...", endpoint, model)
    outline = call_ollama(endpoint, model, build_outline_prompt(topic))
    log.debug("Outline:\n%s", outline)

    log.info("Generating draft ...")
    draft = call_ollama(endpoint, model, build_draft_prompt(topic, outline))
    log.info("Draft generated (%d chars)", len(draft))
    return draft


def main() -> None:
    parser = argparse.ArgumentParser(description="Generate rough draft using local LLM")
    parser.add_argument("--topic", required=True, help="Blog post topic")
    parser.add_argument("--out", required=True, help="Output file path for the draft")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    config = load_config()
    draft = generate_draft(args.topic, config)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(draft, encoding="utf-8")
    log.info("Draft written to %s", out_path)


if __name__ == "__main__":
    main()
