---
layout: default
title: Stockbee モメンタムバースト・プレイブック
grand_parent: 日本語
parent: プレイブック
nav_order: 12
lang_peer: /en/playbooks/stockbee-momentum-burst/
permalink: /ja/playbooks/stockbee-momentum-burst/
---

# Stockbee Momentum Burst — 短期スイングプレイブック

`stockbee-momentum-burst-screener` 単体の説明ではなく、Momentum Burst ワークフロー全体の使い方ガイドです。候補をスクリーニングしてからチャート確認、サイジング、`trader-memory-core` への登録、そして手仕舞いまでを一連の流れとして解説します。スクリーナーを単体で走らせる前に、まずこのページを読んでください。

> **手動運用であり自動化ではありません。** このパイプラインのどのスキルも発注・注文キャンセル・監視を行わず、リアルタイム監視も存在しません。発注はすべて手動でブローカーに出し、スクリーナーの出力は無条件に従うシグナルではなく、レビューすべき候補リストです。

---

## 一段落で言うと

Stockbee 流の Momentum Burst は、レンジが収縮したベースからの短く鋭い価格・出来高のバーストを狙います。4%ブレイクアウト、ドルブレイクアウト、レンジ拡大のいずれかが、常に流動性フロアを超えた出来高で発生した状態です。4%ブレイクアウトとレンジ拡大には前日を上回る出来高も必要ですが、ドルブレイクアウトは流動性フロアさえ満たせばよく、出来高の拡大は要求されません。これは**2〜5セッションのスイング**であり、長期のトレンドフォローでも、決算ドリフトを狙う PEAD でもありません。スクリーナーは候補生成とセットアップ品質の判定ツールであり、シグナルサービスではありません。4%の値動きだけでは決して十分ではなく、生き残った候補も必ずチャート確認を経て、実際にブローカーで約定したものだけがトレードメモリで `ACTIVE` になります。

---

## いつ回すか

- 地合いがスイングの新規リスクを許容していることを確認してから回します。まず `market-regime-daily`（最低でも `drawdown-circuit-breaker`）を実行してください。その確認を省く場合は、スクリーニングに `--market-gate restrictive` を渡すか、出力を明示的に manual-review-only として扱ってください。
- 入力モードは3種類です。ライブのユニバーススキャンを行う `--fmp-universe`（Mode A）、銘柄を明示指定する `--symbols`（Mode B）、完全オフラインで動く `--prices-json`（Mode C）のいずれかを使います。
- デフォルトのエントリー参照値は直近の終値です。このスクリーナーは主に引け後・引け近辺で使うツールだからです。日中に走らせる場合、エントリー参照値はあくまで目安として扱い、実際の発注タイミング付近でブレイクアウトがまだ有効かを手動で確認してください。

## 回してはいけないとき

