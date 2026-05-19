---
layout: post
title: "OpenClaw REST API でカスタムインテグレーションを実装する手順"
date: 2026-05-19 09:00:00 +0900
tags:
  - openclaw
  - rest-api
  - integration
  - automation
  - devops
description: "OpenClaw REST API を使って外部システムと連携する最小構成の進め方を解説します。認証、登録、実行確認、失敗時の切り分けまでを短く整理し、段階的に安全に広げる方法を紹介します。"
---

OpenClaw を REST API 経由で外部システムとつなぐと、定型運用を手作業から切り離しやすくなります。最初から広く作り込むより、1 本の連携を確実に通してから広げるほうが、結果的に安定します。

結論: OpenClaw REST API を使ったカスタムインテグレーション は、最小構成で始めてログを見ながら段階的に広げるのが最短です。

## Background

毎日の運用タスクは、手作業だと実行漏れや設定ブレが起きやすくなります。REST API 連携にすると、呼び出し条件と処理内容をコードで固定できるため、再現性を上げやすくなります。

ただし、最初から複数の処理や通知先をまとめて連携すると、失敗時の切り分けが難しくなります。まずは 1 つの処理だけを自動化し、期待どおりに動くことを確認してから拡張するのが安全です。

## Step-by-step

1. 目的と対象範囲を決める

最初は 1 つの処理だけを API 連携の対象にします。たとえば「毎朝 9:00 にジョブを起動し、結果サマリを取得できれば成功」のように、成功条件を先に決めます。

入力、実行タイミング、期待する出力が曖昧なまま進めると、API 呼び出しが成功しても運用は安定しません。まずは「何を呼び、何が返れば OK か」を 1 行で説明できる状態にします。

2. 最小構成で登録する

最初の一歩は、認証付きで 1 件のインテグレーションを登録することです。以下は、環境変数を使って毎日 9:00 JST に実行する設定を登録する最小例です。

```bash
export OPENCLAW_BASE_URL="https://openclaw.example.com"
export OPENCLAW_API_TOKEN="replace-with-real-token"

# スケジュール実行するインテグレーションを登録
curl --fail --silent --show-error \
  -X POST "$OPENCLAW_BASE_URL/api/v1/integrations" \
  -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{
    "name": "daily-sample",
    "trigger": {
      "type": "schedule",
      "cron": "0 9 * * *",
      "timezone": "Asia/Tokyo"
    },
    "action": {
      "type": "prompt",
      "message": "ジョブを実行して結果を要約"
    }
  }'
```

レスポンスで `id` が返ったら、その ID を控えます。登録と実行を分けて確認すると、失敗箇所を切り分けやすくなります。

3. 実行結果を検証する

登録できたら、次は明示的に 1 回実行して結果を見ます。スケジュール任せにせず、その場で実行してレスポンスとログを確認したほうが早く詰められます。

```bash
export INTEGRATION_ID="replace-with-returned-id"

# 登録済みインテグレーションを即時実行
curl --fail --silent --show-error \
  -X POST "$OPENCLAW_BASE_URL/api/v1/integrations/$INTEGRATION_ID/runs" \
  -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

実行後は、返ってきた `run_id` を使って状態を確認します。HTTP 200 だけで成功と判断せず、実際に期待した出力が残っているかまで見ます。

```bash
export RUN_ID="replace-with-returned-run-id"

# 実行状態と結果を確認
curl --fail --silent --show-error \
  "$OPENCLAW_BASE_URL/api/v1/runs/$RUN_ID" \
  -H "Authorization: Bearer $OPENCLAW_API_TOKEN"
```

この段階で、失敗時の再実行手順も決めておくと運用が安定します。最低でも「どの ID を確認するか」「どのログを見るか」「どこへ通知するか」は固定しておくべきです。

## Common pitfalls

- タイムゾーンを明示せず、想定より 9 時間ずれて実行される  
`trigger.timezone` を `Asia/Tokyo` のように明示し、登録後のレスポンスでも同じ値になっていることを確認します。

- 認証トークンの期限切れや設定ミスで 401 が返る  
`Authorization` ヘッダーの形式を固定し、トークンの有効期限と更新手順を運用手順書に含めます。失敗時は、まず認証情報から確認するのが最短です。

- 再試行時に同じジョブを二重実行してしまう  
障害時の再送を想定し、外部システム側で冪等性キーを持たせるか、重複判定に使える識別子を payload に含めます。自動リトライを入れるほど、この対策は重要です。

- API 呼び出しは成功しても依存サービスが停止していて結果が空になる  
ローカル LLM や外部 API に依存する場合は、事前ヘルスチェックを 1 本入れておくと切り分けが速くなります。成功判定はステータスコードではなく、出力内容まで含めて行います。

## Summary

OpenClaw REST API を使ったカスタムインテグレーションは、まず 1 本の API 呼び出しを確実に通し、その後に実行結果とログの見方を固める進め方が安定します。登録、実行、検証を分けて確認すると、認証エラー、時刻ずれ、重複実行といった典型的な失敗を早い段階で潰せます。