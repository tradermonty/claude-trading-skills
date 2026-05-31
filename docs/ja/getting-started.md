---
layout: default
title: はじめに
parent: 日本語
nav_order: 1
lang_peer: /en/getting-started/
permalink: /ja/getting-started/
---

# はじめに
{: .no_toc }

Claude Trading Skillsのインストール方法、APIキーの設定、最初のスキル実行までをガイドします。
{: .fs-6 .fw-300 }

<details open markdown="block">
  <summary>目次</summary>
  {: .text-delta }
- TOC
{:toc}
</details>

---

## 必要なもの

| 項目 | 必須/任意 | 説明 |
|------|-----------|------|
| Claudeアカウント | 必須 | Pro / Team / Enterprise プラン（Skills機能が利用可能なプラン） |
| Python 3.9+ | 必須 | スクリプト実行用。多くのスキルが Python ヘルパーを使用 |
| FMP APIキー | 任意 | Financial Modeling Prep API。一部スキルで必須（無料ティアあり） |
| FINVIZ Elite | 任意 | 配当スクリーナーの高速化、Theme Detectorの精度向上に推奨 |
| Alpacaアカウント | 任意 | Portfolio Managerスキルで保有データ取得に必要 |

---

## インストール方法

### Claude Web Appで使う場合

1. `skill-packages/` ディレクトリから使いたいスキルの `.skill` ファイル（ZIP形式）をダウンロードします。
2. ブラウザでClaudeを開き、**Settings → Skills** に進みます。
3. ダウンロードした `.skill` ファイルをアップロードします。
4. 新しい会話でスキルが自動的に有効になります。

> 詳しくは Anthropic の [Skills ローンチ記事](https://www.anthropic.com/news/skills) を参照してください。
{: .note }

### Claude Code（デスクトップ / CLI）で使う場合

```bash
# 1. リポジトリをクローン
git clone https://github.com/tradermonty/claude-trading-skills.git

# 2. 使いたいスキルフォルダをClaude CodeのSkillsディレクトリにコピー
#    （Claude Code → Settings → Skills → Open Skills Folder でパスを確認）
cp -r claude-trading-skills/skills/finviz-screener /path/to/skills-directory/

# 3. Claude Codeを再起動またはリロード
```

> `.skill` パッケージはソースフォルダから生成しますが、テストとローカルビルド成果物は除外します。カスタマイズしたい場合はソースフォルダを編集し、配布前に `python3 scripts/package_skills.py --skill <skill-name>` を実行してください。
{: .tip }

---

## APIキーの設定

### Financial Modeling Prep (FMP)

多くのスクリーニングスキルで使用するファンダメンタルデータAPIです。

| プラン | 料金 | API コール上限 | 対象 |
|--------|------|---------------|------|
| Free | 無料 | 250回/日 | 少数銘柄のスクリーニングに十分 |
| Starter | $29.99/月 | 750回/日 | CANSLIM 40銘柄フルスクリーニング |
| Professional | $79.99/月 | 2,000回/日 | 大規模スクリーニング、複数スキル併用 |

**登録:** [https://site.financialmodelingprep.com/developer/docs](https://site.financialmodelingprep.com/developer/docs)

```bash
# 環境変数で設定（推奨）
export FMP_API_KEY=your_key_here

# または、スクリプト実行時に引数で指定
python3 scripts/screen_canslim.py --api-key YOUR_KEY
```

### FINVIZ Elite

配当スクリーナーの高速化（実行時間 70-80% 短縮）や Theme Detector の精度向上に利用します。

| プラン | 料金 | 備考 |
|--------|------|------|
| Elite月払い | $39.50/月 | リアルタイムデータ、高速API |
| Elite年払い | $299.50/年（約$24.96/月） | 年間割引あり |

**登録:** [https://elite.finviz.com/](https://elite.finviz.com/)

```bash
export FINVIZ_API_KEY=your_key_here
```

### Alpaca Trading

Portfolio Manager スキルで保有データの取得とトレード執行に使用します。

| プラン | 料金 | 備考 |
|--------|------|------|
| ペーパートレード | 無料 | シミュレーション環境、全API利用可能 |
| ライブトレード | 無料（手数料なし） | 株式・ETFの売買が可能 |

**登録:** [https://alpaca.markets/](https://alpaca.markets/)

```bash
export ALPACA_API_KEY="your_api_key_id"
export ALPACA_SECRET_KEY="your_secret_key"
export ALPACA_PAPER="true"  # ペーパートレードの場合
```

---

## 最初のスキルを試す - FinViz Screener

FinViz ScreenerはAPIキー不要で最も手軽に試せるスキルです。自然言語でスクリーニング条件を伝えるだけで、FinVizのフィルター付きURLを生成してChromeで開きます。

### 使用例

Claudeに以下のように話しかけてみてください：

```
EPS成長率25%以上で、SMA200の上にある銘柄を探して
```

### Claudeの動作

1. ユーザーの自然言語を解析し、FinVizフィルターコードに変換します
   - `fa_epsqoq_o25` (EPS QoQ成長率 > 25%)
   - `ta_sma200_pa` (SMA200の上)
2. 選択したフィルターを表形式で確認のため提示します
3. 確認後、URLを構築してChromeで結果ページを開きます

### 期待される出力

- Chromeブラウザに FinViz Screener の結果が表示されます
- 条件に合致する銘柄がテーブル形式で一覧表示されます
- Overview / Valuation / Financial / Technical 等のビューを切り替えて詳細を確認できます

> FinViz Screener の詳しい使い方は [FinViz Screener ガイド]({{ '/ja/skills/finviz-screener/' | relative_url }}) をご覧ください。
{: .tip }

---

## トラブルシューティング

### スキルが読み込まれない

| 原因 | 対処 |
|------|------|
| SKILL.md の `name` フィールドがフォルダ名と不一致 | `name` がフォルダ名と完全一致しているか確認 |
| スキルフォルダの配置場所が間違っている | Claude Code の Skills ディレクトリに正しくコピーされているか確認 |
| Claude Code を再起動していない | 新しいスキルの追加後は再起動が必要 |

### APIキーエラー

```
ERROR: FMP API key not found. Set FMP_API_KEY environment variable or use --api-key argument.
```

**対処:**
1. 環境変数が正しく設定されているか確認: `echo $FMP_API_KEY`
2. シェルの設定ファイル（`.zshrc` / `.bashrc`）に `export FMP_API_KEY=...` を追加して再読み込み
3. それでもダメな場合は `--api-key` 引数で直接渡す

### スクリプトエラー（依存パッケージ不足）

```
ModuleNotFoundError: No module named 'requests'
```

**対処:**

```bash
pip install requests beautifulsoup4 lxml pandas numpy yfinance
```

> 必要な依存パッケージはスキルによって異なります。各スキルガイドの「前提条件」セクションを確認してください。
{: .note }

### FMP API レートリミット

```
ERROR: 429 Too Many Requests - Rate limit exceeded
```

**対処:**
1. スクリプトは自動で60秒後にリトライします
2. 無料ティア（250回/日）の上限を超えた場合は、翌日（UTC午前0時）にリセットされます
3. `--max-candidates` パラメータで分析対象を減らすことで使用量を削減できます
4. 頻繁に使う場合は FMP Starter ($29.99/月) へのアップグレードを検討してください
