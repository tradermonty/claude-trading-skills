# LLM Review JSON Schema

Use this schema when requesting the LLM-axis review.

## Required JSON Shape

```json
{
  "score": 0,
  "summary": "one-paragraph assessment",
  "findings": [
    {
      "severity": "high|medium|low",
      "path": "skills/<skill-name>/file.ext",
      "line": 0,
      "message": "problem statement",
      "improvement": "concrete fix"
    }
  ]
}
```

## Constraints

- Return JSON only (no markdown wrapper).
- Set `score` in range `0..100`.
- Set `line` to `null` when unknown.
- Keep `severity` to `high`, `medium`, or `low`.
- Make `message` specific and testable.
- Make `improvement` actionable, preferably with file-level targets.

## Review Focus

- Validate logic and behavior in scripts (`scripts/*.py`).
- Check mismatch between `SKILL.md` instructions and actual script behavior.
- Check missing tests and risk of regressions.
- Identify ambiguous instructions that reduce execution reliability.
