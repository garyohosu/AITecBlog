# spec.md — OpenClaw Daily Tech Blog Factory (GitHub Pages / Jekyll)

## 0. Summary
Build a fully automated pipeline that publishes **one OpenClaw-focused technical blog post per day** to a **GitHub Pages (Jekyll)** site. Scheduling is done via **OpenClaw Cron**. Content generation is split between **Local LLM** (cheap/slow: ideation + rough draft) and **Codex CLI (OAuth/定額運用)** (quality: final draft + correctness). **Google AdSense must appear on every article** by enforcing placement in the Jekyll layout, not per-article authoring.

googleアドセンスを各ページに入れておくこと
<script async src="https://pagead2.googlesyndication.com/pagead/js/adsbygoogle.js?client=ca-pub-6743751614716161"
     crossorigin="anonymous"></script>

各ページはCDNを使ったモダン技術ブログ的外観のサイトとすること



---

## 1. Goals
- Publish **1 post/day** to GitHub Pages (Jekyll) under `_posts/`.
- Posts are always valid Jekyll posts:
  - filename: `_posts/YYYY-MM-DD-<slug>.md`
  - YAML front matter includes `title`, `date` (with `+0900`), `tags`, `description`
- Topic domain is initially **OpenClaw** (features, cron jobs, workflows, integration patterns, troubleshooting, examples).
- Split generation:
  - Local LLM: topic candidates, outline, rough draft
  - Codex CLI: final article, code examples, style consistency, front matter
- **AdSense is guaranteed to be included on all posts** by embedding in Jekyll layout (`_layouts/post.html`) and/or includes.
- Fully automated commit/push to the Pages repo.

---

## 2. Non-goals
- No database.
- No user accounts.
- No comments system.
- No paid content gating.
- No multi-language output (initially).
- No image generation pipeline (optional later).

---

## 3. Operating Assumptions
- GitHub Pages site is a Jekyll repo with posts rendered from `_posts/`.
- Timezone is **Asia/Tokyo (+0900)**; publishing time is fixed daily.
- OpenClaw Cron triggers a single orchestration entrypoint.
- Codex CLI is available on the runner machine (where OpenClaw runs), with required API credentials configured.
- Local LLM is available (e.g., via Ollama) and can be called from CLI.

---

## 4. Repository Layout (Target)
Example (Jekyll):
- `_posts/`
  - `YYYY-MM-DD-openclaw-*.md`
- `_layouts/`
  - `post.html`  (AdSense insertion enforced here)
- `_includes/`
  - `adsense.html` (optional include for reuse)
- `scripts/`
  - `run_daily.py` (orchestrator entrypoint)
  - `topic.py` (topic selection utilities)
  - `draft_local_llm.py` (local LLM calls)
  - `final_codex.py` (Codex CLI calls)
  - `validate_post.py` (lint/validation)
  - `git_publish.py` (commit/push)
  - `slugify.py`
- `data/`
  - `state.json` (seen topics, last run info, duplication guard)
  - `topics_seed.md` (optional curated topic list)
- `logs/`
  - `YYYY-MM-DD.log`

---

## 5. Daily Workflow (End-to-end)
### 5.1 Trigger
- OpenClaw Cron triggers `scripts/run_daily.py`.

### 5.2 Steps
1) **Select topic**
   - generate 10 candidates (local LLM)
   - filter by rules (see §6)
   - choose 1 topic (avoid duplicates vs last N days)
2) **Research**
   - (initial) offline: rely on a curated OpenClaw knowledge snippets file OR allow web research later if permitted
   - output a structured research brief: bullets + key terms + cited links (if used)
3) **Draft (Local LLM)**
   - create outline (H2 headings required)
   - create rough markdown draft (no front matter yet)
4) **Finalize (Codex CLI)**
   - produce final markdown with:
     - front matter
     - clear structure (see §7)
     - runnable code blocks when possible
     - “Common pitfalls” section
5) **Validate**
   - filename format
   - required front matter keys exist
   - at least 2 H2 sections
   - no forbidden strings (secrets)
   - optional: markdownlint/textlint
6) **Write file**
   - `_posts/YYYY-MM-DD-<slug>.md`
7) **Commit + Push**
   - `git add _posts/...`
   - commit message: `post: YYYY-MM-DD <slug>`
   - push to default branch (e.g., `main`)
8) **Report**
   - log success/failure
   - update `data/state.json`

---