- **単体の買いリストとして使わない。** 4%のトリガーだけでは足りません。セットアップ品質（ベースの長さ・幅・クローズの位置）とストップまでの許容できるリスク距離が必要です。
- **決算ギャップ狙いには使わない。** 決算当日のギャップアップは PEAD の領域であり、このプレイブックの対象外です。詳しくは後述の[PEADと混同しないこと](#dont-confuse-this-with-pead)を参照してください。
- **自動発注には決して繋がない。** このスクリーナーにブローカー連携は存在せず、このパイプライン内で今後も追加されることはありません。

---

## パイプライン全体像

```
1  market-regime-daily / drawdown-circuit-breaker →  market_gate                    （新規スイングリスクの許可・制限）
2  stockbee-momentum-burst-screener                →  stockbee_momentum_burst_report （候補、5状態に分類）
3  technical-analyst                                →  チャート確認                    （画像ベース、CLIなし）
4  position-sizer                                    →  ポジションサイズ                （株数、純計算）
5  trader-memory-core（ingest --source manual）        →  IDEA thesis                    （専用アダプタなし）
6  trader-memory-core（link_report、uv run経由）        →  thesisへエビデンスをlink         （スクリーナー・チャートレビューのレポート）
7  trader-memory-core（store transition ENTRY_READY）  →  発注準備完了の thesis
8  pre-trade-discipline-gate                          →  GO / REVIEW_REQUIRED / NO_GO
9  [GOのみ] ブローカーで手動発注
10 trader-memory-core（store open-position）            →  ACTIVE thesis                  （実約定後のみ）
```

ステップ2・7・8・10は判断ポイントです。ステップ4は純粋な計算です。ステップ3はチャートベースで CLI はありません。

---

## ランブック

作業日を一度だけ設定してから、ステップ2に進みます。以降のファイル名やジャーナル記録が同じセッションに紐づくようにするためです。

```bash
export RUN_DATE=2026-07-15
```

以下の例では `ZBRK` という候補をスクリーニングします。

### ステップ 1 — 地合いが新規リスクを許容していることを確認

スクリーニングの前に `market-regime-daily`（最低でも `drawdown-circuit-breaker`）を実行します。地合いが restrictive であれば、新規エントリーを見送るか、ステップ2のスクリーニングに `--market-gate restrictive` を渡してください。スコアが高い候補でも `ACTIONABLE_DAY1` ではなく `MANUAL_REVIEW_ONLY` に格下げされます。

### ステップ 2 — Momentum Burst 候補をスクリーニング

```bash
# Mode A: FMP ユニバーススキャン（過去価格の取得に FMP_API_KEY が必要）
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --fmp-universe --max-symbols 300 \
  --market-gate allowed \
  --output-dir reports/

# Mode B: 銘柄を明示指定（過去価格の取得に FMP_API_KEY が必要）
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --symbols ZBRK NVDA SMCI \
  --market-gate allowed \
  --output-dir reports/

# Mode C: 完全オフライン（FMP クライアントは一切構築されない）
python3 skills/stockbee-momentum-burst-screener/scripts/screen_momentum_burst.py \
  --prices-json data/daily_ohlcv.json \
  --market-gate allowed \
  --output-dir reports/
```

Mode A と Mode B はどちらもスクリーニング前に `FMPClient` を構築するため `FMP_API_KEY` が必要です。完全オフラインで動くのは Mode C（`--prices-json`）だけです。

`stockbee_momentum_burst_<timestamp>.json` を生成します。各候補は `setup_score` と渡した `--market-gate` によって、次の5つの `state` のいずれかに分類されます。

| State | 条件 | 目安レーティング |
|---|---|---|
| `ACTIONABLE_DAY1` | score ≥ 80、market gate が restrictive でない | A / A- |
| `MANUAL_REVIEW` | 70 ≤ score < 80、market gate が restrictive でない | B |
| `MANUAL_REVIEW_ONLY` | score ≥ 70 **かつ** `--market-gate restrictive` | A／A-／B |
| `WATCH_ONLY` | 55 ≤ score < 70 | Watch |
| `REJECTED` | score < 55、または hard reject（最低株価・出来高割れ、トリガーなし、履歴不足、`entry_reference <= stop_reference`、または `--max-risk-pct-to-stop` を超えるリスク幅） | Reject |

`MANUAL_REVIEW_ONLY` は `MANUAL_REVIEW` の言い換えではなく独立した第5の状態です。地合い全体が restrictive のあいだは、スコアの高い候補であっても自動的にアクショナブルにはならないための仕組みです。サイジングの観点では `MANUAL_REVIEW` と同様に扱ってください。どちらの場合もフルのチャートレビューが必須で、この時点で自動的にアクショナブルになるものはありません。

このスクリーニング処理は、本プレイブック用のオフラインfixtureで実際にend-to-endで実行して確認済みです。20日間のタイトなベースの後に5倍の出来高で7.5%のブレイクアウトが発生したケースで、スコア86（`ACTIONABLE_DAY1`、レーティングA-）となり、`entry_reference` はトリガー日の終値、`stop_reference` はトリガー日の安値でした。

### ステップ 3 — チャート確認

`A`/`A-` の候補だけを `technical-analyst` に送って手動でチャートを確認します。`B` 候補はウォッチリストか、より小さいリスクでのレビューにとどめます。`Watch` レーティングの候補は、チャートレビューで格上げされない限りトレード計画を立てずモデルブックに残します。`Reject` 候補は執行対象ではなく、事後分析のキャリブレーション用にのみ保持します。

### ステップ 4 — ポジションをサイジング

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 54.05 --stop 50.38 --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/
```

`entry_reference` と `stop_reference` はスクリーナーの候補行（それぞれ直近終値とトリガー日安値）からそのまま使います。最終的な株数を決めるのはスクリーナーの役割ではなく、これら2つの参照値を渡すだけです。`risk_pct_to_stop` が自分の口座のリスク方針に対して広すぎる場合は、サイズを縮小するのではなく**NO TRADE**と判断してください。

### ステップ 5 — IDEA thesis を登録（専用アダプタなしの manual ingest）

`trader-memory-core` には `stockbee-momentum-burst-screener` 専用のアダプタが無く、候補は汎用の `--source manual` 経由で登録します。

```json
{
  "ticker": "ZBRK",
  "thesis_type": "growth_momentum",
  "setup_type": "stockbee_momentum_burst",
  "thesis_statement": "ZBRK 4pct_breakout on a 20-day tight base, ACTIONABLE_DAY1 score 86 (A-). Stockbee Momentum Burst short-term swing (2-5 sessions) — not a long-term or PEAD thesis.",
  "entry_price": 54.05,
  "stop_price": 50.38
}
```

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source manual --input idea.json --state-dir state/theses/
```

`Registered 1 thesis(es): th_...` と表示されます。この ID を export して以降のステップで使ってください。

```bash
export THESIS_ID=th_zbrk_grw_20260715_xxxx  # 表示された ID を貼り付け
```

**ここでの `thesis_type` の扱いには注意が必要です。** `trader-memory-core` には `dividend_income` / `growth_momentum` / `mean_reversion` / `earnings_drift` / `pivot_breakout` の5値しか無く、`growth_momentum` は Momentum Burst 専用のラベルではなく、消去法で最も近いものを選んでいるにすぎません。`canslim-screener` のアダプタも同じ `growth_momentum` で thesis を登録します。`list` サブコマンドは `--type`（thesis_type）でしかフィルタできず `--setup-type` は存在しないため、`trader_memory_cli.py store list --type growth_momentum` を実行すると Momentum Burst と CANSLIM 由来の thesis が混在して表示されます。上の `setup_type: stockbee_momentum_burst` フィールドこそが2つのコホートを実際に分ける手がかりであり、現状ではコマンドラインで絞り込むのではなく、各 thesis の YAML から手動でこのフィールドを読み取ることでしか分離できません。

### ステップ 6 — 上流のエビデンスをlink

`link_report()` は CLI サブコマンドではなく Python 関数です。`trader_memory_cli.py` を経由せず `thesis_store` を直接 import するため、trader-memory-core の依存（`pyyaml`、`jsonschema`）が必要です。`uv` 経由か、これらが導入済みの環境で実行してください。スクリーナーの出力とチャート確認レポートを thesis に link し、証跡を監査可能にします。以下のパスは各スキル自身が文書化している出力ファイル名の規則に沿った例であり、この実行で実際に生成されたファイルだと主張するものではありません。

```bash
uv run --project . python - <<PYEOF
import sys
sys.path.insert(0, "skills/trader-memory-core/scripts")
from pathlib import Path
import thesis_store

state_dir = Path("state/theses/")
thesis_id = "$THESIS_ID"
run_date = "$RUN_DATE"
for skill, path in [
    ("stockbee-momentum-burst-screener", f"reports/stockbee_momentum_burst_{run_date}_101500.json"),
    ("technical-analyst", f"reports/ZBRK_technical_analysis_{run_date}.md"),
]:
    thesis_store.link_report(state_dir, thesis_id, skill, path, run_date)
    print(f"linked {skill} -> {path}")
PYEOF
```

### ステップ 7 — `ENTRY_READY` へ遷移

チャートレビューとサイジングの両方が確認できたら遷移します。

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ transition "$THESIS_ID" ENTRY_READY \
  --reason "ACTIONABLE_DAY1 confirmed, sizing verified"
```

thesis はステップ10で実際の約定を記録するまで `IDEA` → `ENTRY_READY` のままで、決して `ACTIVE` にはなりません。このfixtureで直接確認済みです。`transition ENTRY_READY` の後、`store list --ticker ZBRK` は `"status": "ENTRY_READY"` を返し、`open-position` を実際の約定価格・日付で実行して初めて `"status": "ACTIVE"` に変わります。

### ステップ 8 — Pre-Trade Discipline Gate を実行

```bash
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --state-dir state/theses/ \
  --market-regime-decision reports/exposure_decision_latest.json \
  --circuit-breaker-decision reports/circuit_breaker_decision_latest.json \
  --output-dir reports/pre-trade-discipline
```

`ACTIONABLE_DAY1` は、ゲートが認識するアクショナブルな `order_intent` の一つです（`ENTRY_READY`、`ACTIONABLE`、`MANUAL_ORDER` と並んで）。このゲートは完全にオフラインで動作し、発注・注文キャンセル・監視は一切行わず、判断をジャーナルに記録するだけです。**`GO` の判定が出たときだけ発注してください。** `REVIEW_REQUIRED` や `NO_GO` は「まだトレードしない」ことを意味します。

### ステップ 9 — 手動で発注

このパイプラインのどのスキルもブローカーには触れません。ステップ4で計算したサイズで、自分自身で発注してください。

### ステップ 10 — 実約定を記録

```bash
export FILL_DATE=2026-07-16  # 実際にブローカーで約定した日

python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ open-position "$THESIS_ID" \
  --actual-price 54.10 --actual-date "$FILL_DATE" --shares 272
```

ここで初めて thesis が `ACTIVE` になります。計画上のエントリーが約定として扱われることは決してありません。

---

## 保有ルールとエグジット

このスキル自身の `references/entry_exit_rules.md` は、意図的に緩いエグジットテンプレートしか定めていません。トリガー日の安値を割ったらストップ、**3〜5セッション後にレビュー**、異常に速い値動き（特に1セッションで10%以上）では利益を保護、シグナルの完全な反転や数セッション経ってもフォロースルーが無い状態は失敗したバーストとして扱う、という内容だけです。これが参照文書のすべてであり、具体的なセッション番号をチェックポイントとして名指ししているわけではありません。

このプレイブックでは、その方針の上に次の具体的な運用解釈を追加します。**これはスキル自身のルールからの引用ではなく、このプレイブック独自の解釈**として扱ってください。

- 標準的な保有期間: 2〜3セッション。
- **セッション3** — フォロースルーレビューを行います。バーストがまだ確認できているか（トリガー日安値を上回ったまま、出来高が急減していないか）を見ます。
- **セッション5** — Momentum Burst ポジションとしての最終期限として扱います。ここまでに結着していなければ、2〜5セッションのスイングをなし崩し的に無期限保有にせず、手仕舞います。
- セッション数によらず、トリガー日安値割れ、シグナルの完全な反転、数セッション経ってもフォロースルーが無い場合はエグジットします。
- 1セッションで10%以上の急伸は利益保護のサインです（ストップの引き上げ、部分利確）。必ずしも即エグジットを意味しません。
- セッション5を超えて本当に保有を続けたい場合は、Momentum Burst の thesis のまま延長してはいけません。いったんクローズするか、メモ上で「転換」と記録した上で、Episodic Pivot や一般的なスイング thesis など別の `setup_type` を持つ**別 thesis** として再登録してください。そうすることで `trader-memory-core` の Momentum Burst コホートの統計が正しく保たれます。

## やってはいけないこと

- 4%の値動きだけを買いシグナルにしない。スコア、セットアップ品質、許容できるリスク距離のすべてが必要です。
- スクリーナーの出力を自動発注システムに繋がない。このパイプラインにそのような仕組みは存在せず、即興で作るべきでもありません。
- `risk_pct_to_stop` が自分のリスク方針に対して広すぎる候補を取らない。それは**NO TRADE**であり、サイズを小さくして対応するものではありません。
- 損失確定を避けるために、失敗した2〜5セッションのバーストを「長期投資」と言い換えない。

## PEADと混同しないこと {#dont-confuse-this-with-pead}

どちらのプレイブックも `trader-memory-core` を通じて流動性の高い米国株のスイングエントリーをスクリーニングしますが、コホートとしては別物です。

| | Momentum Burst | PEAD |
|---|---|---|
| カタリスト | 価格・出来高のブレイクアウト。決算は前提条件でない | 実際の決算ギャップアップを手動で確認したもの |
| エントリーパターン | タイトなベースからの4%ブレイクアウト／ドルブレイクアウト／レンジ拡大 | 赤週足の高値を上回る緑週足の終値 |
| 保有期間 | 2〜5セッション | 2〜6週間 |
| `thesis_type` | `growth_momentum`（CANSLIMと共有） | `earnings_drift`（型は共有、`pead-screener` 専用アダプタ） |
| Ingest経路 | `--source manual`、専用アダプタなし | `--source pead-screener`、fail-closedの専用アダプタ |
| ストップ参照 | トリガー日の安値 | 赤週足の安値 |

Stockbee の Episodic Pivot 分類器（`analyze_ep.py`）は両プレイブックの上流に位置します。`momentum_handoff` 候補（当日上昇率4%以上、かつ REJECT でない）をこのプレイブックへ渡しますが、実際に thesis として登録するのは `ACTIONABLE_DAY1` 状態の候補のみとする編集判断を取っており、それ以外の状態は watch にとどめます。同じ分類器はさらに `pead_handoff` 候補（決算・ガイダンスがカタリスト）を PEAD 候補として個別に示しますが、`pead_handoff` フラグ自体は PEAD のエントリーを意味しません。候補は、PEAD プレイブックが定める赤週足プルバック→ブレイクアウトの条件を独立に満たして初めて、[PEAD のエントリールール]({{ '/ja/playbooks/pead/' | relative_url }})が適用されます。

---

## 関連ページ

- このプレイブック専用の `workflows/*.yaml` manifest はまだ存在しません。`stockbee-momentum-burst-screener` は、より広範な [`stockbee-ep-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/stockbee-ep-daily.yaml) と [`swing-opportunity-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/swing-opportunity-daily.yaml) の両ワークフローに既に含まれていますが、Momentum Burst 単独のフローはありません。専用フローへの Trading Skills Navigator によるルーティングは、それが追加されるまでスコープ外です。
- スキルリファレンス: [Stockbee Momentum Burst Screener]({{ '/ja/skills/stockbee-momentum-burst-screener/' | relative_url }})
- 使用するスキル: `stockbee-momentum-burst-screener`、`technical-analyst`、`position-sizer`、`trader-memory-core`、`pre-trade-discipline-gate`
- 関連: [PEAD プレイブック]({{ '/ja/playbooks/pead/' | relative_url }})
