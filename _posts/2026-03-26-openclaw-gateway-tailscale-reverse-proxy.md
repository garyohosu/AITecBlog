---
layout: post
title: "OpenClaw Gateway を安全に公開する方法: Tailscale と Reverse Proxy の実践パターン"
date: 2026-03-26 09:00:00 +0900
tags:
  - openclaw
  - gateway
  - tailscale
  - reverse-proxy
  - security
description: "OpenClaw Gateway を外部公開するなら、まずは Tailscale で閉域公開し、必要になった段階で Reverse Proxy を追加するのが安全です。公開範囲を最小化し、ログを見ながら段階的に広げる実践パターンを整理します。"
---

OpenClaw Gateway を外部から使いたくなったとき、最初に決めるべきなのは「誰に、どこまで、どの経路で見せるか」です。便利さを優先していきなりインターネットへ直接公開すると、認証や TLS、アクセス制御の穴がそのまま運用リスクになります。

結論: OpenClaw Gateway の安全な公開パターンは、まず Tailscale で閉じた範囲に公開し、必要な場合だけ Reverse Proxy を前段に置いて段階的に広げるのが最短です。

## Background

Gateway は社内ツールや個人運用でも便利ですが、HTTP ポートをそのまま公開すると、想定外のアクセスや設定漏れが起きやすくなります。特に検証環境では、「とりあえず開ける」がそのまま本番運用に持ち込まれやすい点が危険です。

安全に始めるには、最初から大きく公開しないことが重要です。アクセス元を絞り、ログを確認しながら必要な機能だけを外へ出す構成にすると、障害時の切り分けも簡単になります。

## Step-by-step

1. まずは Gateway をローカルバインドに固定する

最初の原則は、Gateway 自体は外部 NIC に直接 bind しないことです。`127.0.0.1` のみで待ち受けさせ、公開は別レイヤーで制御します。

```bash
# 例: Gateway をローカルホストだけで待ち受ける
openclaw gateway start --host 127.0.0.1 --port 3000
```

この形にしておくと、誤って firewall を緩めても Gateway が直接露出しにくくなります。公開経路を Tailscale または Reverse Proxy に限定できるため、設定の責任範囲も明確です。

2. 最小構成は Tailscale で閉域公開する

最初の公開先が自分やチーム内だけなら、Tailscale 経由が最も扱いやすい構成です。ノード同士を tailnet 内だけで接続し、公開面をインターネットへ広げません。

```bash
# Tailscale を有効化
sudo tailscale up

# tailnet 内だけで Gateway を公開
# https://<tailnet-hostname> で 127.0.0.1:3000 を配信する
sudo tailscale serve https / http://127.0.0.1:3000
```

この構成では、Gateway はローカル待ち受けのままです。外部公開の責務を Tailscale に寄せることで、公開対象を tailnet 参加者に限定できます。

3. 共有範囲を広げる必要が出たら Reverse Proxy を前段に置く

社外ユーザーや既存ドメイン配下で見せたい場合は、Gateway の前に Reverse Proxy を置きます。ここでも Gateway 自体は `127.0.0.1:3000` に閉じたままにし、TLS とアクセス制御を Proxy 側で受けます。

Caddy の最小例です。

```caddyfile
# /etc/caddy/Caddyfile
gateway.example.com {
	encode gzip

	# 必要なら Basic Auth を追加
	basicauth {
		admin $2a$14$exampleReplaceWithRealHashxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxxx
	}

	reverse_proxy 127.0.0.1:3000

	# ログは必ず残す
	log {
		output file /var/log/caddy/openclaw-gateway.log
		format json
	}
}
```

Caddy は TLS 自動化がしやすく、最小構成でも始めやすいのが利点です。公開を広げる前に、まずは Basic Auth や IP 制限のどちらかを必ず入れてください。

4. ログを見ながら段階的に制御を追加する

公開後は「つながるか」だけでなく、「誰が、いつ、どこへアクセスしたか」を追える状態にします。Gateway 側ログと Proxy 側ログの両方を見られるようにしておくと、認証失敗や 5xx の原因を切り分けやすくなります。

```bash
# Caddy のアクセスログを確認
sudo tail -f /var/log/caddy/openclaw-gateway.log
```

最初は自分だけ、次にチーム、最後に必要な外部利用者という順番で広げるのが実運用では安定します。公開先を増やすたびに、認証方式とログの粒度を見直してください。

## Common pitfalls

- Gateway を `0.0.0.0` で起動してしまう  
  Reverse Proxy を使う予定でも、Gateway 自体が全 NIC で待ち受けていると想定外に直接到達されます。起動オプションやサービス定義を確認し、`127.0.0.1` 固定にしてください。

- Tailscale 公開なのに OS の firewall で不要ポートを開けたままにする  
  Tailscale を使っていても、ホスト側で `3000/tcp` を外向きに許可していれば直接到達される余地が残ります。`ss -lntp` や firewall 設定を確認し、公開経路を 1 つに絞ってください。

- Reverse Proxy を置いたが認証を Proxy 側で入れていない  
  TLS だけでは「暗号化」されるだけで、「誰でも見られる」状態は解消しません。最低でも Basic Auth、可能なら SSO や IP 制限を追加し、無認証公開を避けてください。

- ログを見ないまま公開範囲だけ広げる  
  403、401、5xx の傾向を把握していないと、障害時に原因が Gateway 側か Proxy 側か判断できません。アクセスログとアプリケーションログの保存先を最初に決めておくべきです。

- ヘルスチェックや依存サービスの停止を見落とす  
  Gateway の背後にローカル LLM や別サービスがある場合、公開経路が正常でも実処理は失敗します。公開前に依存先への疎通確認を定期チェックへ組み込むと、表面上の「起動しているだけ」状態を避けられます。

## Summary

OpenClaw Gateway を安全に公開するなら、最初の選択肢は Tailscale です。閉域で運用を固め、アクセスログと障害時の切り分け手順を確認してから、必要に応じて Reverse Proxy を前段に追加するのが現実的です。

重要なのは、Gateway 本体を直接露出させないことです。`127.0.0.1` 待ち受けを維持しながら、公開経路と認証を分離して管理すると、最小構成のままでも安全性と運用性を両立できます。