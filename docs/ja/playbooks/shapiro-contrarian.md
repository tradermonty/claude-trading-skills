---
layout: default
title: Shapiro COT 逆張りプレイブック
grand_parent: 日本語
parent: プレイブック
nav_order: 20
lang_peer: /en/playbooks/shapiro-contrarian/
permalink: /ja/playbooks/shapiro-contrarian/
---

# Shapiro COT 逆張り — 週次プレイブック

`shapiro-contrarian` ワークフロー全体の使い方ガイドです。個別スキルの説明ではなく、パイプラインを最初から最後まで通しで解説します。いつ回すか、6つのステップの順序、ゲートがどう判断するか、ポジションをどう計算するか、そして逆張り仮説をトレードメモリにどう登録するか。6つのスキルを単体で走らせる前に、まずこのページを読んでください。

> **これは実験キット v1 です。** 目的は、Shapiro 流の逆張りを規律ある週次ルーティンとして「始める」ことであって、収益性を証明することではありません。発注と監視は手動です。自動発注はありません。ポジション監視は別スキルとして後から提供します。

---

## 一段落で言うと

Jason Shapiro の逆張り手法は、先物市場で「混み合った投機ポジション」に対して群衆と逆方向に仕掛けます（= fade）。ただし混雑そのものは決してトレードのシグナルにはなりません。エッジが生まれるのは、群衆がさらに間違っているときだけです。群衆に有利なはずのニュースに価格が反応せず、週足チャートが既に群衆と逆に転換し始めている。このパイプラインはその規律を強制します。まず COT レポートで混雑をスクリーニングし、次にニュース反応の失敗と週足の価格反転という2つの独立した確認を要求します。この2つが揃って初めて、fail-closed のゲートがサイジングを許可します。3つすべてが揃った市場でのみ、群衆を fade します。

---

## いつ回すか

- **週次**。CFTC の Commitment of Traders レポート公表後に回します。公表は金曜 15:30 ET 前後で、火曜時点のポジションを反映しています。
- 混雑の読みは**火曜終値時点**として扱い、リアルタイムとは見なしません。COT データは3日遅れです。

## 回してはいけないとき

- **日中や週次より高頻度では回さない。** エッジはポジショニング由来で、COT は週1回しか更新されません。
- **混雑の極値だけでは決して動かない。** サイジングの前に、ゲートが `READY_FOR_PLAN` に到達する必要があります。混雑・ニュース失敗・価格反転がすべて確認された状態です。
- **株式は対象外。** 扱うのは CFTC 先物市場のみです。

---

## パイプライン全体像

```
1  cot-contrarian-detector        →  cot_crowding_report            (3年COTインデックスの極値をスクリーン)
2  news-reaction-failure-analyzer →  news_failure_verdict           (群衆に有利なニュースを価格が無視)
3  technical-analyst              →  price_action_confirmation_report (週足で群衆と逆の反転)
4  contrarian-setup-gate          →  contrarian_setup_gate_report   (READY_FOR_PLANのみ、fail-closed)
5  futures-position-sizer         →  futures_position_size          (枚数計算、純計算)
6  trader-memory-core             →  contrarian_thesis_entry        (逆張り仮説を登録)
```

ステップ 1〜4 と 6 は**判断ゲート**です。各ステップが候補を先へ進めないよう止められます。ステップ 5 は純粋な計算です。いずれかのゲートで落ちた市場はそのまま脱落します。それがこの設計の狙いです。

---

## 週次ランブック

ステップ 1 の前に、作業日を**一度だけ**シェル変数として設定してください。以下の各ステップはすべてこの変数からファイル名を読み書きするので、証跡の連鎖が最初から最後まで途切れません — ステップ2〜6が昨日の（あるいは誰のものでもない）レポートを黙って読んでしまうのを防ぎます。

```bash
export RUN_DATE=2026-07-15
```

以下の例では `B6` という混み合った市場を fade します。

### ステップ 1 — COT の混雑をスクリーニング

```bash
python3 skills/cot-contrarian-detector/scripts/screen_cot_crowding.py \
  --core --as-of "$RUN_DATE" --output-dir reports/
```

`reports/cot_crowding_$RUN_DATE.json`（`cot_crowding_report`）を生成します。3年 COT インデックスの極値にある市場だけを先へ進めます。`CROWDED_LONG` / `CROWDED_SHORT` が対象です。混雑は**前提条件でありシグナルではありません**。これ単体で動いてはいけません。

### ステップ 2 — ニュース反応の失敗を確認

```bash
python3 skills/news-reaction-failure-analyzer/scripts/analyze_news_reaction.py \
  --symbol B6 --detector-json "reports/cot_crowding_$RUN_DATE.json" \
  --events-json "reports/nrf_events_B6_$RUN_DATE.json" \
  --as-of "$RUN_DATE" --output-dir reports/
```

