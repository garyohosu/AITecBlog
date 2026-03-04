# OpenClaw Daily Tech Blog Factory

OpenClaw に関する技術記事を **毎日1件自動生成・公開** する GitHub Pages (Jekyll) サイト。

## アーキテクチャ

```
Local LLM (Ollama)  →  下書き生成
Codex CLI（定額/OAuth） →  記事仕上げ
Git                 →  _posts/ にコミット・プッシュ
GitHub Pages        →  Jekyll でビルド・公開
```

## ディレクトリ構成

```
.
├── _config.yml          # Jekyll 設定（AdSense 設定を含む）
├── _layouts/
│   ├── default.html     # ベースレイアウト（Bootstrap 5 ダークテーマ）
│   └── post.html        # 記事レイアウト（AdSense 上下挿入）
├── _includes/
│   └── adsense.html     # AdSense スニペット
├── _posts/              # 生成された記事（YYYY-MM-DD-slug.md）
├── index.html           # 記事一覧ページ
├── scripts/
│   ├── run_daily.py     # メインオーケストレーター
│   ├── topic.py         # トピック選択（Ollama + 重複防止）
│   ├── draft_local_llm.py  # 下書き生成（Ollama）
│   ├── final_codex.py   # 記事仕上げ（Codex CLI、必要ならOllamaフォールバック）
│   ├── validate_post.py # バリデーション
│   ├── git_publish.py   # Git コミット・プッシュ
│   └── slugify.py       # URL スラグ生成
├── data/
│   ├── config.json      # 設定ファイル
│   ├── state.json       # 投稿済みトピック記録
│   └── topics_seed.md   # シードトピック一覧
└── logs/                # 実行ログ（YYYY-MM-DD.log）
```

## 初期セットアップ

### 1. 依存パッケージのインストール

Python パッケージ:

```bash
pip install -r requirements.txt
```

Ruby (Jekyll):

```bash
bundle install
```

### 2. Ollama のセットアップ

```bash
# Ollama をインストール（https://ollama.com）
ollama pull llama3.1:8b
```

`data/config.json` の `local_llm.model` を使用するモデル名に合わせて変更してください。

### 3. 設定ファイルの編集

`data/config.json`:

```json
{
  "local_llm": {
    "model": "llama3.1:8b",
    "endpoint": "http://localhost:11434"
  },
  "adsense": {
    "client": "ca-pub-XXXX",
    "slot": "XXXX"
  }
}
```

### 4. Codex CLI の認証（必須）

本プロジェクトは OpenAI API キーを使わず、Codex CLI の OAuth セッション（定額運用）を前提にします。

```bash
codex
# ログインを完了して終了
```

必要に応じて事前確認:

```bash
codex exec "OKだけ返して"
```

### 5. GitHub Pages の設定

リポジトリの Settings → Pages で `main` ブランチを公開ソースに設定してください。

## 実行方法

### 手動実行

```bash
# 今日の記事を生成・公開
python scripts/run_daily.py

# 日付を指定して実行
python scripts/run_daily.py --date 2026-03-04

# ドライラン（git push しない）
python scripts/run_daily.py --dry-run

# 詳細ログ付き
python scripts/run_daily.py --verbose
```

### 各スクリプトを単独実行

```bash
# トピック選択のみ
python scripts/topic.py

# 下書き生成のみ
python scripts/draft_local_llm.py --topic "OpenClaw Cron の基本設定" --out tmp/draft.md

# 仕上げのみ
python scripts/final_codex.py --topic "OpenClaw Cron の基本設定" \
  --draft tmp/draft.md --out tmp/final.md --date 2026-03-04

# バリデーションのみ
python scripts/validate_post.py --file tmp/final.md --no-filename-check

# 公開のみ
python scripts/git_publish.py --file tmp/final.md \
  --slug openclaw-cron-basics --date 2026-03-04
```

### OpenClaw Cron での自動化

OpenClaw のジョブ設定例（毎日 09:00 JST に実行）:

```yaml
name: openclaw-blog-daily
schedule: "0 9 * * *"
timezone: Asia/Tokyo
command: python /path/to/AITecBlog/scripts/run_daily.py
```

### GitHub Actions での自動化（代替）

`.github/workflows/daily-post.yml` を作成:

```yaml
name: Daily Blog Post
on:
  schedule:
    - cron: "0 0 * * *"  # UTC 00:00 = JST 09:00
  workflow_dispatch:

jobs:
  post:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.12"
      - run: pip install -r requirements.txt
      - run: python scripts/run_daily.py
```

## ローカルでの Jekyll プレビュー

```bash
bundle exec jekyll serve
# http://localhost:4000 でプレビュー
```

## 記事の構成（テンプレート）

生成されるすべての記事は以下の構成に従います:

1. **1行結論**（冒頭に配置）
2. `## Background` — 背景・前提知識
3. `## Step-by-step` — 番号付き手順 + コードブロック
4. `## Common pitfalls` — よくあるミスと対処法
5. `## Summary` — まとめ

## 重複防止

`data/state.json` に投稿済みトピックの記録を保持し、直近 60 日間（`dedupe_days`）の重複を防止します。

## トラブルシューティング

| 症状 | 対処 |
|------|------|
| Ollama 接続エラー | `ollama serve` が起動しているか確認 |
| `No valid topic found` | `data/topics_seed.md` にトピックを追加、または `dedupe_days` を小さくする |
| Git push 失敗 | リモートリポジトリの認証情報を確認 |
| バリデーションエラー | `logs/YYYY-MM-DD.log` でエラー内容を確認 |

## ライセンス

MIT
