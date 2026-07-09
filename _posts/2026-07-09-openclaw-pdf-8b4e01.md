---
layout: post
title: "OpenClawで定期レポートをPDF出力する自動化レシピ"
date: 2026-07-09 09:00:00 +0900
tags: [openclaw, cron, automation, pdf]
description: "OpenClaw CronとPandocを使い、定期レポートをPDFとして自動生成する方法を解説します。最小構成のジョブ登録から手動テスト、ログ確認、障害対策までを紹介します。"
---

OpenClawのCronとPDF変換スクリプトを組み合わせると、日次レポートの生成を定型化できます。最初に手動実行で出力を確認してから、定期実行へ移行するのが安全です。

結論: OpenClawで定期レポートをPDF出力するなら、変換処理を独立したスクリプトにまとめ、手動テスト、Cron登録、実行履歴の確認という順で導入するのが最短です。

## Background

毎日のレポート作成を手作業にすると、実行漏れや集計条件のばらつきが発生します。生成処理をスクリプトとして固定すれば、同じ条件で繰り返し実行できます。

この例では、ホストの稼働状況とディスク使用量をMarkdownにまとめ、PandocでPDFへ変換します。OpenClawはスクリプトの定期実行と履歴管理を担当します。

## Step-by-step

1. 必要なコマンドを確認する

OpenClaw Gatewayが起動しており、`pandoc`とPDF生成エンジンが利用できることを確認します。

```bash
openclaw gateway status
pandoc --version
xelatex --version
```

Ubuntu系環境では、必要なパッケージを次のように導入できます。

```bash
sudo apt-get update
sudo apt-get install -y pandoc texlive-xetex fonts-noto-cjk
```

2. PDF生成スクリプトを作成する

次の内容を`/opt/reports/generate-daily-report.sh`として保存します。出力先は`/opt/reports/output`です。

```bash
#!/usr/bin/env bash
set -euo pipefail

OUTPUT_DIR="/opt/reports/output"
GENERATED_AT="$(date '+%Y-%m-%d %H:%M:%S %Z')"
REPORT_DATE="$(date '+%Y-%m-%d')"
MARKDOWN_FILE="${OUTPUT_DIR}/daily-report-${REPORT_DATE}.md"
PDF_FILE="${OUTPUT_DIR}/daily-report-${REPORT_DATE}.pdf"

mkdir -p "${OUTPUT_DIR}"

{
  printf '# 日次運用レポート\n\n'
  printf -- '- 生成日時: %s\n' "${GENERATED_AT}"
  printf -- '- ホスト名: %s\n\n' "$(hostname)"

  printf '## 稼働状況\n\n```text\n'
  uptime
  printf '```\n\n'

  printf '## ディスク使用量\n\n```text\n'
  df -h
  printf '```\n'
} > "${MARKDOWN_FILE}"

pandoc "${MARKDOWN_FILE}" \
  --from markdown \
  --pdf-engine=xelatex \
  -V mainfont="Noto Sans CJK JP" \
  -V geometry:margin=24mm \
  --output "${PDF_FILE}"

test -s "${PDF_FILE}"
printf 'PDFを生成しました: %s\n' "${PDF_FILE}"
```

実行権限を付与し、まず単体で動作を確認します。

```bash
sudo mkdir -p /opt/reports/output
sudo chmod +x /opt/reports/generate-daily-report.sh

/opt/reports/generate-daily-report.sh
ls -lh /opt/reports/output/
```

3. OpenClaw Cronへ登録する

毎日9時にスクリプトを実行するジョブを登録します。`--exact`を指定し、負荷分散による実行時刻の自動調整を無効にします。

```bash
openclaw cron create "0 9 * * *" \
  --name "daily-pdf-report" \
  --tz "Asia/Tokyo" \
  --exact \
  --command-argv '["/opt/reports/generate-daily-report.sh"]' \
  --command-cwd "/opt/reports"
```

登録内容とタイムゾーンを確認します。

```bash
openclaw cron list
```

4. 手動実行して結果を検証する

一覧から取得したジョブIDを指定し、完了まで待機します。`<job-id>`は実際の値へ置き換えてください。

```bash
openclaw cron run <job-id> \
  --wait \
  --wait-timeout 10m \
  --poll-interval 2s
```

実行履歴とPDFファイルを確認します。

```bash
openclaw cron runs --id <job-id> --limit 20
ls -lh /opt/reports/output/*.pdf
```

問題の調査中は、別のターミナルでGatewayのログを追跡できます。

```bash
openclaw logs --follow
```

## Common pitfalls

- 実行時刻が想定とずれる  
  `--tz "Asia/Tokyo"`を明示し、登録後に`openclaw cron list`で設定値を確認します。毎時0分などの正確な実行が必要なら`--exact`も指定します。

- Gateway停止中にジョブが実行されない  
  OpenClaw CronはGatewayプロセス内で動作します。`openclaw gateway status`を監視し、常時稼働するサービスとして管理してください。

- Cronから実行するとコマンドが見つからない  
  Cron環境の`PATH`は対話シェルと異なる場合があります。スクリプト内では`pandoc`などの絶対パスを使うか、冒頭で`PATH`を明示してください。

- PDFは生成されるが日本語が文字化けする  
  日本語フォントを導入し、Pandocへ`--pdf-engine=xelatex`と`mainfont`を指定します。フォント名は`fc-list`で確認できます。

- 出力先への書き込みで失敗する  
  Gatewayを実行するユーザーに、出力ディレクトリの書き込み権限を付与します。手動テストも同じユーザーで実行すると権限差を発見しやすくなります。

- 外部APIの認証切れで集計に失敗する  
  APIを利用する場合は、スクリプトの終了コードを非ゼロにして失敗をOpenClawへ伝えます。定期的に`openclaw cron runs --id <job-id>`を確認し、認証情報の更新手順も運用に含めます。

- PDFが蓄積してディスクを圧迫する  
  保存期間を決め、古いファイルを削除する処理を追加します。たとえば30日より古いPDFは次のコマンドで削除できます。

```bash
find /opt/reports/output \
  -type f \
  -name 'daily-report-*.pdf' \
  -mtime +30 \
  -delete
```

## Summary

OpenClawで定期レポートをPDF出力する場合は、PDF生成を独立したスクリプトとして実装し、OpenClaw Cronから決まった時刻に呼び出します。

最小構成で手動テストを行い、Cron登録後は実行履歴と出力ファイルを確認してください。タイムゾーン、Gatewayの稼働状態、実行ユーザーの権限、フォント、保存期間まで決めておくと、安定した運用につながります。