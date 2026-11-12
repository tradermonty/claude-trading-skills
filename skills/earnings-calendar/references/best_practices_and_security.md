# Best Practices and Security Notes

Moved verbatim from `SKILL.md`.

## Best Practices

### Do's
✓ Always get current date first before any data retrieval
✓ Use FMP API as primary source for reliability
✓ Store API key in environment variable for CLI usage
✓ Sort by market cap to prioritize high-impact companies
✓ Group by date then timing for logical organization
✓ Include summary statistics for quick overview
✓ Credit data sources in report footer
✓ Use clean markdown tables for readability
✓ Provide timing reference section for clarity
✓ Note data freshness and potential for changes
✓ Include EPS and revenue estimates when available

### Don'ts
✗ Don't assume "next week" without calculating from current date
✗ Don't omit timing information (BMO/AMC/TAS)
✗ Don't mix date formats within report (stay consistent)
✗ Don't include micro/small-cap unless specifically requested
✗ Don't forget to sort by market cap within sections
✗ Don't share API key in conversations or reports
✗ Don't include earnings from current week or past dates
✗ Don't generate report without quality assurance checks
✗ Don't commit API keys to version control

## Security Notes: API Key Security

### API Key Security

**Important Reminders**:
1. ✓ Use free tier API keys for testing
2. ✓ Rotate keys regularly
3. ✓ Don't share conversations containing API keys
4. ✓ Set API key as environment variable for CLI
5. ✓ Keys provided in chat are session-only (forgotten after session ends)
6. ✗ Never commit API keys to Git repositories
7. ✗ Never use production API keys with sensitive data access

**Best Practice**:
For Claude Code (CLI), always use environment variable:
```bash
# Add to ~/.zshrc or ~/.bashrc
export FMP_API_KEY="your-key-here"
```

For Claude Web, understand that:
- API key entered in chat is temporary
- Stored only in conversation context
- Not saved to disk
- Forgotten when session ends