## 6. Topic Rules (OpenClaw)
A candidate topic is acceptable if:
- It is about OpenClaw usage, architecture, automation, cron, integrations, or troubleshooting.
- It can be explained with a concrete example (commands, config, workflow).
- It can contain at least one code block or configuration snippet.

Reject topics that:
- are too vague (“OpenClaw is cool”)
- duplicate an existing post slug/title in the last N days (default N=60)
- require unknown private info

---

## 7. Article Template (Mandatory)
All posts must follow this structure:

1. **One-line conclusion** near the top
2. `## Background`
3. `## Step-by-step`
   - numbered steps
   - code blocks (shell/python/yaml) where appropriate
4. `## Common pitfalls`
5. `## Summary`

Notes:
- Use **H2 headings** (`##`) consistently (used for ad insertion hooks).
- Use short paragraphs.
- Avoid tables (copy/paste friendliness).

---

## 8. AdSense Enforcement (Mandatory)
### 8.1 Preferred Method: Layout-level insertion (guarantees coverage)
- Insert AdSense in `_layouts/post.html` so every post includes it, without relying on generated content.

Option A: Inline insertion in `post.html`
- Place ad block:
  - after article header (top)
  - optionally after first H2 (mid)
  - optionally at end

Option B: `_includes/adsense.html`
- put AdSense snippet in `_includes/adsense.html`
- include it from layout

### 8.2 “Mid-article” insertion strategy (optional)
- Place the include between sections, e.g., after first H2.
- Implementation can be simple (top + bottom) to avoid fragile HTML splitting.

### 8.3 Never store AdSense secrets in generated posts
- AdSense client and slot IDs are not “secrets” but must be treated as configuration:
  - store in `_config.yml` or includes
  - avoid duplicating in every post if possible

---

## 9. Configuration
Create a single config file `data/config.json`:

- `timezone`: `Asia/Tokyo`
- `publish_hour`: int (e.g., 9)
- `dedupe_days`: int (e.g., 60)
- `repo_root`: path to Pages repo
- `branch`: `main`
- `local_llm`:
  - `provider`: `ollama`
  - `model`: e.g., `llama3.1:8b`
  - `endpoint`: default
- `codex`:
  - `command`: `codex`
  - `model`: optional
- `git`:
  - `remote`: `origin`
- `adsense`:
  - `client`: `ca-pub-XXXX`
  - `slot`: `XXXX`
  - `enabled`: true

---

## 10. Interfaces (Functions / Commands)
### 10.1 Orchestrator
- `python scripts/run_daily.py --date YYYY-MM-DD`

### 10.2 Local LLM
- `python scripts/draft_local_llm.py --topic "<topic>" --out tmp/draft.md`

### 10.3 Codex CLI finalization
- `python scripts/final_codex.py --topic "<topic>" --draft tmp/draft.md --out tmp/final.md`

### 10.4 Validation
- `python scripts/validate_post.py --file tmp/final.md`

### 10.5 Publish
- `python scripts/git_publish.py --file tmp/final.md --slug <slug> --date YYYY-MM-DD`

---

## 11. Prompting Guidelines (for Claude Code / Agents)
### 11.1 Local LLM prompts (cheap)
- “Generate 10 OpenClaw post ideas for engineers; each must have a concrete demo.”
- “Create an outline with H2 headings; include at least 1 code/config snippet.”
- “Write a rough draft; focus on steps, not prose.”

### 11.2 Codex CLI prompts (quality)
- “Rewrite the draft into a publish-ready Jekyll post with front matter.”
- “Ensure commands/config examples are consistent and runnable.”
- “Add Common pitfalls section; keep paragraphs short; no tables.”

---

## 12. Safety & Compliance
- Never include credentials, tokens, private repo URLs, or internal-only identifiers in posts.
- If using web research later, cite sources and avoid copying large text.
- Validate that no environment variables are printed into the post.

---

## 13. Acceptance Criteria
- Running `scripts/run_daily.py` produces exactly one new file in `_posts/` with correct filename & front matter.
- The new post builds on GitHub Pages without errors.
- AdSense appears on the rendered post (layout-level enforcement).
- Duplicate prevention works (no repeated slug/title within `dedupe_days`).
- Failures produce a clear log and do not leave half-written posts committed.

---

## 14. Next Extensions (Optional)
- Add GitHub Actions as a fallback scheduler (if OpenClaw is down).
- Add a small “topic registry” (Markdown list) to intentionally cover OpenClaw features systematically.
- Add lightweight link checking (HTTP HEAD) during validation.
