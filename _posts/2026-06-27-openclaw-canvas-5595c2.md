---
layout: post
title: "OpenClaw Canvas入門：HTMLを表示して画像として出力する方法"
date: 2026-06-27 09:00:00 +0900
tags: [openclaw, canvas, visualization, html]
description: "OpenClawのCanvas機能を使い、HTMLベースの画面をNodeに表示してスナップショットを取得する手順を解説します。接続確認からトラブル対処まで、最小構成で実践できます。"
---

OpenClawのCanvasは、HTML/CSS/JavaScriptで作成したダッシュボードや操作画面を、接続済みNodeのWebViewに表示する機能です。表示内容は画像として取得できるため、処理結果の可視化やレポート生成にも利用できます。

結論: OpenClawのCanvas機能は、単純なHTMLを表示する最小構成から始め、`eval`と`snapshot`で動作を検証しながら拡張するのが最短です。

## Background

テキストだけでは、数値の傾向や処理状況を直感的に把握しにくい場合があります。Canvasを使えば、エージェントが生成した結果をカード、グラフ、ステータス画面などとして提示できます。

Canvasの操作には、Gatewayへ接続されたCanvas対応Nodeが必要です。最初に次のコマンドを実行し、対象Nodeの名前またはIDを確認してください。

```bash
# 接続済みNodeと利用可能な機能を確認する
openclaw nodes list
```

## Step-by-step

1. 表示するHTMLを作成する

Canvasホストのルートディレクトリに、自己完結したHTMLファイルを配置します。次の例では、依存ライブラリを使わない簡単なステータス画面を作成します。

```bash
mkdir -p ~/.openclaw/workspace/canvas

cat > ~/.openclaw/workspace/canvas/status.html <<'HTML'
<!doctype html>
<html lang="ja">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1">
  <title>OpenClaw Status</title>
  <style>
    body {
      margin: 0;
      padding: 40px;
      color: #e5e7eb;
      background: #111827;
      font-family: system-ui, sans-serif;
    }
    .card {
      max-width: 520px;
      padding: 24px;
      border: 1px solid #374151;
      border-radius: 16px;
      background: #1f2937;
    }
    .value {
      margin: 8px 0;
      color: #34d399;
      font-size: 48px;
      font-weight: 700;
    }
  </style>
</head>
<body>
  <main class="card">
    <h1>処理ステータス</h1>
    <p class="value" id="count">42</p>
    <p id="message">すべてのジョブが完了しました。</p>
  </main>
</body>
</html>
HTML
```

2. Canvasに表示する

`NODE`には、`openclaw nodes list`で確認したNode名またはIDを指定します。Canvasホスト上のHTMLを対象Nodeに表示します。

```bash
NODE="My Mac"

openclaw nodes canvas present \
  --node "$NODE" \
  --target "/status.html"
```

外部Webページを表示する場合は、`--target`にHTTPS URLを指定できます。

```bash
openclaw nodes canvas present \
  --node "$NODE" \
  --target "https://example.com"
```

3. JavaScriptで表示内容を検証する

`eval`を使うと、Canvas内でJavaScriptを実行できます。まず、表示したページのタイトルが取得できることを確認します。

```bash
openclaw nodes canvas eval \
  --node "$NODE" \
  --js "document.title"
```

表示中の値を更新することも可能です。

```bash
openclaw nodes canvas eval \
  --node "$NODE" \
  --js "document.querySelector('#count').textContent = '57'; 'updated'"
```

4. スナップショットを取得する

表示結果をPNG画像として取得します。コマンドが出力する保存先を確認し、レイアウトや文字切れがないか検証してください。

```bash
openclaw nodes canvas snapshot \
  --node "$NODE" \
  --format png
```

ファイルサイズを抑えたい場合は、幅と品質を指定してJPEGで取得できます。

```bash
openclaw nodes canvas snapshot \
  --node "$NODE" \
  --format jpg \
  --max-width 1200 \
  --quality 0.9
```

確認後、不要になったCanvasを閉じます。

```bash
openclaw nodes canvas hide --node "$NODE"
```

## Common pitfalls

- `node required`と表示される場合は、すべてのCanvasコマンドに`--node`を指定します。Node名の入力ミスを避けるため、事前に`openclaw nodes list`の出力をコピーしてください。

- `node not connected`と表示される場合は、対象アプリが起動し、Gatewayへ接続されているか確認します。モバイルNodeではアプリを前面に出してから再実行してください。

- `CANVAS_DISABLED`と表示される場合は、Node側の設定でCanvasを許可します。macOSアプリでは「Settings」から「Allow Canvas」が有効になっているか確認してください。

- 白い画面になる場合は、まず外部URLを`present`してCanvas自体が動作するか切り分けます。外部URLは表示できるのにローカルHTMLだけ失敗する場合は、ファイルの配置先とCanvasホストのルート設定を確認してください。

- 更新内容が反映されない場合は、HTMLがCanvasホストの管理対象ディレクトリにあるか確認します。ライブリロードが無効な環境では、`navigate`または`present`を再実行してください。

- スナップショットが失敗する場合は、先に`present`でCanvasを表示してから取得します。Nodeがバックグラウンド状態の場合は、前面へ戻して再試行してください。

## Summary

OpenClawのCanvasを使うと、HTML/CSS/JavaScriptによる画面表示、JavaScriptでの動的更新、画像としての保存を一連の操作として実行できます。

まずは単純なHTMLを1枚表示し、`eval`で内容を確認してから`snapshot`を取得してください。最小構成で表示経路を確立した後に、グラフやインタラクティブなUIへ段階的に拡張すると、問題を切り分けやすくなります。