`reports/nrf_B6_$RUN_DATE.json`（`news_failure_verdict`）を生成します。events ファイルは実在 URL を持つ一次情報・通信社配信から精選してください。捏造は禁止です。`CONFIRMED` の市場だけを残します。`NOT_CONFIRMED` と `INSUFFICIENT_EVIDENCE` はここで止まります。

### ステップ 3 — 週足の価格反転を確認

```bash
python3 skills/technical-analyst/scripts/check_weekly_price_action.py \
  --symbol B6 --detector-json "reports/cot_crowding_$RUN_DATE.json" \
  --as-of "$RUN_DATE" --output-dir reports/
```

`reports/ta_confirmation_B6_$RUN_DATE.json`（`price_action_confirmation_report`）を生成します。`--detector-json` はステップ1から群衆の direction を渡すためのものです。これ（または明示的な `--direction`）が無いと、何に対して反転を確認すればよいか分からず `no_direction_provided` で終了し、判定が出ません。週足チャートで群衆と逆の反転を探します。キーリバーサル、フェイルドブレイクアウト、極値の失敗のいずれかで、**明確なスイングストップ**を伴うものです。`NOT_CONFIRMED` / `INSUFFICIENT_DATA` は却下します。

### ステップ 4 — ゲートで統合

```bash
python3 skills/contrarian-setup-gate/scripts/run_contrarian_setup_gate.py \
  --symbol B6 \
  --detector-json "reports/cot_crowding_$RUN_DATE.json" \
  --news-json "reports/nrf_B6_$RUN_DATE.json" \
  --price-action-json "reports/ta_confirmation_B6_$RUN_DATE.json" \
  --as-of "$RUN_DATE" --output-dir reports/
```

`reports/contrarian_setup_gate_B6_$RUN_DATE.json`（`contrarian_setup_gate_report`）を生成します。`--as-of` は**必須**です。ゲートはこれを使って上流の各レポートの鮮度を検証するため、無いと exit 2 で終了します。ゲートは **fail-closed** で、ステップを順番に評価します。サイジングへ進めるのは `READY_FOR_PLAN` のみです。`CROWDED`、`WATCHING_PRICE`、`REJECTED`、`INSUFFICIENT_EVIDENCE` はすべてここで止まります。ゲートが次へ渡すのは `symbol`、`direction`、`invalidation_level` の3つだけです。

### ステップ 5 — 先物の枚数を計算

```bash
python3 skills/futures-position-sizer/scripts/futures_position_sizer.py \
  --gate-json "reports/contrarian_setup_gate_B6_$RUN_DATE.json" \
  --entry 1.3820 --account-size 200000 --risk-pct 1.0 \
  --as-of "$RUN_DATE" --output-dir reports/ --format both
```

`reports/futures_position_size_B6_$RUN_DATE.json`（`futures_position_size`）を生成します。direction と stop はゲートから来ます。一方で **`--entry`、`--account-size`、`--risk-pct` は常にオペレーターが供給します**。ゲートもサイザーもこれらを導出しないので、実行前に手元で用意してください。先へ進めるのは `SIZED` の結果だけで、`NO_TRADE` はここで止まります。発注前に枚数と1枚あたりリスクを検証し、ポートフォリオ全体のヒートが予算内であることを確認します。

### ステップ 6 — 逆張り仮説を登録

ステップ 6 で、計画がトレードメモリ上の監査可能な記録になります。操作は**この順序で厳密に**実行してください。`attach-futures-position` は**既存の**仮説に添付する操作であり作成はしません。また `open-position` は `ENTRY_READY` を要求し、`IDEA` のままでは拒否されます。

1. **IDEA 仮説を作成**します（manual ingest または `register()`）。`idea.json` に必要なのは `ticker` / `thesis_type` / `thesis_statement` の3つだけです。以下の `entry_price` のようなそれ以外の項目は `origin.raw_provenance` に記録として残るだけで、正式な価格として扱われるわけではありません。

   ```json
   {
     "ticker": "B6",
     "thesis_type": "mean_reversion",
     "thesis_statement": "B6の買い持ち偏重によるCOT極値、ニュース反応の失敗と週足反転を確認 — 群衆に逆張りしてショート。",
     "entry_price": 1.3820
   }
   ```

   ```bash
   python3 skills/trader-memory-core/scripts/trader_memory_cli.py ingest \
     --source manual --input idea.json --state-dir state/theses/
   ```

   `Registered 1 thesis(es): th_...` と表示されます。この ID を export してください。以降のステップで使います。

   ```bash
   export THESIS_ID=th_b6_mean_reversion_20260715_xxxx  # 表示された ID を貼り付け
   ```

2. **SIZED レポートを添付**します（仮説がまだ `IDEA` のままでも実行できます）。これで枚数・direction・multiplier・USD 通貨・リスクが仮説の position に保存されます。

   ```bash
   python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
     --state-dir state/theses/ attach-futures-position "$THESIS_ID" \
     --report "reports/futures_position_size_B6_$RUN_DATE.json"
   ```

