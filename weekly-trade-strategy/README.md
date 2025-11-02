# Weekly Trade Strategy Blog Generator

米国株の週間トレード戦略ブログを自動生成するAIエージェントシステム

[English](#english) | [日本語](#japanese)

---

## <a name="japanese"></a>日本語

### 概要

このプロジェクトは、Claude Agentsを活用して、米国株市場の週間トレード戦略ブログを自動生成するシステムです。チャート分析、市場環境評価、ニュース分析を段階的に実行し、兼業トレーダー向けの実践的な戦略レポートを生成します。

### 主な機能

- **テクニカル分析**: VIX、金利、Breadth指標、主要指数、コモディティの週足チャート分析
- **市場環境評価**: バブルリスク検出、センチメント分析、セクターローテーション分析
- **ニュース・イベント分析**: 過去10日間のニュース影響評価、今後7日間の経済指標・決算予測
- **週間戦略ブログ生成**: 3つの分析レポートを統合し、実践的なトレード戦略を200-300行のMarkdown形式で出力
- **中長期戦略レポート**（オプション）: Druckenmiller流の18ヶ月投資戦略を4シナリオ（Base/Bull/Bear/Tail Risk）で生成

### 前提条件

- **Claude Code CLI** または **Claude Desktop**
- 以下のClaudeスキルが利用可能であること：
  - `technical-analyst`
  - `breadth-chart-analyst`
  - `sector-analyst`
  - `market-environment-analysis`
  - `us-market-bubble-detector`
  - `market-news-analyst`
  - `economic-calendar-fetcher`
  - `earnings-calendar`
  - `stanley-druckenmiller-investment`（中長期戦略用）

### セットアップ

1. **リポジトリのクローン**

```bash
git clone <repository-url>
cd weekly-trade-strategy
```

2. **環境変数の設定**

`.env`ファイルを作成し、必要なAPI キーを設定：

```bash
# Financial Modeling Prep API (決算・経済カレンダー取得用)
FMP_API_KEY=your_api_key_here
```

3. **フォルダ構造の確認**

```
weekly-trade-strategy/
├── charts/              # チャート画像格納フォルダ
├── reports/             # 分析レポート格納フォルダ
├── blogs/               # 最終ブログ記事格納フォルダ
├── skills/              # Claudeスキル定義
└── .claude/
    └── agents/          # Claudeエージェント定義
```

### 使い方

#### クイックスタート

1. **チャート画像を準備** (推奨18枚)

```bash
# 日付フォルダを作成
mkdir -p charts/2025-11-03

# チャート画像を配置（以下の画像を推奨）
# - VIX (週足)
# - 米10年債利回り (週足)
# - S&P 500 Breadth Index
# - Nasdaq 100, S&P 500, Russell 2000, Dow (週足)
# - 金、銅、原油、天然ガス、ウラン (週足)
# - Uptrend Stock Ratio
# - セクター・インダストリーパフォーマンス
# - 決算カレンダー、ヒートマップ
```

2. **レポートフォルダを作成**

```bash
mkdir -p reports/2025-11-03
```

3. **一括実行プロンプト** (Claude Code/Desktop で実行)

```
2025-11-03週のトレード戦略ブログを作成してください。

1. technical-market-analystでcharts/2025-11-03/の全チャートを分析
   → reports/2025-11-03/technical-market-analysis.md

2. us-market-analystで市場環境を総合評価
   → reports/2025-11-03/us-market-analysis.md

3. market-news-analyzerでニュース/イベント分析
   → reports/2025-11-03/market-news-analysis.md

4. weekly-trade-blog-writerで最終ブログ記事を生成
   → blogs/2025-11-03-weekly-strategy.md

各ステップを順次実行し、レポートを確認してから次に進んでください。
```

4. **オプション: 中長期戦略レポート生成**

週間ブログとは別に、18ヶ月の中長期投資戦略レポートを生成できます（四半期ごと推奨）。

```
druckenmiller-strategy-plannerエージェントで2025年11月3日時点の18ヶ月戦略を策定してください。

reports/2025-11-03/配下の3つのレポートを総合的に分析し、
Druckenmiller流の戦略フレームワークを適用して、
reports/2025-11-03/druckenmiller-strategy.mdに保存してください。
```

**特徴**:
- 18ヶ月先行の中長期マクロ分析
- 4つのシナリオ（Base/Bull/Bear/Tail Risk）と確率評価
- 確信度に基づくポジションサイジング推奨
- マクロ転換点（金融政策、景気サイクル）の識別
- 各シナリオの無効化条件を明示

#### ステップ別実行

より詳細な手順は `CLAUDE.md` を参照してください。

### プロジェクト構造

```
weekly-trade-strategy/
│
├── charts/                          # チャート画像
│   └── YYYY-MM-DD/
│       ├── vix.jpeg
│       ├── 10year_yield.jpeg
│       └── ...
│
├── reports/                         # 分析レポート
│   └── YYYY-MM-DD/
│       ├── technical-market-analysis.md
│       ├── us-market-analysis.md
│       ├── market-news-analysis.md
│       └── druckenmiller-strategy.md  # (オプション: 中長期戦略)
│
├── blogs/                           # 最終ブログ記事
│   └── YYYY-MM-DD-weekly-strategy.md
│
├── skills/                          # Claudeスキル定義
│   ├── technical-analyst/
│   ├── breadth-chart-analyst/
│   ├── sector-analyst/
│   ├── market-news-analyst/
│   ├── us-market-bubble-detector/
│   └── ...
│
├── .claude/
│   └── agents/                      # Claudeエージェント定義
│       ├── technical-market-analyst.md
│       ├── us-market-analyst.md
│       ├── market-news-analyzer.md
│       ├── weekly-trade-blog-writer.md
│       └── druckenmiller-strategy-planner.md  # (オプション: 中長期戦略)
│
├── CLAUDE.md                        # 詳細な実行手順ガイド
├── README.md                        # このファイル
├── .env                             # 環境変数 (要作成)
└── .gitignore
```

### エージェント一覧

| エージェント | 役割 | 出力 |
|---------|------|------|
| `technical-market-analyst` | チャート画像からテクニカル分析を実行 | `technical-market-analysis.md` |
| `us-market-analyst` | 市場環境とバブルリスクを評価 | `us-market-analysis.md` |
| `market-news-analyzer` | ニュース影響とイベント予測を分析 | `market-news-analysis.md` |
| `weekly-trade-blog-writer` | 3つのレポートを統合してブログ記事を生成 | `YYYY-MM-DD-weekly-strategy.md` |
| `druckenmiller-strategy-planner`（オプション） | 中長期（18ヶ月）戦略プランニング（4シナリオ分析） | `druckenmiller-strategy.md` |

### トラブルシューティング

**Q: エージェントがチャートを見つけられない**
- `charts/YYYY-MM-DD/` フォルダが存在するか確認
- 画像形式が `.jpeg` または `.png` であることを確認

**Q: レポートが生成されない**
- `reports/YYYY-MM-DD/` フォルダが作成されているか確認
- 前のステップのレポートが正常に生成されているか確認

**Q: ブログ記事のセクター配分が急変している**
- 前週のブログ記事が `blogs/` ディレクトリに存在するか確認
- エージェントは段階的調整（±10-15%）を行うよう設計されています

**Q: FMP APIエラーが発生する**
- `.env` ファイルに `FMP_API_KEY` が正しく設定されているか確認
- APIキーの有効性を確認（[Financial Modeling Prep](https://site.financialmodelingprep.com/)）

### ライセンス

このプロジェクトはMITライセンスの下で公開されています。

### 貢献

プルリクエストを歓迎します。大きな変更の場合は、まずissueを開いて変更内容を議論してください。

---

## <a name="english"></a>English

### Overview

An AI agent system that automatically generates weekly trading strategy blog posts for US stock markets using Claude Agents. The system performs step-by-step chart analysis, market environment evaluation, and news analysis to produce actionable strategy reports for part-time traders.

### Key Features

- **Technical Analysis**: Weekly chart analysis of VIX, yields, breadth indicators, major indices, and commodities
- **Market Environment Assessment**: Bubble risk detection, sentiment analysis, sector rotation analysis
- **News & Event Analysis**: Past 10 days news impact evaluation, upcoming 7 days economic indicators and earnings forecasts
- **Weekly Strategy Blog Generation**: Integrates three analysis reports into a 200-300 line Markdown format trading strategy
- **Medium-Term Strategy Report** (Optional): 18-month Druckenmiller-style investment strategy with 4 scenarios (Base/Bull/Bear/Tail Risk)

### Prerequisites

- **Claude Code CLI** or **Claude Desktop**
- The following Claude skills must be available:
  - `technical-analyst`
  - `breadth-chart-analyst`
  - `sector-analyst`
  - `market-environment-analysis`
  - `us-market-bubble-detector`
  - `market-news-analyst`
  - `economic-calendar-fetcher`
  - `earnings-calendar`
  - `stanley-druckenmiller-investment` (for medium-term strategy)

### Quick Start

1. Clone the repository
2. Create `.env` file with your `FMP_API_KEY`
3. Create date folders: `mkdir -p charts/2025-11-03 reports/2025-11-03`
4. Place chart images in `charts/2025-11-03/`
5. Run the complete workflow via Claude Code/Desktop (see Japanese section for detailed prompt)

### Project Structure

See the Japanese section above for detailed structure.

### Agents

- **technical-market-analyst**: Chart-based technical analysis
- **us-market-analyst**: Market environment and bubble risk evaluation
- **market-news-analyzer**: News impact and event forecasting
- **weekly-trade-blog-writer**: Final blog post generation
- **druckenmiller-strategy-planner** (Optional): Medium-term (18-month) strategy planning with 4-scenario analysis

### Documentation

For detailed workflow instructions, see `CLAUDE.md`.

### License

This project is licensed under the MIT License.

### Contributing

Pull requests are welcome. For major changes, please open an issue first to discuss what you would like to change.

---

## Acknowledgments

This project leverages Claude's advanced AI capabilities for financial market analysis. All trading strategies generated are for educational purposes only and should not be considered as financial advice.

---

**Version**: 1.0
**Last Updated**: 2025-11-02
