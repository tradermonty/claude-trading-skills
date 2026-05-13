# Claude Trading Skills プロジェクトビジョン

Version: 0.1
Last updated: 2026-05-03

English version: [PROJECT_VISION.md](PROJECT_VISION.md)

Claude Trading Skills は、時間制約のある個人投資家が、長期投資を土台にしながら、相場環境に応じて規律あるスイングトレードを行い、リスク管理と記録・振り返りを通じて継続的に成長するための Claude Skills ベースの意思決定プロセスOSです。

## 1. マントラ

**Empower solo traders, growing together.**

このプロジェクトは、個人トレーダーが孤独な裁量判断だけに頼るのではなく、再現可能なプロセス、明確なリスク管理、記録と振り返り、継続的な改善ループを持てるようにするための Claude Skills プロジェクトです。

ここでいう **solo** は、孤立を意味しません。個人で判断し、個人でリスクを取るトレーダーを対象にしながらも、ワークフロー、レビュー、改善知見は共有された実践から成長していくことを目指します。

## 2. 重要な注意と免責

このリポジトリは、教育、研究、プロセス改善を目的とした Claude Skills と関連資料を提供するものです。金融助言、投資顧問、売買シグナル配信、ブローカー注文執行、税務・法務助言を提供するものではありません。

投資・トレードには元本損失を含むリスクがあります。過去のデータ、バックテスト、スクリーニング結果、サンプルレポート、AI が生成した分析は、将来の成果を保証しません。最終的な売買判断、ポジションサイズ、リスク管理、税務・規制遵守、ブローカー利用判断は、すべてユーザー自身の責任です。

このプロジェクトは MIT License で提供されます。ソフトウェアと資料は、ライセンスに記載された通り **"AS IS, WITHOUT WARRANTY"**、つまり明示・黙示を問わず保証なしで提供されます。

## 3. プロジェクトの原点と公開する理由

このプロジェクトは、作者自身が AI を使って自分のトレードプロセスを一段引き上げたいと考えたことから始まりました。

個人トレーダー、特に本業や生活を持ちながら投資とトレードに取り組む人にとって、時間、情報量、感情管理、リスク管理は大きな制約になります。Claude Trading Skills は、そうした制約の中でも、市場確認、候補銘柄の抽出、トレード計画、リスク管理、記録、振り返りを継続しやすくするために作られました。

このプロジェクトは、まず作者自身が毎日・毎週使うための実践的な道具として育てます。自分のトレードを一段引き上げ、退場しにくい判断プロセスを作り、記録から学び続けるためです。同時に、同じような制約や悩みを持つ人にとって少しでも役に立つ可能性があると考えているため、オープンソースとして公開しています。

この立ち位置は、**first for self, open for others** です。最初の利用者は作者自身であり、外からの反応が少ない時期でも、自分が本当に使う道具として改善し続けます。そのうえで、ワークフロー、レビュー、改善知見が共有され、個人トレーダーの実践知が少しずつ積み上がっていく状態を目指します。

Claude Trading Skills は、完成された勝ち方を配るものではありません。作者自身もまだ学び続けている一人の個人トレーダーです。このリポジトリは「答え」を渡す場所ではなく、個人トレーダーが判断力を鍛え、リスクを管理し、記録から学び、少しずつ成長していくための有用な仕組みを共有する場所です。

## 4. 中心となる考え方

このプロジェクトの目的は、市場を誰よりもうまく予測することではありません。

目的は、個人トレーダーがより構造化され、リスクを意識し、振り返り可能で、改善可能な判断をできるようにすることです。

このプロジェクトの中心にあるのは、次のような流れではありません。

```text
Ask -> Signal -> Trade
```

中心にあるのは、次の学習ループです。

```text
Plan -> Trade -> Record -> Review -> Improve
```

Claude Trading Skills は、売買シグナルを出すエンジンではありません。個人トレーダーが AI を使って退場しにくい判断プロセスを作り、自分の判断、リスク、記録、改善を一貫して運用するための **意思決定プロセスOS** を目指します。

## 5. このプロジェクトの目的

