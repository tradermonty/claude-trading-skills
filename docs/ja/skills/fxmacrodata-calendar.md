---
layout: default
title: "FXMacroData Calendar"
grand_parent: 日本語
parent: スキルガイド
nav_order: 34
lang_peer: /en/skills/fxmacrodata-calendar/
permalink: /ja/skills/fxmacrodata-calendar/
generated: false
---

# FXMacroData Calendar
{: .no_toc }

FXMacroDataの公式APIからマクロ経済指標の発表予定を取得し、取引計画、マクロ環境の確認、イベントリスクの判定に利用します。CPI、雇用統計、GDP、PCE、小売売上高、PMI、中央銀行会合などの前に使用してください。
{: .fs-6 .fw-300 }

<span class="badge badge-free">USD公開データはAPIキー不要</span>

[スキルパッケージをダウンロード (.skill)](https://github.com/tradermonty/claude-trading-skills/raw/main/skill-packages/fxmacrodata-calendar.skill){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
[GitHubでソースを見る](https://github.com/tradermonty/claude-trading-skills/tree/main/skills/fxmacrodata-calendar){: .btn .fs-5 .mb-4 .mb-md-0 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 1. 概要

FXMacroDataのリリースカレンダーから、指定通貨に関連する経済指標イベントを取得するスキルです。イベントの時刻と重要度を確認し、重要指標の直前に新規エントリーを避ける、ポジションサイズやレバレッジを抑える、発表後に再評価するといった判断に使用します。

スクリプトはレスポンスを厳格に検証します。要求通貨との一致に加え、`data_quality` が公式・非プロキシ・非フォールバック・非stale・発表日時完備・point-in-time safeであることを要求します。各イベントには整数の `announcement_datetime` と空でない `release` が必要です。正当な `data: []` は「該当イベントなし」として扱いますが、空配列でも品質情報が欠落または不安全ならエラーとして非zero終了します。レスポンス構造の破損、深すぎるJSON、非有限数、契約外の `market_tier` も拒否し、取得失敗や不正データを「イベントなし」と誤認しないフェイルクローズド設計です。

---

## 2. 前提条件

- Python 3.9以上
- FXMacroData REST API（正規URL: `https://api.fxmacrodata.com/v1`）
- 公開されているUSDカレンダーはAPIキーなしで取得可能
- 認証が必要なエンドポイントを使う場合は、環境変数 `FXMACRODATA_API_KEY` を設定

APIキーはクエリパラメータとして送信されますが、エラー出力には表示されません。

---

## 3. クイックスタート

重要度tier 1のUSDイベントを取得します。

```bash
python3 skills/fxmacrodata-calendar/scripts/fetch_calendar.py \
  --currency usd \
  --min-tier 1
```

`--min-tier` には `1`、`2`、`3` のいずれかを指定します。数値が小さいほど重要度が高く、たとえば `--min-tier 2` はtier 1とtier 2を返します。取得件数は `--limit` で指定でき、1〜100件に制限されます。

ライブのカレンダーレスポンスには現在 `market_tier` が含まれていますが、現行OpenAPIの `CalendarReleaseRow` にはこの項目が定義されていません。このスキルではライブ拡張フィールドとして扱い、フィルタリングのため整数の1〜3を必須とします。

---

## 4. ワークフロー

1. 分析対象の通貨を3文字コードで指定してスクリプトを実行します。
2. 出力された `events[]` を確認し、発表日時、指標名、`market_tier`、予想値・前回値を取引計画へ反映します。
3. 重要イベントの前後では、必要に応じて次を実施します。
   - 新規エントリーを見送る
   - レバレッジまたはポジションサイズを下げる
   - ストップ位置と許容損失を再確認する
   - 実績値の公表後に価格反応を再評価する
4. 取引判断を変更した場合は、判断に影響したイベント名と発表時刻を明記します。

CLIが非zeroで終了した場合は、イベントが存在しないとは判断しないでください。APIまたはデータ契約の問題を解消して再実行するまで、イベントリスクは未確認として扱います。`currency`、`data_quality`、`announcement_datetime`、`release` のエラーも同じ扱いです。

---

## 5. リソース

**スクリプト:**

- `skills/fxmacrodata-calendar/scripts/fetch_calendar.py`

---

[English版ガイドを見る]({{ '/en/skills/fxmacrodata-calendar/' | relative_url }}){: .btn .btn-primary .fs-5 .mb-4 .mb-md-0 .mr-2 }
