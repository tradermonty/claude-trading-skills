# Hermes Integration Notes

## Suggested Slash Command: `/post-trade-coach`

Purpose: review a closed or partially closed trade and generate process, risk,
execution, and possible behavior-pattern feedback.

Suggested bundle flow:

```text
trader-memory-core
→ signal-postmortem
→ trade-performance-coach
```

Required output sections:

- Data freshness / source provenance
- Trade summary
- Process adherence
- Risk manager notes
- Execution quality
- Possible behavioral patterns
- Coach questions
- Next-session operating rules
- Human decision gate

## Suggested Slash Command: `/monthly-performance-coach`

Purpose: review recurring process, risk, and behavior patterns across the month.

Suggested bundle flow:

```text
trader-memory-core
→ signal-postmortem
→ trade-performance-coach
→ monthly-performance-review
```

## Guardrails for Hermes Prompts

Hermes prompts should state:

- This is not financial advice.
- This is not therapy or mental-health diagnosis.
- The assistant must not place or prepare broker orders.
- The assistant must not tell the user to buy, sell, short, hold, or size a specific security.
- All recommendations are process guardrails for the human trader to accept, modify, defer, or journal.

## Naming

Existing alias can remain:

```text
trading-research-assistant
```

Future public positioning can broaden to:

```text
Hermes Trading Desk Assistant
```

Suggested subtitle:

```text
A trading desk assistant for research, journaling, risk review, and performance coaching.
```