Claude Trading Skills は、米国株・ETF・配当投資・スイングトレード・マクロ分析・戦略研究を中心に、必要に応じてオプションやイベント戦略も扱う Claude 用スキルを集めたリポジトリです。

各スキルは、以下のような意思決定を支援します。

- 市場環境を把握する
- 銘柄候補をスクリーニングする
- トレードプランを作る
- ポジションサイズを計算する
- ポートフォリオリスクを確認する
- トレード仮説を記録する
- 結果を振り返り、改善点を見つける
- 新しい戦略アイデアを検証する

このプロジェクトが目指すのは、単なる「便利な分析ツール集」ではなく、個人トレーダーのための **意思決定支援システム** です。

特に、長期投資を土台にしながら、限られた時間で相場環境に応じたスイングトレードを行いたい個人投資家が、判断を効率化し、リスクを取りすぎず、記録から改善できる状態を目指します。

## 6. このプロジェクトであるもの / ないもの

| このプロジェクトであるもの | このプロジェクトではないもの |
| --- | --- |
| 意思決定支援システム | 金融助言・投資顧問 |
| トレードワークフローの道具箱 | 売買シグナル配信サービス |
| リスク管理と振り返りのフレームワーク | 利益保証システム |
| Claude Skills のリポジトリ | ブローカー注文執行プラットフォーム |
| トレーダーの学習ループを支える仕組み | 完全自動売買ボット |

このプロジェクトは、トレーダーの判断を置き換えるものではありません。トレーダーの判断プロセスを明確にし、再現可能にし、振り返り可能にし、改善可能にするための仕組みです。

最終判断とリスク責任は常にユーザー側にあります。免責の詳細は「重要な注意と免責」に集約し、この立ち位置は今後プロジェクトが大きくなっても変えない前提です。

## 7. 対象ユーザー

このプロジェクトが中心に置くのは、**兼業または時間制約のある個人投資家・スイングトレーダー** です。

具体的には、長期投資や配当投資を資産形成の土台にしつつ、相場環境が整ったときに短中期のスイングトレードで追加リターンを狙う人を想定します。本業や生活があり、投資に使える時間は限られているため、毎日の判断を効率化し、リスク管理と記録を仕組み化したいというニーズを持っています。

### Primary Users

最初に最も重視するユーザーは以下です。

| ペルソナ | 主な目的 | 必要な導線 |
| --- | --- | --- |
| 兼業スイングトレーダー | 毎日の相場確認、候補選定、トレード計画 | `market-regime-daily` / `swing-opportunity-daily` |
| リスク管理を強化したい成長株投資家 | 攻める相場と守る相場を分けたい | `market-regime` / `exposure` workflow |
| 配当・長期投資家 | 配当株の発掘、保有株の点検、ポートフォリオ確認 | `core-portfolio` / `dividend-income` |

### Secondary / Advanced Users

拡張対象として、以下のユーザーも想定します。

| ペルソナ | 主な目的 | 必要な導線 |
| --- | --- | --- |
| イベント・決算トレーダー | 決算、ニュース、経済イベント後の機会を探したい | `advanced-satellite` / `earnings-event` |
| ショート戦略トレーダー | risk-off 環境で弱い銘柄や過熱銘柄を監視したい | `advanced-satellite` / `risk-off-short` |
| 戦略研究者・開発者 | 仮説を検証し、戦略を改善したい | `strategy-research` |
| 上級者 | 独自 workflow、YAML manifest、CLI を拡張したい | manifests / scripts / API matrix |

一方で、以下のユーザーを主対象にはしません。

- 完全自動売買を期待している人
- 利益保証や売買シグナルの丸投げを求める人
- リスク管理や記録をしたくない人
- 短期スキャルピングだけを主目的にする人

## 8. Core + Satellite の運用思想

このプロジェクトの主対象ユーザーは、以下のような **Core + Satellite** の構造で投資とトレードを行う人です。

- **Core**: 長期投資、配当株、ETF、ポートフォリオ管理
- **Satellite**: スイングトレード、テーマ株、ブレイクアウト、決算後モメンタム
- **Advanced Satellite**: 必要に応じたショート戦略、イベント戦略、オプション戦略
- **Shared Layer**: 市場環境、リスク管理、ポジションサイズ、記録、振り返り

