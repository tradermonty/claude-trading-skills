# Use Cases and Examples

Moved verbatim from `SKILL.md`.

### Use Case 1: Weekly Review (Primary Use Case)

**User Request**: "Get next week's earnings calendar"

**Workflow**:
1. Get current date (e.g., November 2, 2025)
2. Calculate target week (November 3-9, 2025)
3. Load FMP API guide
4. Detect/request API key
5. Fetch earnings data:
   ```bash
   python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 > earnings_data.json
   ```
6. Generate markdown report:
   ```bash
   python scripts/generate_report.py earnings_data.json earnings_calendar_2025-11-02.md
   ```
7. Notify user with summary

**Complete One-Liner**:
```bash
python scripts/fetch_earnings_fmp.py 2025-11-03 2025-11-09 > earnings_data.json && \
python scripts/generate_report.py earnings_data.json earnings_calendar_2025-11-02.md
```

### Use Case 2: Focused on Specific Day

**User Request**: "What earnings are coming out Monday?"

**Workflow**:
1. Get current date and identify next Monday (e.g., November 4, 2025)
2. Fetch full week data (same as Use Case 1)
3. Generate full report but highlight Monday section
4. Provide verbal summary of Monday's earnings with emphasis

### Use Case 3: Mega-Cap Focus

**User Request**: "Show me earnings for companies over $100B market cap next week"

**Workflow**:
1. Fetch full earnings data (script already filters >$2B)
2. Process and organize as normal
3. When generating report, add a "Mega-Cap Focus" section at top
4. Filter tables to show only companies >$100B
5. Note: Still include full data in appendix for reference

### Use Case 4: Sector-Specific

**User Request**: "What tech companies have earnings next week?"

**Workflow**:
1. Fetch full earnings data
2. Process and organize as normal
3. Filter results by sector = "Technology"
4. Generate report with focus on technology sector
5. Note: Template structure remains the same; content is filtered
