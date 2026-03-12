---
layout: post
title: "OpenClaw REST APIでカスタムインテグレーションを実装する手順"
date: 2026-03-12 09:00:00 +0900
tags:
  - openclaw
  - rest-api
  - integration
  - automation
  - devops
description: "OpenClaw REST API を使ってカスタムインテグレーションを最小構成で始める手順を解説します。認証、実行確認、失敗時の切り分けまでを短く整理し、段階的に安全に広げる進め方を紹介します。"
---

運用フローをREST APIで外部システムとつなぐと、手作業の抜け漏れを減らしつつ再現性を上げられます。最初から広く作るより、1本のAPI連携を確実に通すほうが結果的に早く安定します。

結論: OpenClaw REST API を使ったカスタムインテグレーション は、最小構成で始めてログを見ながら段階的に広げるのが最短です。

## Background

OpenClaw を外部システムとつなぐときに最初に決めるべきなのは、「どのイベントで呼ぶか」と「成功をどう判定するか」です。ここが曖昧だと、API 呼び出し自体は成功しても運用が安定しません。

特に社内ツール連携では、作成、実行、結果取得を一度に広げないことが重要です。まずは 1 件のリクエストを確実に通し、レスポンスとログの形を固めてから対象を増やします。

## Step-by-step

1. 目的と対象範囲を決める

最初は 1 つの処理だけを API 連携の対象にします。たとえば「毎朝 9:00 にジョブを起動し、結果サマリを取得できれば成功」のように、入力と期待結果を先に固定します。

2. 最小構成で API を呼び出す

まずは認証付きで 1 回リクエストを送り、OpenClaw 側で受理されることを確認します。以下は環境変数を使った最小例です。

```bash
export OPENCLAW_BASE_URL="https://openclaw.example.com"
export OPENCLAW_API_TOKEN="replace-with-real-token"

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

レスポンスで `id` が返ったら、その ID を使って実行確認に進みます。登録と実行を分けると、失敗箇所を切り分けやすくなります。

```bash
export INTEGRATION_ID="replace-with-returned-id"

# 登録済みインテグレーションを即時実行
curl --fail --silent --show-error \
  -X POST "$OPENCLAW_BASE_URL/api/v1/integrations/$INTEGRATION_ID/runs" \
  -H "Authorization: Bearer $OPENCLAW_API_TOKEN" \
  -H "Content-Type: application/json" \
  -d '{}'
```

3. 実行結果を検証する

実行後はステータスとログを必ず確認します。成功レスポンスだけで判断せず、実際に期待した出力が残っているかまで見ます。

```bash
export RUN_ID="replace-with-returned-run-id"

# 実行状態を確認
curl --fail --silent --show-error \
  "$OPENCLAW_BASE_URL/api/v1/runs/$RUN_ID" \
  -H "Authorization: Bearer $OPENCLAW_API_TOKEN"
```

この時点で、失敗時の再実行手順も決めておきます。最低でも「どの ID を見ればよいか」「どのログを確認するか」「どこへ通知するか」は固定してください。

## Common pitfalls

- タイムゾーンを明示せず、想定より 9 時間ずれて実行される  
`schedule.timezone` を `Asia/Tokyo` のように明示し、登録後に API のレスポンスでも同じ値になっているか確認します。

- 認証トークンの期限切れで 401 が返る  
手元で成功したトークンを長期間使い回さず、期限と更新手順を運用に含めます。失敗時はまず `Authorization` ヘッダーとトークンの有効期限を確認してください。

- 同じリクエストを再送して二重実行になる  
再試行を入れる場合は、外部システム側で冪等性キーを持たせるか、OpenClaw 側で重複判定できる識別子を payload に含めます。障害時の自動リトライほど、重複実行の対策が必要です。

- リクエストは通るのに依存サービスが落ちていて結果が空になる  
HTTP 200 だけで成功とみなさず、実行結果の本文や要約フィールドまで確認します。外部 API やローカル LLM に依存する場合は、事前ヘルスチェックを 1 本入れておくと切り分けが速くなります。

## Summary

OpenClaw REST API を使ったカスタムインテグレーションは、まず 1 本の API 呼び出しを確実に通し、次に実行結果とログの見方を固める進め方が安定します。登録、実行、検証を分けて確認すると、認証、時刻ずれ、重複実行といった典型的な失敗を早い段階で潰せます。