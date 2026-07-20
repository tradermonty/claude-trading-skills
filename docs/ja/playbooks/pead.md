---
layout: default
title: PEAD 決算後ドリフト・プレイブック
grand_parent: 日本語
parent: プレイブック
nav_order: 14
lang_peer: /en/playbooks/pead/
permalink: /ja/playbooks/pead/
---

# PEAD — 決算後ドリフト（Post-Earnings Announcement Drift）プレイブック

`pead-screener` 単体の説明ではなく、PEAD ワークフロー全体の使い方ガイドです。決算ギャップのスクリーニングから、赤週足のプルバック、ブレイクアウトエントリー、サイジング、`trader-memory-core` への登録、そして手仕舞いまでを一連の流れとして解説します。`pead-screener` を単体で走らせる前に、まずこのページを読んでください。

> **手動運用であり自動化ではありません。** このパイプラインのどのスキルも発注・注文キャンセル・監視を行わず、リアルタイム監視も存在しません。発注はすべて手動でブローカーに出します。

---

## 一段落で言うと

Post-Earnings Announcement Drift とは、決算でポジティブなサプライズが出てギャップアップした銘柄が、その後数週間にわたって上昇を続ける傾向のことです。市場の過小反応として学術的にも確認されています（Ball & Brown 1968、Bernard & Thomas 1989）。このプレイブックは、決算当日のギャップそのものではなく、**週足**での明確でリスク定義可能なパターンでこれを狙います。ギャップの後に整った赤週足のプルバックが形成されるのを待ち、その赤週足の高値を緑週足の終値が上回ったときにのみエントリーします。保有期間は**2〜6週間**であり、[Stockbee Momentum Burst プレイブック]({{ '/ja/playbooks/stockbee-momentum-burst/' | relative_url }})の1桁セッション保有とは異なります。2つのコホートを混同しないでください。

---

## いつ回すか

- `earnings-trade-analyzer` で直近の決算反応をスクリーニング済みの銘柄に対して実行します。これが後述の Mode B です。あるいは FMP の決算カレンダーに対して Mode A として直接実行します。
- 週次で、既にウォッチリストにある銘柄の stage 遷移（`MONITORING` → `SIGNAL_READY` → `BREAKOUT`）を確認します。
- 決算日から5週間（デフォルト、変更可能）のモニタリング窓の中で実行します。PEAD の効果は1〜3週目で最も強く、4〜5週目には弱まります。

## 回してはいけないとき