3. **上流の証跡を link** します。`link_report()` は CLI サブコマンドではなく Python 関数です。`trader_memory_cli.py` を経由せず `thesis_store` を直接 import するため、trader-memory-core の依存（`pyyaml`、`jsonschema`）が必要です。`uv` 経由か、これらが導入済みの環境で実行してください。以下を実行して4つの上流レポートを直接 link し、fade の証跡連鎖を監査可能にします。

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
       ("cot-contrarian-detector", f"reports/cot_crowding_{run_date}.json"),
       ("news-reaction-failure-analyzer", f"reports/nrf_B6_{run_date}.json"),
       ("technical-analyst", f"reports/ta_confirmation_B6_{run_date}.json"),
       ("contrarian-setup-gate", f"reports/contrarian_setup_gate_B6_{run_date}.json"),
   ]:
       thesis_store.link_report(state_dir, thesis_id, skill, path, run_date)
       print(f"linked {skill} -> {path}")
   PYEOF
   ```

4. サイジングを確認し発注準備ができたら、**`ENTRY_READY` へ遷移**します。

   ```bash
   python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
     --state-dir state/theses/ transition "$THESIS_ID" ENTRY_READY \
     --reason "READY_FOR_PLAN confirmed and sizing verified"
   ```

5. **実際にブローカーで約定した後にのみ `ACTIVE` へ遷移**します。実約定価格と日付を渡します。日付は分析日ではなく実際の約定日を使うため、別変数 `FILL_DATE` にします。`entry.actual_date` は保有期間や事後評価の基準になるので、後日約定したときに分析日を入れると値がずれてしまいます。`--contracts` / `--multiplier` / `--direction` はステップ2で既に仮説に付与済みなので省略できます。

   ```bash
   export FILL_DATE=2026-07-16  # 実際にブローカーで約定した日。同日約定なら $RUN_DATE と同じでよい

   python3 skills/trader-memory-core/scripts/trader_memory_cli.py store \
     --state-dir state/theses/ open-position "$THESIS_ID" \
     --actual-price 1.3835 --actual-date "$FILL_DATE"
   ```

`contrarian_thesis_entry` を生成します。これは下流の `trade-memory-loop` と `monthly-performance-review` へ流れます。

---

## 規律とガードレール

- **混雑は前提条件であり、トレードシグナルではありません。** サイジングの前にニュース失敗と価格反転の両方の確認を要求します。
- **ゲートが安全装置です。** ゲートが独立に `READY_FOR_PLAN` に到達しない限り、何もサイジングされません。
- **計画エントリーは実約定ではありません。** `attach-futures-position` は `entry.actual_price` を設定しません。manual ingest では計画エントリーは `origin.raw_provenance.entry_price` に保持されます。約定前に `entry.actual_price` へ書き込んではいけません。
- **自動発注はありません。** すべての発注はブローカーで手動で行います。
- **監視は当面手動です。** COT の正常化、ストップ、仮説の無効化は、`contrarian-position-monitor` が提供されるまで手作業で見ます。この監視スキルは [#243](https://github.com/tradermonty/claude-trading-skills/issues/243) で追跡しています。
- **トレードメモリへの受け渡しは USD 限定です。** サイザー単体は `--fx-rate`（銘柄通貨→USD のレート）を渡せば非 USD 銘柄もサイズ計算できます。USD 限定なのは `attach-futures-position` によるトレードメモリへの受け渡しの方で、非 USD の SIZED レポートは、黙って誤登録するのではなくここで拒否されます。
- **証拠金は計算しません。** 先物の証拠金はブローカーと時期に依存します。取引前に当初証拠金と維持証拠金をブローカーで確認してください。

---

## ここでの「完成」の意味

実験キットは**6スキル中6完成**でマージ済みです。今日から Shapiro 流の逆張りを規律ある週次ルーティンとして始められます。自動ポジション監視を含むライフサイクル全体は**6/7**です。監視スキルは意図的に延期しており、実運用またはシャドー運用の経験を踏まえてから設計します。

このキットは実験を「始める」ためのものです。戦略が収益的だとは主張しません。それを検証するのが、週次ルーティン、トレードメモリの記録、月次レビューの役割です。

---

## 関連

- ワークフロー manifest: [`workflows/shapiro-contrarian.yaml`](https://github.com/tradermonty/claude-trading-skills/blob/main/workflows/shapiro-contrarian.yaml) が正本です
- 自動生成リファレンス: [ワークフロー]({{ site.baseurl }}/ja/workflows/#shapiro-contrarian)
- 6つのスキル: `cot-contrarian-detector`、`news-reaction-failure-analyzer`、`technical-analyst`、`contrarian-setup-gate`、`futures-position-sizer`、`trader-memory-core`
