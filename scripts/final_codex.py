#!/usr/bin/env python3
"""Finalize draft into a publish-ready Jekyll post using Codex CLI (flat-rate flow)."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)

SYSTEM_PROMPT = (
    "You are a senior technical writer who specializes in developer-facing blog posts. "
    "You produce clean, accurate, and engaging technical articles for engineers."
)

FINALIZE_TEMPLATE = """\
Finalize the following rough draft into a publish-ready Jekyll blog post.

Topic: {topic}
Date: {date}

Draft:
---
{draft}
---

Requirements:
1. Add YAML front matter at the very top with these keys:
   - title: (clear, specific, SEO-friendly title — in Japanese if draft is in Japanese)
   - date: {date} 09:00:00 +0900
   - tags: (YAML list of 3-5 relevant tags in lowercase English, e.g. [openclaw, cron, automation])
   - description: (1-2 sentence summary for SEO, matching the draft language)
2. Keep the one-line conclusion near the top (just after any intro paragraph)
3. Use H2 headings (##) consistently: Background, Step-by-step, Common pitfalls, Summary
4. Make code examples correct and runnable; add comments where helpful
5. Short paragraphs (2-3 sentences max)
6. No tables — use lists or prose instead
7. Common pitfalls must be specific and actionable (at least 3 items)
8. Maintain the original language (Japanese or English) consistently

Return ONLY the complete Jekyll markdown post (front matter + content).
No explanations, no markdown fences around the whole output.
"""


def load_config() -> dict:
    return json.loads((ROOT / "data/config.json").read_text())


def finalize_with_codex_cli(topic: str, date: str, draft: str, config: dict) -> str:
    """Call the `codex exec` CLI flow (OAuth flat-rate usage)."""
    codex_cmd = config.get("codex", {}).get("command", "codex")
    if not shutil.which(codex_cmd):
        raise RuntimeError(f"Command '{codex_cmd}' not found in PATH")

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        + FINALIZE_TEMPLATE.format(topic=topic, date=date, draft=draft)
    )

    log.info("Calling codex CLI (%s exec) ...", codex_cmd)
    result = subprocess.run(
        [codex_cmd, "exec", prompt],
        capture_output=True,
        text=True,
        timeout=600,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"codex CLI failed (exit {result.returncode}):\n{result.stderr}"
        )

    output = result.stdout.strip()
    if not output:
        raise RuntimeError("codex CLI returned empty output")
    return output


def finalize_with_ollama_fallback(topic: str, date: str, draft: str, config: dict) -> str:
    """Fallback: use Ollama with a quality prompt."""
    import requests

    llm = config["local_llm"]
    prompt = FINALIZE_TEMPLATE.format(topic=topic, date=date, draft=draft)
    log.info("Falling back to Ollama for finalization ...")
    resp = requests.post(
        f"{llm['endpoint']}/api/generate",
        json={"model": llm["model"], "prompt": prompt, "stream": False},
        timeout=600,
    )
    resp.raise_for_status()
    return resp.json()["response"].strip()


def finalize_with_claude_api(topic: str, date: str, draft: str, config: dict) -> str:
    """Fallback: use Claude API (Anthropic) for finalization."""
    import os
    import anthropic

    api_key = os.environ.get("ANTHROPIC_API_KEY")
    if not api_key:
        raise RuntimeError("ANTHROPIC_API_KEY environment variable not set")

    client = anthropic.Anthropic(api_key=api_key)
    prompt = FINALIZE_TEMPLATE.format(topic=topic, date=date, draft=draft)

    log.info("Calling Claude API for finalization ...")
    message = client.messages.create(
        model="claude-haiku-4-5-20251001",
        max_tokens=4096,
        system=SYSTEM_PROMPT,
        messages=[{"role": "user", "content": prompt}],
    )
    result = message.content[0].text.strip()
    if not result:
        raise RuntimeError("Claude API returned empty output")
    return result


def finalize(topic: str, date: str, draft: str, config: dict) -> str:
    """Prefer Codex CLI; fallback to Claude API, then optionally Ollama."""
    errors = []

    # 1. Codex CLI (primary, flat-rate)
    try:
        return finalize_with_codex_cli(topic, date, draft, config)
    except Exception as e:
        log.warning("Codex CLI failed: %s", e)
        errors.append(f"codex: {e}")

    # 2. Claude API fallback (uses ANTHROPIC_API_KEY env var)
    try:
        return finalize_with_claude_api(topic, date, draft, config)
    except Exception as e:
        log.warning("Claude API failed: %s", e)
        errors.append(f"claude: {e}")

    # 3. Optional Ollama fallback
    if config.get("codex", {}).get("use_ollama_fallback", False):
        try:
            return finalize_with_ollama_fallback(topic, date, draft, config)
        except Exception as e:
            errors.append(f"ollama: {e}")

    raise RuntimeError("Finalization failed:\n" + "\n".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize draft with Codex CLI")
    parser.add_argument("--topic", required=True, help="Blog post topic")
    parser.add_argument("--draft", required=True, help="Path to rough draft file")
    parser.add_argument("--out", required=True, help="Output path for final markdown")
    parser.add_argument("--date", default=None,
                        help="Publication date YYYY-MM-DD (default: today)")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    if args.date is None:
        from datetime import date
        args.date = date.today().isoformat()

    config = load_config()
    draft_text = Path(args.draft).read_text(encoding="utf-8")

    final_text = finalize(args.topic, args.date, draft_text, config)

    out_path = Path(args.out)
    out_path.parent.mkdir(parents=True, exist_ok=True)
    out_path.write_text(final_text, encoding="utf-8")
    log.info("Final post written to %s (%d chars)", out_path, len(final_text))


if __name__ == "__main__":
    main()