重要なのは、Core と Satellite の目的、時間軸、リスクを混ぜないことです。

このプロジェクトは、個人投資家が長期資産形成を土台にしながら、相場環境が整ったときだけ規律ある短中期トレードで追加リターンを狙うための運用プロセスを提供します。

Advanced Satellite は、主導線よりも高いリスク、複雑な前提、または実行上の確認事項を伴う領域です。たとえばショート戦略、イベント戦略、オプション戦略は、十分な経験、明確な損失上限、手動確認、必要APIやブローカー制約の理解、事前検証済み workflow がある場合にのみ扱います。実装量が大きいスキルであっても、主対象ユーザーに最初に勧める導線とは限りません。

## 9. 現在地

このリポジトリには、すでに多数のスキルがあります。大きく分けると、以下の領域をカバーしています。

- **市場分析**: 市場環境、ブレッド、セクター、マクロ、ニュース、バブルリスク
- **スクリーニング**: CANSLIM、VCP、配当株、決算後モメンタム、テーマ、機関投資家フロー
- **トレード計画**: ブレイクアウト、Parabolic Short、ポジションサイズ、エクスポージャー管理
- **ポートフォリオと記録**: ポートフォリオ管理、仮説管理、トレード記録、ポストモーテム
- **戦略研究**: バックテスト、戦略アイデア生成、エッジ研究パイプライン
- **品質管理とメタスキル**: スキル設計、レビュー、統合テスト、改善ループ

個別スキルはかなり充実してきました。一方で、ユーザー目線では次の課題が残っています。

- どのスキルを使えばよいかわかりにくい
- 複数スキルの使い順が見えにくい
- トレード前後の一連のワークフローが整理されていない
- GitHub や `.skill` ファイルに慣れていない人には入口が難しい
- スキルを使った結果を、継続的な学習ループに接続しきれていない

次の段階では、スキルを増やすことよりも、**使える形に束ねること**、**ユーザーに合わせて案内すること**、**運用ワークフローとして定着させること**が重要になります。

## 10. 戦略的方向性: スキル集から運用OSへ

このプロジェクトの次の方向性は、以下の一文で表せます。

> スキル集から、個人トレーダーのための運用OSへ。

ここでいう運用OSとは、個人トレーダーが日次・週次の投資判断を行うために必要な、市場確認、リスク予算、戦略選択、候補生成、トレード計画、手動実行確認、記録、振り返り、改善をつなぐ一連の仕組みです。

この運用OSが目指すのは、個人トレーダーが簡単に勝てるようになることではありません。限られた時間の中でも、退場せず、リスクを管理し、記録から学び、自分の判断プロセスを少しずつ改善できる状態を作ることです。

理想的な体験は次のようなものです。

1. ユーザーが「自分はこういうトレードをしたい」と自然言語で伝える
2. システムが、その人の目的、経験、時間、リスク許容度、API環境を理解する
3. 適したスキルセットとワークフローを提案する
4. ユーザーが市場環境、リスク、候補銘柄、トレードプランを順番に確認できる
5. トレード後に仮説と結果を記録し、次回の改善につなげる

この流れが実現できれば、GitHub やツール設定に詳しくないユーザーでも、段階的にこのプロジェクトの価値にアクセスできます。

## 11. プロジェクト構造

今後は、以下の階層でプロジェクトを整理します。

```text
1. Individual Skills
    ↓
2. Skill Inventory / API Matrix
    ↓
3. Skillsets
    ↓
4. Workflows
    ↓
5. Trading Skills Navigator
    ↓
6. User Entry Points
    ↓
7. Journal / Postmortem / Learning Loop
```

各レイヤーの役割は次の通りです。

| レイヤー | 役割 |
| --- | --- |
| Skills | 小さな専門機能。個別の分析、計算、計画、記録を担当する |
| Skill Inventory / API Matrix | スキルの用途、必要API、難易度、入出力を整理する単一の情報源 |
| Skillsets | 目的別のスキル束。どのスキルを組み合わせるかを定義する |
| Workflows | 実運用の順番、判断ゲート、成果物の受け渡しを定義する |
| Navigator | ユーザーの目的に合う skillset / workflow を提案する案内役 |
| User Entry Points | docs、starter prompts、CLI、将来の Web UI など、使い始める入口 |
| Learning Loop | 記録、振り返り、改善を通じてスキルとトレーダーの両方を育てる仕組み |

