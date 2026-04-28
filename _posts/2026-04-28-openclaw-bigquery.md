---
layout: post
title: "OpenClaw と BigQuery で始めるデータパイプライン構築入門"
date: 2026-04-28 09:00:00 +0900
tags:
  - openclaw
  - bigquery
  - etl
  - automation
  - data-pipeline
description: "OpenClaw と BigQuery を使って、最小構成のデータパイプラインを安全に立ち上げる手順を解説します。ジョブ登録、BigQuery 側の確認、運用で詰まりやすいポイントまでを短く整理します。"
---

日次集計やログ取り込みを手作業で回していると、実行漏れや設定差分がすぐに運用負債になります。OpenClaw と BigQuery の組み合わせは、小さく始めてログを見ながら広げる構成に向いています。

結論: OpenClaw と BigQuery を使ったデータパイプライン構築 は、最小構成で始めてログを見ながら段階的に広げるのが最短です。

## Background

データパイプラインを安定させるうえで重要なのは、最初から複雑な変換を詰め込まないことです。まずは「決まった時刻に処理が走り、BigQuery に期待どおりの結果が残る」状態を作ります。

特に運用初期は、失敗時に何を見ればよいかが明確な構成にしておくべきです。1本のジョブを確実に回せるようになると、後続の集計や通知も追加しやすくなります。

## Step-by-step

1. 目的と対象範囲を決める

最初に自動化する対象は1つに絞ります。たとえば「毎朝9時に前日分の集計テーブルを更新し、成功件数を確認できれば完了」のように、成功条件を先に固定します。

入力元、出力先、更新頻度を先に決めておくと、ジョブ失敗時の切り分けが速くなります。BigQuery では、対象のプロジェクト、データセット、テーブル名を先に揃えておくのが実務的です。

```bash
# 実行前に使う値を明示しておく
export GCP_PROJECT_ID="my-project"
export BQ_DATASET="analytics"
export BQ_LOCATION="asia-northeast1"
```

2. 最小構成で設定する

BigQuery 側は、まず受け皿となるデータセットを作成します。すでに存在する場合はこの手順をスキップできます。

```bash
# BigQuery のデータセットを作成
bq --location="${BQ_LOCATION}" mk --dataset "${GCP_PROJECT_ID}:${BQ_DATASET}"
```

次に、OpenClaw で日次ジョブを登録します。最初は処理内容を絞り、結果を要約して確認できるメッセージにしておくと運用しやすくなります。

```bash
# 毎日 09:00 JST にジョブを実行
openclaw cron add \
  --name "daily-bigquery-pipeline" \
  --cron "0 9 * * *" \
  --tz "Asia/Tokyo" \
  --session isolated \
  --message "BigQuery の日次集計ジョブを実行し、成功可否と処理件数を要約"
```

登録後は、スケジュール設定を必ず一覧で確認します。時刻とタイムゾーンの確認を省くと、初回のずれに気づきにくくなります。

```bash
# ジョブ名、cron式、タイムゾーンを確認
openclaw cron list
```

3. 実行結果を検証する

最初の検証では、BigQuery に「更新されたこと」が明確に分かる小さな出力を作るのが安全です。以下は、実行日を残す確認用テーブルの例です。

```bash
# 動作確認用の最小クエリ
bq query \
  --use_legacy_sql=false \
  "
  CREATE OR REPLACE TABLE \`${GCP_PROJECT_ID}.${BQ_DATASET}.daily_pipeline_check\` AS
  SELECT
    CURRENT_DATE('Asia/Tokyo') AS run_date,
    CURRENT_TIMESTAMP() AS processed_at,
    'ok' AS status
  "
```

書き込み後は、テーブルの中身を即確認します。ジョブが動いたかだけでなく、想定した日付や件数になっているかを見ることが重要です。

```bash
# 書き込み結果を確認
bq query \
  --use_legacy_sql=false \
  "
  SELECT run_date, processed_at, status
  FROM \`${GCP_PROJECT_ID}.${BQ_DATASET}.daily_pipeline_check\`
  ORDER BY processed_at DESC
  LIMIT 5
  "
```

ここで確認したいのは、実行時刻、出力先テーブル、レコード内容の3点です。失敗時は再実行手順と確認クエリをセットで残しておくと、運用に移したあとも迷いません。

## Common pitfalls

- タイムゾーンを指定せず、意図した時刻にジョブが動かない  
`--tz "Asia/Tokyo"` を明示し、`openclaw cron list` で設定値を確認します。BigQuery 側の `CURRENT_DATE()` や `CURRENT_TIMESTAMP()` も、必要ならタイムゾーン前提をそろえてください。

- BigQuery の認証は通るが、対象データセットへの権限が不足している  
`bq` コマンドが使えても、書き込み権限がないとジョブは失敗します。事前に対象プロジェクトとデータセットへ必要な IAM 権限があるかを確認し、最初は `CREATE OR REPLACE TABLE` のような単純なクエリで疎通確認を行います。

- ジョブの責務が広すぎて、失敗時に原因を切り分けられない  
最初から抽出、変換、集計、通知を1本に詰め込まないでください。まずは「BigQuery に正しく書ける」ジョブを独立させ、安定後に後続処理を分けて追加します。

- 実行は成功扱いなのに、期待したデータが入っていない  
終了コードだけでは不十分です。検証用クエリを用意し、更新件数、対象日付、重複有無を毎回確認できるようにします。確認用テーブルや件数チェックを最初から入れておくと、異常を早く見つけられます。

## Summary

OpenClaw と BigQuery の組み合わせでは、最初に小さな日次ジョブを1本だけ安定させるのが最も実用的です。ジョブ登録、BigQuery への最小書き込み、検証クエリの3点を先に固めることで、失敗を抑えながら安全にパイプラインを拡張できます。