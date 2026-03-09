#!/usr/bin/env python3
"""Copy the finalized post to _posts/ and commit + push to GitHub."""
from __future__ import annotations

import argparse
import json
import logging
import shutil
import subprocess
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parent.parent
log = logging.getLogger(__name__)


def load_config() -> dict:
    return json.loads((ROOT / "data/config.json").read_text())


def run_git(args: list[str], cwd: Path) -> str:
    result = subprocess.run(
        ["git"] + args,
        cwd=cwd,
        capture_output=True,
        text=True,
    )
    if result.returncode != 0:
        raise RuntimeError(
            f"git {' '.join(args)} failed (exit {result.returncode}):\n"
            f"stdout: {result.stdout}\nstderr: {result.stderr}"
        )
    return result.stdout.strip()


def publish(src_file: Path, slug: str, date: str, config: dict) -> Path:
    repo_root = Path(config.get("repo_root", ".")).resolve()
    if not repo_root.is_absolute():
        repo_root = ROOT / repo_root
    repo_root = repo_root.resolve()

    posts_dir = repo_root / "_posts"
    posts_dir.mkdir(parents=True, exist_ok=True)

    dest_filename = f"{date}-{slug}.md"
    dest_path = posts_dir / dest_filename

    # Copy final post to _posts/
    log.info("Copying %s -> %s", src_file, dest_path)
    shutil.copy2(src_file, dest_path)

    # Git operations
    branch = config.get("branch", "main")
    remote = config.get("git", {}).get("remote", "origin")

    log.info("Running git add ...")
    add_paths = [str(dest_path.relative_to(repo_root))]
    state_path = repo_root / "data" / "state.json"
    if state_path.exists():
        add_paths.append(str(state_path.relative_to(repo_root)))
    run_git(["add"] + add_paths, cwd=repo_root)

    commit_msg = f"post: {date} {slug}"
    log.info("Committing: %s", commit_msg)
    run_git(["commit", "-m", commit_msg], cwd=repo_root)

    log.info("Pushing to %s/%s ...", remote, branch)
    run_git(["push", remote, branch], cwd=repo_root)

    log.info("Published: %s", dest_path)
    return dest_path


def main() -> None:
    parser = argparse.ArgumentParser(description="Commit and push post to GitHub Pages")
    parser.add_argument("--file", required=True, help="Path to finalized markdown file")
    parser.add_argument("--slug", required=True, help="URL slug for the post")
    parser.add_argument("--date", required=True, help="Publication date YYYY-MM-DD")
    parser.add_argument("--dry-run", action="store_true",
                        help="Copy file but skip git commit/push")
    parser.add_argument("--verbose", "-v", action="store_true")
    args = parser.parse_args()

    logging.basicConfig(level=logging.DEBUG if args.verbose else logging.INFO,
                        format="%(levelname)s %(message)s")

    config = load_config()

    if args.dry_run:
        log.info("[DRY RUN] Would publish %s as %s-%s.md", args.file, args.date, args.slug)
        dest = ROOT / "_posts" / f"{args.date}-{args.slug}.md"
        dest.parent.mkdir(parents=True, exist_ok=True)
        shutil.copy2(args.file, dest)
        log.info("[DRY RUN] Copied to %s (no git commit)", dest)
        return

    dest = publish(Path(args.file), args.slug, args.date, config)
    print(str(dest))


if __name__ == "__main__":
    main()