この構造により、スキル本体、ドキュメント、推薦ロジック、ワークフローの情報が分散しすぎないようにします。Navigator は対話的にユーザーへ適した導線を提案し、User Entry Points は静的ドキュメント、starter prompts、CLI、将来の Web UI として入口を提供します。

## 12. ロードマップ

### Phase 0: Vision and Metadata — ✅ 一部完了 (2026-05-09)

> **状況:** PR #84 で `skills-index.yaml` を SSoT として導入。54 スキル全件に id / display_name / category / status / summary / integrations[] を付与。timeframe / difficulty の補完は後続タスク。

まず、既存スキル群を整理し、プロジェクト全体を説明しやすくします。

主な作業:

- プロジェクトビジョンとロードマップを明文化する
- `skills-index.yaml` または `skills-inventory.yaml` を作成する
- スキル一覧、カテゴリ、API要件を最新化する
- 各スキルの用途、時間軸、難易度、必要APIを構造化する
- 古い説明や重複表現を整理する

完了条件:

- `PROJECT_VISION.md` と `PROJECT_VISION.ja.md` が存在する
- `skills-index.yaml` または `skills-inventory.yaml` が存在する
- 全スキルに category、use case、required API、difficulty、timeframe の初期分類がある
- API requirements matrix が最新化されている
- docs のスキル数、カテゴリ、説明が現状と矛盾していない

### Phase 1: Trading Skills Navigator v0

このリポジトリの案内係となるメタスキルを作ります。

ユーザーが「こんなことをしたい」と聞くと、Navigator が適切なスキル、組み合わせ、導入方法、ワークフローを案内します。

Phase 1 の責任範囲は、AI による対話的推薦です。ユーザーの目的、経験、時間、API環境に応じて、どの skillset / workflow から始めるべきかを会話の中で案内します。

想定される質問:

- 「長期投資をしながら、相場が良いときだけスイングしたい」
- 「毎朝15分で、今日は攻めてよい相場か知りたい」
- 「長期保有と短期トレードのリスクを分けたい」
- 「今週の保有株と配当株候補を確認したい」
- 「スイングトレードをしたい」
- 「配当株を探したい」
- 「空売り戦略を使いたい」
- 「APIキーなしで使えるものを知りたい」
- 「初心者向けの始め方を知りたい」

完了条件:

- `skills/trading-skills-navigator/` が存在する
- 代表的なユーザー質問 10 件に対して、推奨 skillset と workflow を返せる
- APIキーあり / なしの導線を分けて案内できる
- Claude Web App と Claude Code の導入手順を説明できる

### Phase 2: Skillsets

目的別にスキルを束ねる manifest を作ります。

初期候補:

- `core-portfolio`
- `market-regime`
- `swing-opportunity`
- `trade-memory-loop`
- `dividend-income`
- `strategy-research`
- `advanced-satellite`

`advanced-satellite` には、risk-off short、earnings event、options、thematic momentum など、主導線よりも上級者向けの戦略を含めます。

完了条件:

- 主要 7 skillset の YAML manifest が存在する
- 各 skillset に required / recommended / optional skills が定義されている
- 対象ユーザー、時間軸、必要API、使わない方がよい条件が書かれている
- Navigator が skillset manifest を参照して推薦できる

### Phase 3: Workflows — ✅ 一部完了 (2026-05-09)

> **状況:** PR #85 で 5 本の Core + Satellite manifest（`core-portfolio-weekly` / `market-regime-daily` / `swing-opportunity-daily` / `trade-memory-loop` / `monthly-performance-review`）を `workflows/` に追加し、`--strict-workflows` で検証。Advanced 系 (`risk-off-short-daily` / `earnings-weekly` / `strategy-research-pipeline`) は後続。

Skillset だけでは実運用には足りません。実際のトレードでは、順番、判断ゲート、成果物の受け渡しが必要です。