- **決算当日の飛び乗りとして使わない。** このプレイブックはギャップ当日には決してエントリーしません。まず赤週足が形成され、その後にブレイクアウトが必要です。プルバックせずにそのまま上昇する「gap-and-go」はエントリー候補ではありません。赤週足が無い間、スクリーナーは監視ウィンドウ（デフォルト5週）内では `MONITORING`（ウォッチリスト）に留め置き、ウィンドウを過ぎると `EXPIRED` になります。リスクをまだ定義できないためアクショナブルにはなりません。
- **オフラインでは動かない。** 両方の入力モードとも FMP API キーが必要です。詳しくは後述の[両モードともネットワーク必須](#network-requirement-both-modes)を参照してください。Momentum Burst の `--prices-json` に相当するオフラインモードはここには存在しません。
- **Momentum Burst の結果と混ぜない。** Momentum Burst のスキャンにも出てくる銘柄は、時間軸の異なる別の thesis です。詳しくは後述の[Momentum Burstと混同しないこと](#dont-confuse-this-with-momentum-burst)を参照してください。

---

## パイプライン全体像

```
1  earnings-trade-analyzer                    →  earnings_trade_analyzer_report （5要因スコアの決算反応、ネットワーク必須）
2  pead-screener（Mode B）                     →  pead_screener_report           （stage分類、ネットワーク必須）
3  手動でのgap方向確認                          →  候補ごとに gap_pct > 0 を確認（スクリーナーは強制しない、後述）
4  technical-analyst                          →  BREAKOUT候補のチャート確認         （画像ベース、CLIなし）
5  position-sizer                             →  ポジションサイズ                  （株数、純計算）
6  trader-memory-core（ingest --source pead-screener） →  IDEA thesis            （fail-closedの専用アダプタ）
7  trader-memory-core（link_report、uv run経由）        →  thesisへエビデンスをlink （決算・PEAD・チャートレビューのレポート）
8  trader-memory-core（store transition ENTRY_READY）  →  発注準備完了のthesis
9  pre-trade-discipline-gate                          →  GO / REVIEW_REQUIRED / NO_GO
10 [GOのみ] ブローカーで手動発注
11 trader-memory-core（store open-position）            →  ACTIVE thesis          （実約定後のみ）
```

ステップ3・6・8・9は候補を先へ進めないよう止められる判断ポイントです。ステップ5は純粋な計算です。

### 両モードともネットワーク必須 {#network-requirement-both-modes}

Momentum Burst の Mode C とは異なり、**このパイプラインのスクリーナー段階にはオフラインの入口がありません。** `screen_pead.py` は Mode A・B のどちらでも、他の処理より前に無条件で `FMPClient` を構築し、`FMP_API_KEY` が無ければその場で exit 1 します。各候補の週足パターン分析に必要な `get_historical_prices()` の呼び出しも、両モードともライブのネットワーク呼び出しです。以下の `trader-memory-core` の ingest・link・遷移・サイジングの各ステップ（6〜11）だけは、手書きの fixture に対して完全にオフラインで実行できます。このプレイブックの Phase 4 検証でも実際にそう検証しました。スクリーナー自体のコマンドは実際の `FMP_API_KEY` が必要であり、オフラインでは実行していません。

---

## ランブック

作業日を一度だけ設定してから、ステップ1に進みます。以降のファイル名・`link_report()` 呼び出し・ジャーナル記録が同じセッションに紐づくようにするためです。

```bash
export RUN_DATE=2026-07-15
```

### ステップ 1 — 直近の決算反応をスクリーニング

```bash
python3 skills/earnings-trade-analyzer/scripts/analyze_earnings_trades.py \
  --min-gap 3.0 --lookback-days 3 --top 20 \
  --output-dir reports/
```

ここで `--min-gap 3.0` を渡すことが重要です。これは `abs(gap_pct)`（`analyze_earnings_trades.py`）による大きさのフィルタなので**明示的に渡してください**。実際、Mode B・連鎖経路でギャップの大きさに下限を課しているのはここだけであり、それでも方向はチェックしません。下流の `screen_pead.py` 自身の `abs(gap_pct) < args.min_gap` フィルタ（491行目付近）は Mode A でしか動作せず、Mode B はこの上流フィルタと後述ステップ3の手動確認だけに依存します。`MONITORING`・`SIGNAL_READY`・`BREAKOUT` のどの `stage` 値も、それ単体で `gap_pct > 0` を証明するものではありません。

### ステップ 2 — 赤キャンドルのプルバックパターンをスクリーニング

```bash
# Mode A: FMP 決算カレンダー（FMP_API_KEY が必要）
python3 skills/pead-screener/scripts/screen_pead.py \
  --lookback-days 14 --watch-weeks 5 --min-gap 3.0 \
  --output-dir reports/

# Mode B: earnings-trade-analyzer の出力から連鎖（米国株のウォッチリスト運用に推奨）
python3 skills/pead-screener/scripts/screen_pead.py \
  --candidates-json reports/earnings_trade_analyzer_YYYY-MM-DD_HHMMSS.json \
  --min-grade B --output-dir reports/
```

寄り付き前の米国株ルーティンには Mode B を推奨します。Mode A はグローバルな FMP 決算カレンダーを取得するため、意図したウォッチリストに到達する前に API 予算を米国外銘柄に使ってしまうことがあります。

各結果には `stage` が付きます。

| Stage | 意味 | アクション |
|---|---|---|
| `MONITORING` | 窓内で決算後のギャップがあるが赤週足はまだ無い | ウォッチリストへ。週次で赤キャンドルの形成を確認 |
| `SIGNAL_READY` | 赤週足が形成された | 赤キャンドルの高値にアラートを設定し、発注を準備 |
| `BREAKOUT` | 現在の週足が緑で、赤キャンドルの高値を上回って終値をつけた | アクショナブル。チャート確認とサイジングへ進む |
| `EXPIRED` | モニタリング窓（デフォルト5週間）を超過 | ウォッチリストから外す |

**週の途中では stage が暫定的な値になることがあります。** `weekly_candle_calculator.py` は直近の週足（`weekly_candles[0]`）を使って `SIGNAL_READY`／`BREAKOUT` を判定しますが、その週がまだ確定していないかどうかはチェックしません。partial week（未確定週）を示すフラグは同じモジュール内に存在するものの、この判定では参照されていないためです。週の途中で実行すると、`SIGNAL_READY` や `BREAKOUT` の結果がまだ確定していない週足バーに基づいている可能性があります。金曜の週足終値を待ち、エントリー前に手動でチャートを確認してください。

### ステップ 3 — gap方向を手動で確認する（コードは強制しない）

**このステップは必須であり、パイプラインのどこにも自動化されていません。** `screen_pead.py` の `abs(gap_pct) < args.min_gap` フィルタは Mode A（`mode == "A"`）でしか動作しません。Mode B ではこのフィルタ自体がスキップされます。さらに、動作する場合であっても確認しているのは*大きさ*だけで*符号*は一切見ていません。セットアップ品質のスコアリングも負の `gap_pct` を通します。3%未満のギャップは負のものも含めてすべて `else: score += 10` の分岐に入り、除外されません。つまり実務上は、Mode B の実行結果として、実際には決算で**下に**ギャップした銘柄が「PEAD候補」として渡ってくることがあります。

`SIGNAL_READY` または `BREAKOUT` の結果を PEAD 候補として扱う前に、次を行ってください。

1. ギャップの大きさを担保するため、上流の `analyze_earnings_trades.py` に `--min-gap 3.0` かそれ以上の値を渡したことを確認する。
2. スクリーナー自身の出力にある**個々の候補ごとに `gap_pct > 0` を手動で確認する**。上流のフィルタから当然そうなっているとは想定しないこと。
3. これを「あればなお良い」ではなく必須の手順として扱う。スクリーナーはどのモードのどの段階でも gap の方向を保証しません。

### ステップ 4 — BREAKOUT候補のチャートと流動性を確認

`BREAKOUT` 候補を `technical-analyst` に送って手動でチャートを確認し、サイジングの前に流動性の3ゲートすべてを独立に確認してください。3つのうち1つか2つしか通らない候補はスコアが大きく下がり、トレード対象として扱うべきではありません。

| ゲート | 閾値 |
|---|---|
| ADV20（20日平均ドル出来高） | $25M 以上 |
| 平均株数出来高 | 100万株以上 |
| 株価 | $10 以上 |

あわせて次も確認します。明確な赤週足であること（doji やインサイドバーではない）、ブレイクアウト週の出来高が過去4週平均を上回ること、決算日から5週間以内であること。

### ステップ 5 — ポジションをサイジング

```bash
python3 skills/position-sizer/scripts/position_sizer.py \
  --entry 118.40 --stop 109.75 --account-size 100000 --risk-pct 1.0 \
  --output-dir reports/
```

エントリーは赤キャンドルの高値かそのわずか上、ストップは赤キャンドルの安値の下、標準ターゲットはエントリー + 2R です。

### ステップ 6 — IDEA thesis を登録（`pead-screener` 専用アダプタ）

`trader-memory-core` にはこのソース専用のアダプタがあります。Momentum Burst のように手でレコードを組み立てる必要はなく、スクリーナー自身の `{"results": [...]}` の JSON をそのまま渡します。

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
  --source pead-screener --input reports/pead_screener_YYYY-MM-DD_HHMMSS.json \
  --state-dir state/theses/
```

`Registered N thesis(es): th_...` と表示されます。取引する候補の ID を export してください。

```bash
export THESIS_ID=th_peady_ern_20260715_xxxx  # 表示された ID を貼り付け
```

このアダプタはスクリーナーの実際のフィールド名である `stage` と `stop_price` を読みます。実際のレコードには存在しない `status`/`stop_loss` ではありません。`thesis_type` はすべての PEAD 登録で `earnings_drift` に固定されますが、この値自体は PEAD 専用ではありません。`earnings-trade-analyzer` アダプタと `edge-candidate-agent` アダプタも、それぞれの thesis に `earnings_drift` を割り当てます。PEAD の thesis を特定するのは `thesis_type` 単体ではなく `origin.skill == pead-screener`（PEAD 専用アダプタ）です。`store list --type earnings_drift` を実行すると earnings-trade-analyzer 由来の thesis も一緒に返ってきます。`list --type growth_momentum` に CANSLIM の thesis が混ざるのと同じ構図です。

**このアダプタは `BREAKOUT` 候補に対して fail-closed です。** `stage == "BREAKOUT"` のレコードで `stop_price` が欠落・非数値・`NaN`・`Infinity`・ゼロ・負の値のいずれかである場合、登録そのものを拒否します。ストップ無しで登録することも、不正なストップのまま登録することもありません。このプレイブック用に手書きした fixture で直接確認済みです。`stop_price` フィールドの無い `BREAKOUT` レコード単体を渡すと次の出力になりました。

```text
ERROR: Adapter error for pead-screener: PEAD record for 'PEADZ' is stage=BREAKOUT (actionable) but stop_price is
missing/non-numeric/non-finite/non-positive (None) — refusing to register an actionable thesis without a valid stop
No theses registered.
```

exit コードは**1**でした。この挙動は `skills/trader-memory-core/scripts/tests/test_thesis_ingest.py` の既存回帰テスト `test_ingest_pead_breakout_rejects_invalid_stop_fail_closed`（7ケース: `None`／非数値／`NaN`／`+Infinity`／`−Infinity`／ゼロ／負の値でパラメータ化）でもカバーされています。`MONITORING` と `SIGNAL_READY` の候補は問題なく登録され、`exit.stop_loss` は未設定のままになります。これらの stage には設計上まだ本物のストップが存在しないためで、アダプタが不正な仮の値でそこを埋めることはありません。

### ステップ 7 — 上流のエビデンスをlink

`link_report()` は CLI サブコマンドではなく Python 関数です。`trader_memory_cli.py` を経由せず `thesis_store` を直接 import するため、trader-memory-core の依存（`pyyaml`、`jsonschema`）が必要です。`uv` 経由か、これらが導入済みの環境で実行してください。決算スクリーン・PEAD スクリーン・チャート確認レポートを thesis に link し、証跡を監査可能にします。以下のパスは各スキル自身が文書化している出力ファイル名の規則に沿った例であり、この実行で実際に生成されたファイルだと主張するものではありません。

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
    ("earnings-trade-analyzer", f"reports/earnings_trade_analyzer_{run_date}_090000.json"),
    ("pead-screener", f"reports/pead_screener_{run_date}_093000.json"),
    ("technical-analyst", f"reports/PEADY_technical_analysis_{run_date}.md"),
]:
    thesis_store.link_report(state_dir, thesis_id, skill, path, run_date)
    print(f"linked {skill} -> {path}")
PYEOF
```

### ステップ 8 — `ENTRY_READY` へ遷移

```bash
python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ transition "$THESIS_ID" ENTRY_READY \
  --reason "BREAKOUT confirmed, liquidity gates checked, sizing verified"
```

thesis はステップ11で実際の約定を記録するまで `IDEA` → `ENTRY_READY` のままで、決して `ACTIVE` にはなりません。上記の fixture で直接確認済みです。`transition ENTRY_READY` の後、`store list --ticker PEADY` は `"status": "ENTRY_READY"` を返します。

### ステップ 9 — Pre-Trade Discipline Gate を実行

```bash
python3 skills/pre-trade-discipline-gate/scripts/check_pre_trade_discipline.py \
  --answers-file state/manual-entry-checklist.json \
  --state-dir state/theses/ \
  --market-regime-decision reports/exposure_decision_latest.json \
  --circuit-breaker-decision reports/circuit_breaker_decision_latest.json \
  --output-dir reports/pre-trade-discipline
```

**`GO` の判定が出たときだけ発注してください。**

### ステップ 10 — 手動で発注

このパイプラインのどのスキルもブローカーには触れません。ステップ5で計算したサイズで、自分自身で発注してください。

### ステップ 11 — 実約定を記録

```bash
export FILL_DATE=2026-07-16  # 実際にブローカーで約定した日

python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
  --state-dir state/theses/ open-position "$THESIS_ID" \
  --actual-price 118.55 --actual-date "$FILL_DATE" --shares 115
```

ここで初めて thesis が `ACTIVE` になります。計画上のエントリーが約定として扱われることは決してありません。

---

## 保有ルールとエグジット

ストップは赤週足の安値、ターゲットはエントリー + 2R です。中心的な保有期間は**2〜6週間**です。

- 1Rの利益が出たらストップをブレイクイーブンに引き上げます。
- 1.5Rを超えたらストップをトレイルします。
- **2Rは全量強制利確の水準ではなく判断点です。** 週足のトレンドの状態に応じて、部分利確・ストップ引き上げ・継続保有のいずれかを選びます。
- エントリーからおよそ4週間経ってもターゲットに届いていなければ、無期限に保有するのではなく scratch または小幅な損失としてクローズすることを検討します。
- PEAD の効果は決算後6〜8週間で目立って減衰します。この期間を超えて当初の PEAD thesis のまま保有し続けないでください。
- エグジットは週足終値でのストップ抵触、thesis の無効化、または時間経過による効果減衰で判断します。固定の日数だけで機械的に保有せず、週足のトレンドとストップ水準を確認してください。

## やってはいけないこと

- 決算当日のギャップに飛び乗るトレードとして説明しない。このプレイブックは明示的にそれを行いません。エントリーはギャップから数週間後の、赤週足を上回るブレイクアウトです。
- 赤週足の無い gap-and-go を PEAD エントリーと呼ばない。赤週足の安値をストップにできなければリスクを定義できません。
- PEAD の結果を Momentum Burst の統計と混ぜない、その逆も同様です。`thesis_type` が異なる別々のコホートです。
- 固定の日数だけで機械的に保有しない。週足のトレンドとストップ水準を確認してください。カレンダーだけを見て判断しないでください。
- 収益を保証しない。PEAD はこの手法の根拠となった研究において、過去は55〜65%の勝率、勝ちトレードが負けトレードの1.5〜2.5倍という傾向を示してきましたが、これは個別のトレードを保証するものではありません。

## Momentum Burstと混同しないこと {#dont-confuse-this-with-momentum-burst}

どちらのプレイブックも `trader-memory-core` を通じて流動性の高い米国株のスイングエントリーをスクリーニングしますが、コホートとしては別物です。

| | PEAD | Momentum Burst |
|---|---|---|
| カタリスト | 実際の決算ギャップアップを手動で確認したもの | 価格・出来高のブレイクアウト。決算は前提条件でない |
| エントリーパターン | 赤週足の高値を上回る緑週足の終値 | タイトなベースからの4%ブレイクアウト／ドルブレイクアウト／レンジ拡大 |
| 保有期間 | 2〜6週間 | 2〜5セッション |
| `thesis_type` | `earnings_drift`（型は共有、`pead-screener` 専用アダプタ） | `growth_momentum`（CANSLIMと共有） |
| Ingest経路 | `--source pead-screener`、fail-closedの専用アダプタ | `--source manual`、専用アダプタなし |
| オフライン検証 | アダプタ・サイジングの段階のみ。スクリーナー自体は `FMP_API_KEY` が必要 | スクリーナー（Mode C）を含め完全にオフライン |

Stockbee の Episodic Pivot 分類器（`analyze_ep.py`）は、決算・ガイダンスをカタリストとする `pead_handoff` 候補を示すことがあります。ただしこのフラグだけでは PEAD のエントリーにはなりません。**フラグが立った段階であり、まだ資格を満たしたわけではない**という位置付けです。候補は、このプレイブックが定める赤週足の形成とその後のブレイクアウトという条件を独立に満たす必要があります。同じ分類器の `momentum_handoff` フラグが Momentum Burst 側にどう渡されるかは、[Stockbee Momentum Burst プレイブック]({{ '/ja/playbooks/stockbee-momentum-burst/' | relative_url }})を参照してください。

---

## 関連ページ

- このプレイブック専用の `workflows/*.yaml` manifest はまだ存在しません。`pead-screener` は、より広範な [`stockbee-ep-daily`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/stockbee-ep-daily.yaml) ワークフローに `stockbee-momentum-burst-screener` と並んで既に含まれていますが、PEAD 単独のフローはありません。専用フローへの Trading Skills Navigator によるルーティングは、それが追加されるまでスコープ外です。
- スキルリファレンス: [PEAD Screener]({{ '/ja/skills/pead-screener/' | relative_url }})
- 使用するスキル: `earnings-trade-analyzer`、`pead-screener`、`technical-analyst`、`position-sizer`、`trader-memory-core`、`pre-trade-discipline-gate`
- 関連: [Stockbee Momentum Burst プレイブック]({{ '/ja/playbooks/stockbee-momentum-burst/' | relative_url }})
