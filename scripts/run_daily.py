#!/usr/bin/env python3
"""
Daily orchestrator for OpenClaw Tech Blog Factory.

Usage:
    python scripts/run_daily.py
    python scripts/run_daily.py --date 2026-03-04
    python scripts/run_daily.py --dry-run
"""
from __future__ import annotations

import argparse
import json
import logging
import sys
import traceback
from datetime import date, datetime
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
sys.path.insert(0, str(ROOT / "scripts"))


def setup_logging(date_str: str, verbose: bool) -> logging.Logger:
    logs_dir = ROOT / "logs"
    logs_dir.mkdir(parents=True, exist_ok=True)

    log_file = logs_dir / f"{date_str}.log"
    level = logging.DEBUG if verbose else logging.INFO

    handlers: list[logging.Handler] = [
        logging.StreamHandler(sys.stdout),
        logging.FileHandler(log_file, encoding="utf-8"),
    ]
    logging.basicConfig(
        level=level,
        format="%(asctime)s %(levelname)-8s %(message)s",
        datefmt="%H:%M:%S",
        handlers=handlers,
    )
    return logging.getLogger("run_daily")


def load_config() -> dict:
    return json.loads((ROOT / "data/config.json").read_text())


def load_state() -> dict:
    state_file = ROOT / "data/state.json"
    if state_file.exists():
        return json.loads(state_file.read_text())
    return {"seen_topics": [], "last_run": None, "last_slug": None, "total_posts": 0}


def save_state(state: dict) -> None:
    state_file = ROOT / "data/state.json"
    state_file.write_text(json.dumps(state, ensure_ascii=False, indent=2), encoding="utf-8")


def step_select_topic(config: dict, log: logging.Logger) -> tuple[str, str]:
    log.info("=" * 60)
    log.info("STEP 1: Selecting topic")
    from topic import select_topic
    topic, slug = select_topic(config)
    log.info("  Topic: %s", topic)
    log.info("  Slug:  %s", slug)
    return topic, slug


def step_draft(topic: str, draft_path: Path, config: dict, log: logging.Logger) -> None:
    log.info("=" * 60)
    log.info("STEP 2: Generating rough draft (Local LLM)")
    from draft_local_llm import generate_draft
    draft_text = generate_draft(topic, config)
    draft_path.parent.mkdir(parents=True, exist_ok=True)
    draft_path.write_text(draft_text, encoding="utf-8")
    log.info("  Draft: %s (%d chars)", draft_path, len(draft_text))


def step_finalize(topic: str, date_str: str, draft_path: Path,
                  final_path: Path, config: dict, log: logging.Logger) -> None:
    log.info("=" * 60)
    log.info("STEP 3: Finalizing post (Codex CLI / OpenAI)")
    from final_codex import finalize
    draft_text = draft_path.read_text(encoding="utf-8")
    final_text = finalize(topic, date_str, draft_text, config)
    final_path.parent.mkdir(parents=True, exist_ok=True)
    final_path.write_text(final_text, encoding="utf-8")
    log.info("  Final: %s (%d chars)", final_path, len(final_text))


def step_validate(final_path: Path, log: logging.Logger) -> None:
    log.info("=" * 60)
    log.info("STEP 4: Validating post")
    from validate_post import validate_post
    errors = validate_post(final_path, check_filename=False)
    if errors:
        for err in errors:
            log.error("  ✗ %s", err)
        raise RuntimeError(f"Validation failed with {len(errors)} error(s)")
    log.info("  Validation passed")


def step_publish(final_path: Path, slug: str, date_str: str,
                 config: dict, dry_run: bool, log: logging.Logger) -> Path:
    log.info("=" * 60)
    log.info("STEP 5: Publishing post%s", " [DRY RUN]" if dry_run else "")
    from git_publish import publish
    import shutil

    posts_dir = ROOT / "_posts"
    posts_dir.mkdir(parents=True, exist_ok=True)

    if dry_run:
        dest = posts_dir / f"{date_str}-{slug}.md"
        shutil.copy2(final_path, dest)
        log.info("  [DRY RUN] Copied to %s (no git commit)", dest)
        return dest

    dest = publish(final_path, slug, date_str, config)
    log.info("  Published: %s", dest)
    return dest


def update_state(state: dict, topic: str, slug: str, date_str: str) -> dict:
    state.setdefault("seen_topics", [])
    state["seen_topics"].append({
        "topic": topic,
        "slug": slug,
        "date": date_str,
    })
    # Keep only last 90 days worth (rough limit)
    state["seen_topics"] = state["seen_topics"][-90:]
    state["last_run"] = datetime.now().isoformat()
    state["last_slug"] = slug
    state["total_posts"] = state.get("total_posts", 0) + 1
    return state


def main() -> None:
    parser = argparse.ArgumentParser(description="Daily blog post orchestrator")
    parser.add_argument("--date", default=None,
                        help="Target date YYYY-MM-DD (default: today)")
    parser.add_argument("--dry-run", action="store_true",
                        help="Run full pipeline but skip git commit/push")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    date_str = args.date or date.today().isoformat()
    log = setup_logging(date_str, args.verbose)

    log.info("OpenClaw Daily Blog Factory — %s%s",
             date_str, " [DRY RUN]" if args.dry_run else "")

    tmp_dir = ROOT / "tmp"
    draft_path = tmp_dir / f"{date_str}-draft.md"
    final_path = tmp_dir / f"{date_str}-final.md"

    config = load_config()
    state = load_state()
    original_state = json.loads(json.dumps(state, ensure_ascii=False))
    state_saved = False

    topic: str = ""
    slug: str = ""

    try:
        topic, slug = step_select_topic(config, log)
        step_draft(topic, draft_path, config, log)
        step_finalize(topic, date_str, draft_path, final_path, config, log)
        step_validate(final_path, log)

        state = update_state(state, topic, slug, date_str)
        save_state(state)
        state_saved = True

        dest = step_publish(final_path, slug, date_str, config, args.dry_run, log)

        log.info("=" * 60)
        log.info("SUCCESS: %s", dest)
        log.info("Total posts published: %d", state["total_posts"])

    except Exception:
        log.error("=" * 60)
        log.error("FAILED on %s", date_str)
        log.error(traceback.format_exc())

        if state_saved:
            save_state(original_state)
            log.warning("Restored data/state.json after failed publish")

        # Clean up any partial files in _posts/
        partial = ROOT / "_posts" / f"{date_str}-{slug}.md"
        if slug and partial.exists():
            partial.unlink()
            log.warning("Removed partial post file: %s", partial)

        sys.exit(1)


if __name__ == "__main__":
    main()
