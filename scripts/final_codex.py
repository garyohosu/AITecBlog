#!/usr/bin/env python3
"""Finalize draft into a publish-ready Jekyll post using Codex CLI or OpenAI API."""
from __future__ import annotations

import argparse
import json
import logging
import os
import shutil
import subprocess
import tempfile
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


def finalize_with_openai(topic: str, date: str, draft: str, config: dict) -> str:
    """Call OpenAI chat completions API."""
    try:
        from openai import OpenAI
    except ImportError:
        raise RuntimeError("openai package not installed. Run: pip install openai")

    api_key = os.environ.get("OPENAI_API_KEY")
    if not api_key:
        raise RuntimeError("OPENAI_API_KEY environment variable not set")

    client = OpenAI(api_key=api_key)
    codex_cfg = config.get("codex", {})
    model = codex_cfg.get("model") or "gpt-4o"

    prompt = FINALIZE_TEMPLATE.format(topic=topic, date=date, draft=draft)
    log.info("Calling OpenAI API (model=%s) ...", model)

    response = client.chat.completions.create(
        model=model,
        messages=[
            {"role": "system", "content": SYSTEM_PROMPT},
            {"role": "user", "content": prompt},
        ],
        temperature=0.7,
        max_tokens=4096,
    )
    return response.choices[0].message.content.strip()


def finalize_with_codex_cli(topic: str, date: str, draft: str, config: dict) -> str:
    """Call the `codex` CLI binary."""
    codex_cmd = config.get("codex", {}).get("command", "codex")
    if not shutil.which(codex_cmd):
        raise RuntimeError(f"Command '{codex_cmd}' not found in PATH")

    prompt = FINALIZE_TEMPLATE.format(topic=topic, date=date, draft=draft)

    with tempfile.NamedTemporaryFile(mode="w", suffix=".txt", delete=False,
                                     encoding="utf-8") as f:
        f.write(prompt)
        prompt_file = f.name

    try:
        log.info("Calling codex CLI (%s) ...", codex_cmd)
        result = subprocess.run(
            [codex_cmd, "--quiet", "--prompt-file", prompt_file],
            capture_output=True,
            text=True,
            timeout=300,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"codex CLI failed (exit {result.returncode}):\n{result.stderr}"
            )
        return result.stdout.strip()
    finally:
        Path(prompt_file).unlink(missing_ok=True)


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


def finalize(topic: str, date: str, draft: str, config: dict) -> str:
    """Try finalization methods in order of quality."""
    errors = []

    # 1. Try Codex CLI
    try:
        return finalize_with_codex_cli(topic, date, draft, config)
    except Exception as e:
        log.warning("Codex CLI unavailable: %s", e)
        errors.append(str(e))

    # 2. Try OpenAI API
    if config.get("codex", {}).get("use_openai_fallback", True):
        try:
            return finalize_with_openai(topic, date, draft, config)
        except Exception as e:
            log.warning("OpenAI API unavailable: %s", e)
            errors.append(str(e))

    # 3. Ollama fallback
    try:
        return finalize_with_ollama_fallback(topic, date, draft, config)
    except Exception as e:
        errors.append(str(e))

    raise RuntimeError("All finalization methods failed:\n" + "\n".join(errors))


def main() -> None:
    parser = argparse.ArgumentParser(description="Finalize draft with Codex CLI / OpenAI")
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
