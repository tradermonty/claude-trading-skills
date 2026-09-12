# スキル自動化クイックスタート

このGitHub向けメンテナーガイドでは、以前メインREADMEに記載されていた
2つのリポジトリ自動化パイプラインを説明します。初心者向けトレード導線や
ドキュメントサイトのナビゲーションには含まれません。

- [READMEへ戻る](../../README.ja.md)
- [English](skill-automation.md)
- [メンテナンスrunbook（英語）](maintenance-runbook.md)
- [自己改善の実装詳細（英語）](../../CLAUDE.md#skill-self-improvement-loop)
- [自動生成の実装詳細（英語）](../../CLAUDE.md#skill-auto-generation-pipeline)

以下のコマンドはすべてリポジトリルートから実行します。環境構築、drift gate、
復旧手順、定期jobのトラブルシューティングは
[maintenance runbook](maintenance-runbook.md)を参照してください。

`run_skill_improvement.sh`と`run_skill_generation.sh`は、guard付きのmacOS
`launchd`専用wrapperです。LinuxまたはWindowsでは、**手動実行**に記載した
Python orchestratorを直接使ってください。自己改善orchestratorは、事前に分離した
clean checkout内でのみ実行します。Pythonを直接呼んでも、macOS wrapperが行う
専用checkoutの作成・resetは再現されません。詳細は
[platformサポートマトリクス](platform-support.ja.md)を参照してください。

## 安全性と副作用

`--dry-run`はbranchやPRの作成を抑止しますが、filesystemをread-onlyには
しません。現行実装の境界は次のとおりです。

| モード | 読み取り | ローカル書き込み | Claude CLI | Git / GitHub書き込み |
| --- | --- | --- | --- | --- |
| 自己改善dry-run | skill、リポジトリmetadata、既存state | lock/log、auto-review成果物、日次summary、`.skill_improvement_state.json` | なし | なし |
| 自己改善通常実行 | skill、リポジトリmetadata、既存state | review成果物、log、summary、state、必要な場合は選定skill | Claude CLIが利用可能なら通常実行ごとに選定skillをreviewし、auto scoreが閾値未満の場合だけ編集 | `git pull --ff-only`を実行。branch、commit、push、PR作成を行う場合があり、PRがmergedまたはclosedのlocal automation branchを削除 |
| 自動生成daily dry-run | 既存idea backlog | lock/log、日次summary、`.skill_generation_state.json` | なし | なし。backlog statusも変更しない |
| 自動生成weekly dry-run | `~/.claude/projects/`以下のallowlist対象session log | `raw_candidates.yaml`、lock/log、週次summary、`.skill_generation_state.json` | なし | なし。backlogも更新しない |
| 自動生成weekly通常実行 | allowlist対象session logと既存backlog | raw candidate、backlog、log、summary、state | session由来signalと長さ・件数を制限したuser-message sampleをabstraction promptへ渡す場合あり。その結果生成されたcandidate descriptionをscoring promptへ渡す。生のsession-log file自体は直接送信しない | なし |
| 自動生成daily通常実行 | 既存idea backlogとリポジトリfile | `skills/<name>/`、生成された英日skill docsとindex/catalog、必要な場合の`pyproject.toml`、report、backlog、log、summary、state | 選定skillをdesign・review | `git pull --ff-only`を実行。同名のstale local branchを削除した後、branch、commit、push、PR作成を行う場合があり、PRがmergedまたはclosedのlocal automation branchも削除 |

この表はPython orchestratorを直接実行した場合を説明しています。自己改善の`launchd`
wrapperは専用checkoutを管理し、`fetch`、`checkout -B main origin/main`、
`reset --hard origin/main`、`clean -fd`を実行します。有効化前に
[専用checkoutの説明](maintenance-runbook.md#the-improvement-loop-runs-in-its-own-checkout)を確認してください。

自動生成daily通常実行は`skill-packages/<name>.skill`を生成・更新しません。
review後に別途packageを生成します。

```bash
python3 scripts/package_skills.py --skill <name>
```

weekly通常実行の前に入力内容を確認してください。入力元fileはローカルですが、
`claude -p`を呼ぶabstraction・scoring段階はローカル処理だけでは完結しません。

## スキル自己改善ループ

このセクションはコントリビューター向けです。初めて使う人は読み飛ばして、
READMEのCore + Satellite導線から始めてください。

スキル品質を継続的にレビュー・改善する自動パイプラインです。毎日の`launchd`
jobが1つのスキルを選択し、デュアルアクシスレビュアーでスコアリングし、
スコアが90/100未満の場合は`claude -p`で改善を適用してPRを作成します。

### 仕組み

1. **ラウンドロビン選択** — レビュアー自身を除く全スキルを順番に巡回。状態は`logs/.skill_improvement_state.json`に永続化。
2. **オートスコアリング** — `run_dual_axis_review.py`を実行して決定論的スコア（0-100）を取得。
3. **改善ゲート** — `auto_review.score < 90`の場合、Claude CLIがSKILL.mdとリファレンスを修正。
4. **品質ゲート** — 改善後に再スコアリング（テスト有効）。スコアが改善されなかった場合はロールバック。
5. **PR作成** — 変更をフィーチャーブランチにコミットし、人間レビュー用にGitHub PRを作成。
6. **日次サマリー** — 結果を`reports/skill-improvement-log/YYYY-MM-DD_summary.md`に出力。

### 手動実行

```bash
# ドライラン: 改善やPR作成なしでスコアリングのみ
python3 scripts/run_skill_improvement_loop.py --dry-run

# フルラン: スコアリング、必要に応じて改善、PR作成
python3 scripts/run_skill_improvement_loop.py
```

以前のREADMEには次のコマンドも記載されていました。

```bash
python3 scripts/run_skill_improvement_loop.py --dry-run --all
```

現行のオーケストレーションCLIは`--all`を受け付けません。全skillを変更せずに
reviewする場合は、レビュアーを直接実行します。

```bash
uv run skills/dual-axis-skill-reviewer/scripts/run_dual_axis_review.py \
  --project-root . --all --output-dir reports/
```

### launchd設定 (macOS)

毎日05:00にmacOS `launchd`で自動実行します。

```bash
# エージェントをインストール
cp launchd/com.trade-analysis.skill-improvement.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-improvement.plist

# 確認
launchctl list | grep skill-improvement

# 手動トリガー
launchctl start com.trade-analysis.skill-improvement
```

### 主要ファイル

| ファイル | 用途 |
| --- | --- |
| `scripts/run_skill_improvement_loop.py` | オーケストレーションスクリプト（選択、スコアリング、改善、PR） |
| `scripts/run_skill_improvement.sh` | guard付きmacOS launchd専用シェルラッパー |
| `launchd/com.trade-analysis.skill-improvement.plist` | macOS launchdエージェント設定 |
| `skills/dual-axis-skill-reviewer/` | レビュアースキル（スコアリングエンジン） |
| `logs/.skill_improvement_state.json` | ラウンドロビン状態と履歴 |
| `reports/skill-improvement-log/` | 日次サマリーレポート |

## スキル自動生成パイプライン

このセクションはコントリビューター向けです。トレード運用に必須のworkflowではなく、
リポジトリ保守用の自動化です。

セッションログからスキルアイデアをマイニング（週次）し、設計・レビュー・PR作成
（日次）を自動実行するパイプラインです。自己改善ループと連携してスキルカタログを
継続的に拡張します。

### 仕組み

1. **週次マイニング** — Claude Codeセッションログをスキャンし、スキル化できる繰り返しパターンを検出。各アイデアを新規性・実現可能性・トレーディング価値でスコアリング。
2. **バックログスコアリング** — ランク付けされたアイデアを`logs/.skill_generation_backlog.yaml`にステータス追跡付きで保存（`pending`、`in_progress`、`completed`、`design_failed`、`review_failed`、`pr_failed`）。
3. **日次選択** — 最高スコアの`pending`アイデアを選択。`design_failed`/`pr_failed`は1回リトライ（`review_failed`はコンテンツ品質の問題を示すため最終判定）。
4. **設計＆レビュー** — スキルデザイナーが完全なスキル（SKILL.md、リファレンス、スクリプト）を構築し、デュアルアクシスレビュアーがスコアリング。スコアが低い場合は`review_failed`。
5. **PR作成** — 新スキルをフィーチャーブランチにコミットし、人間レビュー用にGitHub PRを作成。

### 手動実行

```bash
# 週次: セッションログからアイデアをマイニング・スコアリング
python3 scripts/run_skill_generation_pipeline.py --mode weekly --dry-run

# 日次: バックログの最高スコアアイデアからスキルを設計
python3 scripts/run_skill_generation_pipeline.py --mode daily --dry-run

# フルラン（ブランチ作成、スキル設計、PR作成）
python3 scripts/run_skill_generation_pipeline.py --mode daily
```

### launchd設定 (macOS)

週次と日次の2つの`launchd`エージェントで自動実行します。

```bash
# エージェントをインストール
cp launchd/com.trade-analysis.skill-generation-weekly.plist ~/Library/LaunchAgents/
cp launchd/com.trade-analysis.skill-generation-daily.plist ~/Library/LaunchAgents/
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-generation-weekly.plist
launchctl load ~/Library/LaunchAgents/com.trade-analysis.skill-generation-daily.plist

# 確認
launchctl list | grep skill-generation

# 手動トリガー
launchctl start com.trade-analysis.skill-generation-weekly
launchctl start com.trade-analysis.skill-generation-daily
```

### 主要ファイル

| ファイル | 用途 |
| --- | --- |
| `scripts/run_skill_generation_pipeline.py` | オーケストレーションスクリプト（マイニング、選択、設計、レビュー、PR） |
| `scripts/run_skill_generation.sh` | guard付きmacOS launchd専用シェルラッパー |
| `launchd/com.trade-analysis.skill-generation-weekly.plist` | 週次マイニングスケジュール（土曜06:00） |
| `launchd/com.trade-analysis.skill-generation-daily.plist` | 日次生成スケジュール（07:00） |
| `skills/skill-idea-miner/` | マイニング＆スコアリングスキル |
| `skills/skill-designer/` | スキル設計プロンプトビルダー |
| `logs/.skill_generation_backlog.yaml` | ステータス追跡付きスコア済みアイデアバックログ |
| `logs/.skill_generation_state.json` | 実行履歴と状態 |
| `reports/skill-generation-log/` | 日次生成サマリーレポート |
