# Kanchi Dividend Skills Runbook

このドキュメントは、以下3スキルの実運用順序を固定するための手順書です。

- `kanchi-dividend-sop`
- `kanchi-dividend-review-monitor`
- `kanchi-dividend-us-tax-accounting`

## 結論

開始点は `kanchi-dividend-sop` で正しいです。
基本フローは `SOP -> 監視 -> 税務/口座配置` です。

## 標準フロー

1. 銘柄選定と買い条件を作る
使用スキル: `kanchi-dividend-sop`
実行タイミング: 新規検討時、月次見直し時
成果物:
- Screening結果 (`PASS/HOLD-FOR-REVIEW/FAIL`)
- 1ページ銘柄メモ
- 指値分割プラン

2. 保有銘柄の異常検知を回す
使用スキル: `kanchi-dividend-review-monitor`
実行タイミング:
- 日次: T1, T4
- 週次: T3
- 四半期: T2, T5
成果物:
- `OK/WARN/REVIEW` キュー
- REVIEWチケット

3. 税務区分と口座配置を最適化する
使用スキル: `kanchi-dividend-us-tax-accounting`
実行タイミング: 新規採用時、大きな入替時、年次点検時
成果物:
- 配当区分サマリー
- 口座配置提案
- 税務前提の未確定事項リスト

## 運用リズム

- 日次: `kanchi-dividend-review-monitor` のT1/T4のみ確認
- 週次: REVIEW/WARN銘柄の手動確認
- 月次: `kanchi-dividend-sop` で候補更新と買い条件更新
- 四半期: T2/T5再評価 + SOPメモ更新
- 年次: `kanchi-dividend-us-tax-accounting` で税務メモ確定

## スキル間の受け渡し

1. `kanchi-dividend-sop` から `kanchi-dividend-review-monitor` へ
引き継ぐもの:
- 採用/保有ティッカー一覧
- 配当安全性の基準値
- 失効条件

2. `kanchi-dividend-review-monitor` から `kanchi-dividend-sop` へ
引き継ぐもの:
- `REVIEW` 判定理由
- 前提崩壊の疑い
- 再評価対象の優先順位

3. `kanchi-dividend-us-tax-accounting` から `kanchi-dividend-sop` へ
引き継ぐもの:
- 口座制約
- 税務上の優先配置
- 新規買い付け時の配置ルール

## 最小実行例

`kanchi-dividend-review-monitor` のルールエンジンは以下で実行できます。

```bash
python3 skills/kanchi-dividend-review-monitor/scripts/build_review_queue.py \
  --input /path/to/monitor_input.json \
  --output /path/to/review_queue.json \
  --markdown /path/to/review_queue.md
```

入力形式は `skills/kanchi-dividend-review-monitor/references/input-schema.md` を参照してください。
