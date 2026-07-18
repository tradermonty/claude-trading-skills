---
layout: default
title: プレイブック
parent: 日本語
nav_order: 7
has_children: true
lang_peer: /en/playbooks/
permalink: /ja/playbooks/
---

# プレイブック
{: .no_toc }

個別スキルの説明ではなく、複数スキルをまたぐパイプライン全体の使い方ガイドです。各プレイブックはパイプラインを最初から最後まで解説します。いつ回すか、ステップの順序、ゲートがどう判断するか、ポジションをどう計算するか、そしてトレードを `trader-memory-core` にどう登録するか。個々のスキルを単体で走らせる前に、まず該当するプレイブックを読んでください。

---

## プレイブック一覧

| プレイブック | 時間軸 | 内容 |
|---|---|---|
| [Cross-Asset Quant Strategy Framework]({{ '/ja/playbooks/quant-strategy-framework/' | relative_url }}) | 全時間軸を横断 | すべてのアセットクラス別プレイブックとスキルを結びつける Pre / During / Post フレームワーク |
| [Stockbee Momentum Burst]({{ '/ja/playbooks/stockbee-momentum-burst/' | relative_url }}) | 2〜5セッション | `stockbee-momentum-burst-screener` によるブレイクアウト・レンジ拡大の短期スイングエントリー |
| [PEAD（決算後ドリフト）]({{ '/ja/playbooks/pead/' | relative_url }}) | 2〜6週間 | `pead-screener` の赤週足プルバックパターンによる決算ドリフトエントリー |
| [Shapiro COT 逆張り]({{ '/ja/playbooks/shapiro-contrarian/' | relative_url }}) | 週次 | 2つの独立確認を経てCFTC先物の混雑ポジショニングをフェードする |

各プレイブックは**判断支援のパイプラインであり、自動発注システムではありません**。発注はすべて手動で行い、各スクリーナーの出力は無条件に従うシグナルではなく候補リストです。この4つのプレイブックを支える8つのスキル（`stockbee-momentum-burst-screener`、`pead-screener`、`earnings-trade-analyzer`、`technical-analyst`、`position-sizer`、`trader-memory-core`、`pre-trade-discipline-gate`、`cot-contrarian-detector` および Shapiro パイプラインの周辺スキル）のいずれも、発注・注文キャンセル・ブローカーAPI呼び出し・リアルタイム監視は行いません。

## 2つの短期プレイブックを混同しない

Stockbee Momentum Burst と PEAD はどちらも流動性の高い米国株のスイング候補を出しますが、保有期間もカタリストも異なる別々のコホートです。

- **Momentum Burst** は純粋な価格・出来高のブレイクアウト戦略です。決算は前提条件でなく、保有は2〜5セッション、trigger-day の安値割れやフォロースルー不在で撤退します。
- **PEAD** は実際の決算ギャップアップと週足の赤キャンドルによるプルバックをエントリー前提とし、保有は2〜6週間、週足終値でのストップ抵触または thesis の無効化で撤退します。

決算をたまたま発表したというだけで Momentum Burst のポジションを PEAD の時間軸まで延長してはいけません。ピボットさせる場合は、別の `setup_type` を持つ別 thesis として登録してください。境界の詳細は各プレイブックの「混同しないこと」セクションを参照してください。

## 関連ページ

- 個別スキルのリファレンスは [スキルガイド]({{ '/ja/skills/' | relative_url }})
- 自動生成されたマニフェスト一覧は [ワークフロー]({{ '/ja/workflows/' | relative_url }})
