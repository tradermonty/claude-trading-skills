# エッジのインスティチューション化プロセス

日々の「思いつき」を、属人的なメモで終わらせず、再現可能な戦略資産に昇格させるための標準フロー。

## 目的

- 観察 -> 抽象化 -> 戦略化 -> パイプライン検証を分業化する
- 各段階で「進級ゲート」を定義し、品質を揃える
- エッジの生成と劣化監視を同じ運用系に載せる

## 1. 3スキル構成 + パイプライン接続

### 1-1. メインライン

```mermaid
flowchart TD
    A[edge-hint-collector<br/>観察の構造化<br/>output: hints.yaml]
    B[edge-concept-synth<br/>仮説の抽象化<br/>output: edge_concepts.yaml]
    C[edge-strategy-export<br/>戦略化/エクスポート<br/>output: strategy.yaml + metadata.json]
    D[trade-strategy-pipeline<br/>Phase I -> IS Gate -> Walk-Forward<br/>-> OOS Gate -> Robustness -> Paper -> Live]

    A --> B --> C --> D
```

### 1-2. 差し戻しループ（ゲート運用）

```mermaid
flowchart TD
    H0[edge-hint-collector]
    C0[edge-concept-synth]
    S0[edge-strategy-export]
    P0[trade-strategy-pipeline]

    G1{"Concept Gate<br/>メカニズム仮説 + 成立条件 + FMEA<br/>事前登録(評価基準/成功閾値)"}
    G2{"Spec Gate<br/>StrategySpec適合チェック"}
    G3{"Coverage Gate<br/>非対応はresearch-onlyとして保留"}
    G4{"Pipeline Gate<br/>IS/OOS/Robustnessを通過"}

    H0 --> C0
    C0 --> G1
    G1 -->|Fail| H0
    G1 -->|Pass| S0
    S0 --> G2
    G2 -->|Fail| C0
    G2 -->|Pass| G3
    G3 -->|保留| C0
    G3 -->|export対象| P0
    P0 --> G4
    G4 -->|Fail| C0
    G4 -->|Pass| L0[Paper/Liveへ昇格]
```

### 1-3. 実装マッピング（現リポジトリ）

| 論理スキル名 | 現在の実装 |
|---|---|
| edge-hint-collector | `skills/edge-hint-extractor` |
| edge-concept-synth | `skills/edge-concept-synthesizer` |
| edge-strategy-export | `skills/edge-strategy-designer` + `skills/edge-candidate-agent` (`export_candidate.py` / `validate_candidate.py`) |

## 2. エッジの進級ステート（進学モデル）

```mermaid
stateDiagram-v2
    [*] --> Hint
    Hint --> Ticket: 観察根拠あり
    Ticket --> Concept: 複数証拠を抽象化
    Concept --> Draft: ルール化可能
    Draft --> Candidate: v1 I/Fにマップ可能
    Candidate --> Phase1Pass: validate + dry-run pass
    Phase1Pass --> BacktestPass: 期待値/安定性 pass
    BacktestPass --> Paper: 紙運用で再現
    Paper --> LiveSmall: 小ロット実運用
    LiveSmall --> Live: 継続再現
    Live --> Monitor
    Monitor --> Concept: 劣化検知で再設計
    Monitor --> Retired: 有意な劣化が継続
```

## 3. 日次/週次の運用リズム

```mermaid
flowchart TD
    subgraph Daily[Daily Loop]
        D1[観察データ更新] --> D2[hints生成]
        D2 --> D3[自動検出でticket生成]
        D3 --> D4[概念抽象化]
        D4 --> D5[戦略ドラフト更新]
    end

    subgraph Weekly[Weekly Review]
        W1[Concept Review<br/>採択/保留/却下] --> W2[検証キュー優先順位更新]
        W2 --> W3[パイプライン投入計画]
    end

    subgraph Monthly[Monthly Governance]
        M1[劣化監視レビュー] --> M2[現役エッジの継続/縮小/退役]
        M2 --> M3[仮説ライブラリ更新]
    end

    D5 --> W1
    W3 --> M1
```

## 4. 進級ゲートの最小要件

| ゲート | 最小要件 | 失格条件 |
|---|---|---|
| Concept Gate | thesis + invalidation_signals が明示されている | 仮説が観察の言い換えのみ |
| Draft Gate | entry/exit/risk/cost が定義済み | コスト未考慮、実装不能条件 |
| Pipeline Gate | `edge-finder-candidate/v1` 契約を満たす | schema違反、dry-run失敗 |
| Promotion Gate | OOSで再現し、劣化監視可能 | 特定期間のみ有効、容量不足 |

## 5. まず見るべきポイント

1. `edge_concepts.yaml` の `abstraction.thesis` と `invalidation_signals`
2. `strategy_drafts/*.yaml` の `risk` と `validation_plan`
3. `validate_candidate.py` 結果（I/F適合）
4. パイプライン結果の再現性（期間分割・レジーム分割）
