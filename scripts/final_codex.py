#!/usr/bin/env python3
"""Finalize draft into a publish-ready Jekyll post using Codex CLI (flat-rate flow)."""
from __future__ import annotations

import argparse
import json
import logging
import os
import re
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
   - layout: post
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
    return json.loads((ROOT / "data/config.json").read_text(encoding="utf-8"))


def _resolve_codex_command(codex_cmd: str) -> str:
    candidates = [codex_cmd]
    if os.name == "nt" and Path(codex_cmd).suffix == "":
        candidates.insert(0, f"{codex_cmd}.cmd")
    for candidate in candidates:
        resolved = shutil.which(candidate)
        if resolved:
            return resolved
    raise RuntimeError(f"Command '{codex_cmd}' not found in PATH")


def _contains_japanese(text: str) -> bool:
    return any(
        "\u3040" <= ch <= "\u30ff" or "\u4e00" <= ch <= "\u9fff"
        for ch in text
    )


def _strip_frontmatter(text: str) -> str:
    if not text.startswith("---"):
        return text.strip()
    match = re.match(r"^---\s*\n.*?\n---\s*\n?", text, flags=re.DOTALL)
    if match:
        return text[match.end():].strip()
    return text.strip()


def _normalize_body(topic: str, draft: str) -> str:
    body = _strip_frontmatter(draft).strip()
    required_sections = ["## Background", "## Step-by-step", "## Common pitfalls", "## Summary"]
    if all(section.lower() in body.lower() for section in required_sections):
        return body

    return (
        f"結論: {topic} は、最小構成で始めてログを見ながら段階的に広げるのが最短です。\n\n"
        "## Background\n\n"
        "毎日の運用タスクは、手作業だと実行漏れや設定ブレが起きやすくなります。"
        "まずは小さく自動化して、安定を確認してから拡張するのが安全です。\n\n"
        "## Step-by-step\n\n"
        "1. 目的と対象範囲を決める\n\n"
        "最初は1つの処理だけを自動化対象にし、成功条件を明確にします。\n\n"
        "2. 最小構成で設定する\n\n"
        "```bash\n"
        "# 例: 毎日9時に実行\n"
        "openclaw cron add --name \"daily-sample\" --cron \"0 9 * * *\" --tz \"Asia/Tokyo\" --session isolated --message \"ジョブを実行して結果を要約\"\n"
        "```\n\n"
        "3. 実行結果を検証する\n\n"
        "ログと出力を確認し、失敗時の再実行手順を決めます。\n\n"
        "## Common pitfalls\n\n"
        "- タイムゾーンがUTCのままで実行時刻がずれる\n"
        "- 認証切れでジョブが実行できない\n"
        "- 依存サービスが停止していて結果が空になる\n\n"
        "## Summary\n\n"
        f"{topic} は、最小構成で開始してログ確認を定着させると安定して運用できます。"
    )


def _build_tags(topic: str) -> list[str]:
    tags = ["openclaw", "automation"]
    keyword_map = {
        "cron": "cron",
        "shell": "shell",
        "webhook": "webhook",
        "etl": "etl",
        "dag": "dag",
        "api": "api",
        "docker": "docker",
        "kubernetes": "kubernetes",
        "slack": "slack",
        "prometheus": "monitoring",
        "rbac": "security",
        "github actions": "github-actions",
        "ci/cd": "ci-cd",
        "backup": "backup",
    }
    lower_topic = topic.lower()
    for keyword, tag in keyword_map.items():
        if keyword in lower_topic and tag not in tags:
            tags.append(tag)
    if "cron" not in tags and ("定期実行" in topic or "スケジュール" in topic):
        tags.append("cron")
    if "security" not in tags and ("権限" in topic or "機密" in topic):
        tags.append("security")
    if len(tags) < 3:
        tags.append("devops")
    return tags[:5]


def _build_description(topic: str, japanese: bool) -> str:
    if japanese:
        return f"{topic} を実践できるように、設定手順、確認ポイント、よくある失敗を短く整理します。"
    return (
        f"This guide covers {topic} with practical setup steps, validation points, "
        "and common mistakes to avoid."
    )


def _ensure_publishable_post(text: str, source: str) -> str:
    required_markers = [
        "layout:",
        "title:",
        "date:",
        "tags:",
        "description:",
        "## Background",
        "## Step-by-step",
        "## Common pitfalls",
        "## Summary",
    ]
    if not text.strip().startswith("---"):
        raise RuntimeError(f"{source} did not return Jekyll front matter")
    missing = [marker for marker in required_markers if marker.lower() not in text.lower()]
    if missing:
        raise RuntimeError(f"{source} returned incomplete post content: missing {', '.join(missing)}")
    return text.strip()


def build_deterministic_post(topic: str, date: str, draft: str) -> str:
    japanese = _contains_japanese(topic + "\n" + draft)
    body = _normalize_body(topic, draft)
    tags = _build_tags(topic)
    tags_yaml = "\n".join(f"  - {tag}" for tag in tags)
    description = json.dumps(_build_description(topic, japanese), ensure_ascii=False)
    title = json.dumps(topic.strip(), ensure_ascii=False)
    return (
        "---\n"
        "layout: post\n"
        f"title: {title}\n"
        f"date: {date} 09:00:00 +0900\n"
        "tags:\n"
        f"{tags_yaml}\n"
        f"description: {description}\n"
        "---\n\n"
        f"{body.rstrip()}\n"
    )


def finalize_with_codex_cli(topic: str, date: str, draft: str, config: dict) -> str:
    """Call the `codex exec` CLI flow (OAuth flat-rate usage)."""
    codex_cmd = config.get("codex", {}).get("command", "codex")
    codex_executable = _resolve_codex_command(codex_cmd)

    prompt = (
        f"{SYSTEM_PROMPT}\n\n"
        + FINALIZE_TEMPLATE.format(topic=topic, date=date, draft=draft)
    )

    log.info("Calling codex CLI (%s exec) ...", codex_cmd)
    with tempfile.NamedTemporaryFile("w+", encoding="utf-8", suffix=".md", delete=False) as tmp_file:
        output_path = Path(tmp_file.name)

    try:
        result = subprocess.run(
            [codex_executable, "exec", "-o", str(output_path), prompt],
            capture_output=True,
            text=True,
            timeout=600,
        )
        if result.returncode != 0:
            raise RuntimeError(
                f"codex CLI failed (exit {result.returncode}):\n{result.stderr}"
            )

        output = output_path.read_text(encoding="utf-8").strip() if output_path.exists() else ""
    finally:
        if output_path.exists():
            output_path.unlink()
    if not output:
        raise RuntimeError("codex CLI returned empty output")
    return _ensure_publishable_post(output, "codex CLI")


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
    return _ensure_publishable_post(resp.json()["response"].strip(), "Ollama")


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
    return _ensure_publishable_post(result, "Claude API")


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

    log.warning("Using deterministic finalization fallback")
    if errors:
        log.warning("Finalization fallback reasons:\n%s", "\n".join(errors))
    return build_deterministic_post(topic, date, draft)


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
