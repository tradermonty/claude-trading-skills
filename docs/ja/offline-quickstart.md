---
layout: default
title: オフライン・クイックスタート
parent: 日本語
nav_order: 2
lang_peer: /en/offline-quickstart/
permalink: /ja/offline-quickstart/
---

# 初めてのオフラインレポート

まず[出力プレビュー]({{ '/ja/getting-started/' | relative_url }}#出力プレビュー)を見て、
次にこの手順で**架空データ**の市場レジームレポートを作ります。リポジトリ内のコマンドなので、
Claudeアカウント、証券口座、市場データAPIキーは不要です。同梱の架空の構成要素データと
既存のスコア計算を使い、実データは取得しません。人の判断を待つ地点で止まり、提案を読み、
練習用の判断を `reports/` 配下の新しいディレクトリに記録します。

目安は**環境準備後15分**です。読む時間と練習の判断を含む目標であり、保証ではありません。
自動テストはコマンド経路を900秒以内という上限で計測します。人の読解時間、ダウンロード、
インストール、新しいOSでの準備時間を測定したものではありません。

## 1. リポジトリの環境を準備する

このリポジトリをcloneまたはダウンロードし、ルートに移動します。
`config/python-support.json` に合うPython（ルート環境は `>=3.11.5,<3.14`）と `uv` を用意し、実行します。

```bash
uv sync --locked --extra dev
```

初回の依存ライブラリ導入にはネットワーク接続または取得済みのローカルキャッシュが必要です。
**導入後の以下のコマンド経路がオフラインです。**
環境を有効化して、このリポジトリのPythonを使います。

```bash
# macOS / Linux
source .venv/bin/activate
```

Windows PowerShellでは `.venv\Scripts\Activate.ps1` を使います。有効化が制限されている場合、
以下の `python` を `.venv\Scripts\python.exe` に置き換えます。
macOS/Linuxでは `.venv/bin/python` を直接指定できます。
すべてリポジトリのルートで実行してください。個人のエージェント設定へのスキル導入は行いません。

<!-- quickstart: doctor -->
```bash
python scripts/doctor.py
```

`Offline environment doctor` と項目別の結果・修正ヒントが出ます。
FMP・FINVIZ・Alpaca認証情報の不足は**想定どおりの警告**で、終了コードは0です。
デモのために口座やキーを用意する必要はありません。doctorは接続性、キーの有効性、
すべてのskillsetの実行可否を検証しません。Python・パッケージの警告は上の環境準備で解消してください。

## 2. 生成して判断前で止める

**新しい**出力ディレクトリを選びます。既存の場所は空でも拒否されます。
この名前を使ったことがある場合は別名にし、以後の全コマンドでも同じ名前を使います。
過去の実行結果を削除してやり直す必要はありません。

<!-- quickstart: start -->
```bash
python scripts/run_market_regime_daily.py --run-dir reports/quickstart-demo
```

端末では架空データに基づく提案が表示され、方針の入力を求められます。
今回は先に結果を確認するため、**何も入力せずEnterで一時停止**してください。
入力リダイレクトやCIでは自動で停止します。`AWAITING_DECISION` と終了コード **3** は、
完了や失敗ではなく判断待ちです。コマンドは一つずつ実行してください。
非ゼロ終了で止まる設定のシェルでは、この意図的な一時停止で処理が止まります。

<!-- quickstart: paused-status -->
```bash
python scripts/run_market_regime_daily.py --run-dir reports/quickstart-demo --status
```

停止中はこの確認も終了コード3です。エディターでJSONを開きます。

| `reports/quickstart-demo/` 内の出力 | 確認する内容 |
| --- | --- |
| `01_market_breadth_report.json` | 騰落状況の結果と架空入力の来歴 |
| `02_uptrend_report.json` | 上昇トレンド参加状況 |
| `04_exposure_proposal.json` | 人が確認するエクスポージャー方針の提案 |
| `manifest.json` | 実行ID、各ステップの状態、入力・生成物のハッシュ |

評価時刻は **2026-01-15T13:08:00+00:00** に固定されています。現在の市場ではありません。
基本経路では任意の天井リスク分析は `SKIPPED` です。リスク評価が成功した意味ではなく、
任意入力がない点は提案に反映されます。判断する前には `journal.json` は作成されません。

## 3. 練習の判断を明示して記録する

先に提案を読んでください。今回の**架空の練習**では、制限する方針を体験するため `restrict`
を自分で選びます。実取引の承認や現在の投資配分の推奨ではありません。
最初の入力時に停止せず方針を選んだ場合は、すでに完了しています。
その場合はresumeを省き、statusを確認します。完了済みの実行は2回目の判断を拒否します。

<!-- quickstart: resume -->
```bash
python scripts/run_market_regime_daily.py --run-dir reports/quickstart-demo --resume --decision restrict
```

<!-- quickstart: status -->
```bash
python scripts/run_market_regime_daily.py --run-dir reports/quickstart-demo --status
```

`COMPLETED`、終了コード0となり、`journal.json` に練習の選択と
`destination: trader-memory-core`、`delivery: handoff_only` が記録されます。
これは**ローカルの引継ぎ用ファイル**です。実ジャーナルへの反映や `state/` の変更ではありません。
statusは読取り専用で、既存レポートは同じ実行に紐づいたままです。

`BLOCKED` が出たらディレクトリを保持し、[ランナーの詳細手順](https://github.com/tradermonty/claude-trading-skills/blob/main/docs/dev/guided-market-regime-daily.ja.md)
を確認します。manifestを書き換えて判断ゲートを回避しないでください。
架空の結果を売買シグナルとして扱ったり、公開の問い合わせに個人の口座情報を添付したりしないでください。

## 4. 3つの質問で次の経路を選ぶ

1. **何をしたいですか？** 朝のリスク確認、保有の見直し、取引の振り返りなど、目的を決めます。
2. **安全に使える入力は何ですか？** 最初は架空データを使います。公開市場データと個人の
   口座ファイルを区別し、キーや保有明細を検索文に貼り付けないでください。
   有料API不要の経路でも、後続のすべてのスキルがオフラインとは限りません。
3. **使える時間は？** 15・30・60・90分から選びます。時間は経路選択のヒントで、完了時間の保証ではありません。

以下は15分・初心者向けの朝の確認を選ぶ検証済みの例です。
経路を推薦するだけで、ワークフローの実行やモデルへの問い合わせは行いません。

<!-- quickstart: navigator -->
```bash
python skills/trading-skills-navigator/scripts/recommend.py --query "I have 15 minutes before the market open to check market breadth, uptrend participation and exposure posture" --no-api --time-budget 15m --experience beginner --format json
```

`goal_match.workflow.id` は `market-regime-daily`、`no_api_path` は `true` になります。
機微な情報を含めずに自分の目的へ変えると、別の経路や対応できない範囲が示される場合があります。
選ばれたスキルの使い方は[Navigatorガイド]({{ '/ja/skills/trading-skills-navigator/' | relative_url }})
を確認してください。このデモはリポジトリから直接実行します。skillsetの一括インストーラーや
skillsetごとのlive実行準備診断は #301 の今後の作業です。

## 検証内容

`scripts/tests/test_offline_quickstart.py` は両言語の印付きコマンドを抽出し、
ロックファイルに基づくテスト環境で実行します。キーは渡さず、ユーザーホームも一時領域に分離します。
一時停止、明示した判断、実レポート、固定評価時刻、引継ぎ限定、元の架空入力が不変であること、
最後のstatusが読取り専用であることを確認します。Pythonのsocket・DNS呼出しを記録して拒否し、
ガードの起動と、例外が捕捉されても試行を検出できることをテストします。OSの通信隔離ではありません。
既存CIのルートスクリプト検証でもこのテストが実行されます。
手順の実行可能性を検証するもので、人の所要時間や実市場での正しさを保証するものではありません。