典型的なワークフロー:

1. **Market Context**: 市場環境を確認する
2. **Risk Budget**: 取るリスク量を決める
3. **Strategy Selection**: 今日使う戦略を選ぶ
4. **Candidate Generation**: 候補銘柄を探す
5. **Trade Planning**: entry / stop / target / size を決める
6. **Manual Execution Gate**: 実注文前の確認をする
7. **Monitoring**: トリガーや無効化を監視する
8. **Journal / Postmortem**: 記録し、振り返る

初期候補:

- `core-portfolio-weekly`
- `market-regime-daily`
- `swing-opportunity-daily`
- `trade-memory-loop`
- `monthly-performance-review`

Advanced workflow 候補:

- `risk-off-short-daily`
- `earnings-weekly`
- `macro-morning-brief`
- `strategy-research-pipeline`

完了条件:

- 少なくとも 3 つの実運用 workflow が YAML で定義されている
- 各 workflow に入力、出力、判断ゲート、利用スキル、手動確認項目がある
- 兼業トレーダーが 15〜60 分で実行できる日次 / 週次導線がある
- 各 trade workflow が journal entry または postmortem への接続を持つ
- 1 つ以上の workflow がサンプルデータで end-to-end に説明できる

### Phase 4: ユーザーにやさしい入口

GitHub や `.skill` ファイルに慣れていないユーザー向けに、入口を簡単にします。

Phase 4 の責任範囲は、静的な入口と配布導線です。ドキュメント、quickstart、starter prompts、CLI、将来の Web UI など、Navigator がなくても初見ユーザーが始められる導線を整えます。

候補:

- Core + Satellite quickstart
- "Find Your Workflow" ドキュメント
- 15-minute daily routine
- 60-minute weekly review
- starter prompts
- skill download checklist
- API setup guide
- `scripts/recommend_skills.py`
- static recommender page

完了条件:

- 初見ユーザーが 5 分以内に自分の開始ルートを選べる
- APIキーなしで始めるルートと、FMP / Alpaca を使うルートが分かれている
- Claude Web App にどの `.skill` をアップロードすべきか分かる
- 最初に Claude に貼る starter prompt が用意されている

### Phase 5: Learning Loop

トレード結果を記録し、改善につなげる仕組みを強化します。

目指すループ:

```text
Plan -> Trade -> Record -> Review -> Improve -> Adjust Workflow
```

関連スキル:

- `trader-memory-core`
- `signal-postmortem`
- `backtest-expert`
- `edge-signal-aggregator`
- `skill-integration-tester`
- `dual-axis-skill-reviewer`

完了条件:

- Plan -> Trade -> Record -> Review -> Improve のサンプル運用例が 1 つ以上ある
- trade journal template と postmortem template が用意されている
- どのスキル由来のシグナルが機能したか記録できる
- 失敗事例を workflow や skillset の改善につなげる導線がある

## 13. 成功指標

このプロジェクトの成功は、利益率や的中率だけでは測りません。測るべき対象は、プロセスが実際に使われ、改善され、継続できているかです。

初期の観測指標:

- 作者自身が、`market-regime-daily`、`core-portfolio-weekly`、`trade-memory-loop` のいずれかを 3 か月以上継続利用している
- 少なくとも 3 つの workflow が、入力、出力、判断ゲート、記録先を持つ YAML または Markdown として定義されている
- 主要スキルの 80% 以上が `skills-index.yaml` または `skills-inventory.yaml` に登録され、category、use case、required API、difficulty、timeframe を持つ
- Trading Skills Navigator v0 が、代表的なユーザー質問 10 件に対して、人間レビューで妥当な skillset / workflow を返せる
- `core-portfolio`、`market-regime`、`swing-opportunity`、`trade-memory-loop` で使う primary-path skills の 80% 以上が初期品質ゲートを通過している
- 少なくとも 1 つの Plan -> Trade -> Record -> Review -> Improve のサンプル運用例が、公開ドキュメントとして追跡可能になっている

将来的な外部指標:

- GitHub issue、PR、discussion、X などを通じて、実際の利用者から workflow 改善フィードバックが届いている
- 初見ユーザーが、README または quickstart から 5 分以内に開始ルートを選べる
- APIキーなしの導線と、FMP / Alpaca 等を使う導線の両方が実際に動作確認されている

## 14. 設計原則

今後の開発では、以下の原則を重視します。

1. **予測よりプロセス**
   - 予測そのものより、再現可能な判断プロセスを重視する。

2. **リスクを先に見る**
   - 候補銘柄やシグナルより先に、相場環境とリスク予算を確認する。

3. **人間の判断を中心に置く**
   - 自動売買ではなく、人間の判断を強くするための補助に徹する。

4. **理由を説明できること**
   - なぜそのスキル、ワークフロー、リスク設定を推奨したのか説明できるようにする。

5. **小さなスキルを組み合わせる**
   - 大きな万能スキルより、小さく焦点の合ったスキルを組み合わせる。

6. **初心者には入口を、上級者には拡張性を**
   - GitHub に慣れていない人でも入れる導線を作りつつ、深く使いたい人には拡張可能な構造を残す。

7. **記録し、改善する**
   - トレードは実行して終わりではなく、記録と振り返りで改善する。

8. **単一の情報源を保つ**
   - スキルのメタデータは、できる限り単一の情報源に集約する。カタログ、API要件表、Navigator の推薦、workflow manifest は、共通のメタデータから生成または検証できる状態を目指す。

## 15. 短期優先事項

短期的には、以下の順番で進めます。

- ✅ **完了 (2026-05-09)**: プロジェクトビジョン文書（`PROJECT_VISION.md` / `PROJECT_VISION.ja.md`）
- ✅ **完了 (2026-05-09)**: `skills-index.yaml` SSoT + validator (PR #84)
- ✅ **完了 (2026-05-09)**: 5 本の Core ワークフロー manifest を `workflows/` に追加 (PR #85)
- ✅ **完了 (2026-05-09)**: ワークフロー doc ページの自動生成 (PR #86)
- **Now**: 54 スキル全件の `timeframe` / `difficulty` を埋める（`--strict-metadata` 解禁条件）
- **Next**: Trading Skills Navigator を作る
- **Next**: 主要 skillsets を YAML で定義する
- **Next**: Advanced ワークフロー manifest（`risk-off-short-daily` / `earnings-weekly` / `strategy-research-pipeline`）を追加
- **Next**: "Find Your Workflow" ドキュメントを作る
- **Later**: 必要に応じて bundle builder や recommender CLI を作る
- **Later**: Web アプリ POC を検討する

最初から Web アプリや bundle ZIP に進むより、まずは構造化された知識と案内役を作る方が安全です。

## 16. コミュニティと運営方針

このプロジェクトは MIT License で公開します。Issue や PR は歓迎しますが、金融助言、個別売買推奨、利益保証に関する依頼は扱いません。

歓迎する貢献:

- workflow recipe の改善
- skill metadata や API 要件の修正
- ドキュメント、starter prompt、quickstart の改善
- テスト、fixture、runbook の追加
- 実運用で見つかった落とし穴や改善案の共有

当面の連絡・議論の場所は GitHub Issues / Pull Requests とします。コミュニティを急いで大きくするより、作者自身が使い続けられる品質を保ち、実際の利用から出てきた改善を積み上げることを優先します。

## 17. 長期ビジョン

長期的には、このプロジェクトを以下のような存在に育てます。

- 個人トレーダーが自分に合った戦略とワークフローを見つけられる
- 市場環境に応じてリスクを調整できる
- トレード前に明確なプランを作れる
- トレード後に結果を記録し、失敗から学べる
- スキルやワークフローが実践から改善される
- 初心者でも入りやすく、上級者でも深く使える

将来的には、ユーザーが自分の workflow recipe、postmortem template、strategy research note、skill improvement proposal を共有できるようにし、個人トレーダーの実践知がプロジェクト全体の改善につながる状態を目指します。

このプロジェクトの本質は、トレーダーに「答え」を渡すことではありません。

トレーダーが自分の判断を鍛え、リスクを管理し、記録から学び、継続的に成長できる環境を作ることです。

**Empower solo traders, growing together.**
