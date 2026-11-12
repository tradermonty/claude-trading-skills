# Advanced Usage

Moved verbatim from `SKILL.md`.

### Customizing Screening Criteria

Modify thresholds in `scripts/screen_dividend_stocks.py`:

**Line 383-388** - Initial screening parameters:
```python
candidates = client.screen_stocks(
    dividend_yield_min=3.5,  # Adjust yield threshold
    pe_max=20,               # Adjust P/E threshold
    pb_max=2,                # Adjust P/B threshold
    market_cap_min=2_000_000_000  # Minimum $2B market cap
)
```

**Line 423** - Dividend CAGR threshold:
```python
if not div_cagr or div_cagr < 5.0:  # Adjust growth threshold
```

### Sector-Specific Screening

Add sector filtering after initial screening:

```python
# Filter for specific sectors
target_sectors = ['Consumer Defensive', 'Utilities', 'Healthcare']
candidates = [s for s in candidates if s.get('sector') in target_sectors]
```

### Excluding REITs and Financials

REITs and financial stocks have different dividend characteristics (higher payouts, different metrics):

```python
# Exclude REITs and Financials
exclude_sectors = ['Real Estate', 'Financial Services']
candidates = [s for s in candidates if s.get('sector') not in exclude_sectors]
```

### Exporting to CSV

Convert JSON results to CSV for Excel analysis:

```python
import json
import csv

with open('dividend_screener_results.json', 'r') as f:
    data = json.load(f)

stocks = data['stocks']

with open('screening_results.csv', 'w', newline='') as csvfile:
    if stocks:
        fieldnames = stocks[0].keys()
        writer = csv.DictWriter(csvfile, fieldnames=fieldnames)
        writer.writeheader()
        writer.writerows(stocks)
```
