---
layout: post
title: "OpenClaw Gatewayを安全に公開する方法: TailscaleとReverse Proxyの実践パターン"
date: 2026-06-16 09:00:00 +0900
tags: [openclaw, tailscale, reverse-proxy, security]
description: "OpenClaw Gatewayを安全に公開するための基本パターンを、TailscaleとReverse Proxyに分けて解説します。最小構成から始め、認証、TLS、ログ確認を段階的に整える運用手順を紹介します。"
---

OpenClaw Gatewayを外部から使えるようにすると、ローカル環境や社内環境の自動化を柔軟に扱えます。一方で、Gatewayは実行系に近い入口になるため、公開範囲を誤るとリスクが大きくなります。

結論: OpenClaw Gateway の安全な公開パターン（Tailscale / Reverse Proxy） は、最小構成で始めてログを見ながら段階的に広げるのが最短です。

## Background

OpenClaw Gatewayを公開する目的は、多くの場合「自分の端末以外から安全に操作したい」「チーム内で限定的に共有したい」「外部サービスからWebhookで呼びたい」のいずれかです。目的によって、選ぶべき公開パターンは変わります。

個人利用や小規模チームでは、まずTailscaleでプライベートネットワーク内に閉じるのが安全です。インターネットに公開する必要がある場合だけ、Reverse Proxyを置き、TLS、認証、レート制限、ログを必ず設定します。

ここでは、OpenClaw Gatewayがローカルの `127.0.0.1:8080` で動いている前提で進めます。実際のポートや起動方法は環境に合わせて読み替えてください。

## Step-by-step

1. 公開範囲を決める

まず、誰がどこからGatewayにアクセスするのかを決めます。自分やチームだけが使うならTailscale、外部サービスからのWebhookを受けるならReverse Proxyを検討します。

最初はインターネットに直接公開しない構成にします。OpenClaw Gateway本体は `127.0.0.1` にだけ待ち受けさせ、外部公開はTailscaleまたはReverse Proxyに任せます。

```bash
# Gatewayがローカルだけで待ち受けているか確認する
ss -ltnp | grep ':8080'

# 期待例:
# LISTEN 0 4096 127.0.0.1:8080 0.0.0.0:*
```

2. Tailscaleでプライベートに公開する

Tailscaleを使う場合、Gatewayをインターネットに出さず、Tailnet内の端末だけからアクセスできます。まずはこの構成で運用し、ログと権限を確認します。

```bash
# Gatewayを動かすホストでTailscaleに参加する
sudo tailscale up

# Tailscale上のIPv4アドレスを確認する
tailscale ip -4
```

クライアントから直接アクセスさせたい場合は、GatewayをTailscaleのIPアドレスにだけバインドします。`0.0.0.0` にバインドするとLAN側にも開く可能性があるため、公開範囲を明示します。

```bash
# Tailscale IPを変数に入れる
TS_IP="$(tailscale ip -4 | head -n 1)"

# 例: GatewayをTailscale IPだけで待ち受ける
# 実際の起動コマンドや環境変数名は利用中のOpenClaw設定に合わせる
OPENCLAW_GATEWAY_HOST="$TS_IP" \
OPENCLAW_GATEWAY_PORT=8080 \
openclaw gateway serve
```

アクセス制御はTailscale ACLで管理します。Gateway用のホストにタグを付け、必要なユーザーやグループだけが `8080` に接続できるようにします。

```json
{
  "acls": [
    {
      "action": "accept",
      "src": ["group:developers"],
      "dst": ["tag:openclaw-gateway:8080"]
    }
  ]
}
```

3. Reverse Proxyでインターネット公開する

外部サービスからWebhookを受ける場合など、インターネット公開が必要なときはReverse Proxyを前段に置きます。OpenClaw Gateway本体は引き続き `127.0.0.1:8080` に閉じ、CaddyやNginxでTLSと認証を担当します。

Caddyを使うと、TLS証明書の取得と更新を自動化しやすくなります。以下はBasic認証を付けてGatewayへ転送する最小例です。

```bash
# Basic認証用のハッシュを作成する
caddy hash-password --plaintext 'change-this-password'
```

```caddyfile
# /etc/caddy/Caddyfile
gateway.example.com {
    encode zstd gzip

    basicauth {
        openclaw $2a$14$REPLACE_WITH_CADDY_HASHED_PASSWORD
    }

    reverse_proxy 127.0.0.1:8080

    log {
        output file /var/log/caddy/openclaw-gateway.log
        format json
    }
}
```

設定を反映する前に、必ず構文チェックを行います。問題がなければCaddyを再読み込みします。

```bash
sudo caddy validate --config /etc/caddy/Caddyfile
sudo systemctl reload caddy
```

4. 動作確認とログ確認を行う

公開後は、疎通確認だけで終わらせず、成功時と失敗時のログを確認します。認証なしでアクセスできないこと、意図したホスト名だけで応答すること、Gateway本体が直接外部に出ていないことを確認します。

```bash
# 認証なしでは拒否されることを確認する
curl -i https://gateway.example.com/

# 認証ありで応答することを確認する
curl -i -u openclaw:'change-this-password' https://gateway.example.com/

# Gateway本体が外部公開されていないことを確認する
ss -ltnp | grep ':8080'
```

ログには、少なくともアクセス元、ステータスコード、時刻、リクエストパスが残るようにします。異常な連続アクセスや認証失敗が見える状態にしてから、利用範囲を広げます。

## Common pitfalls

- Gateway本体を `0.0.0.0` で待ち受けたままにする  
  Reverse ProxyやTailscaleで保護しているつもりでも、LANやクラウドのセキュリティグループ経由で直接到達できる場合があります。まず `ss -ltnp` で待ち受けアドレスを確認し、必要がなければ `127.0.0.1` またはTailscale IPに限定します。

- Reverse Proxyに認証を付け忘れる  
  TLSだけでは「暗号化されている」だけで、誰でもアクセスできる状態です。Basic認証、OIDC、VPN、IP制限のいずれかを必ず追加し、認証なしの `curl` が失敗することを確認します。

- Tailscale ACLを広くしすぎる  
  `*:*` や全ユーザー許可で始めると、後から権限を絞るのが難しくなります。Gateway用のタグを作り、必要なグループから必要なポートだけに接続できるACLにします。

- ログを標準出力だけに流して確認していない  
  障害時や不審なアクセスの調査ができなくなります。Reverse ProxyのアクセスログとOpenClaw Gateway側のアプリケーションログを残し、時刻、ステータスコード、リクエストIDを追えるようにします。

- Webhook用途で固定の共有シークレットを検証していない  
  外部サービスから呼ばれるエンドポイントでは、送信元の認証が必要です。署名ヘッダーや共有シークレットを検証し、検証に失敗したリクエストは処理前に拒否します。

## Summary

OpenClaw Gatewayを安全に公開する基本は、Gateway本体を直接インターネットに出さないことです。個人利用やチーム内利用ではTailscaleを優先し、外部公開が必要な場合だけReverse ProxyでTLS、認証、ログを前段に置きます。

OpenClaw Gateway の安全な公開パターン（Tailscale / Reverse Proxy） は、最小構成で開始→ログ検証→段階拡張の順で進めると、失敗を抑えながら運用を安定させられます。