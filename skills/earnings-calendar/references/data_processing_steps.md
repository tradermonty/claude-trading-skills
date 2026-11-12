# Data Processing Steps

Step 5 detail, moved verbatim from `SKILL.md`.

#### 5.1 Parse JSON Data

Load JSON data from script output:
```python
import json
earnings_data = json.loads(earnings_json_string)
```

Or if saved to file:
```python
with open('earnings_data.json', 'r') as f:
    earnings_data = json.load(f)
```

#### 5.2 Verify Data Structure

Confirm data includes required fields:
- ✓ symbol
- ✓ companyName
- ✓ date
- ✓ timing (BMO/AMC/TAS)
- ✓ marketCap
- ✓ sector

#### 5.3 Group by Date

Group all earnings announcements by date:
- Sunday, [Full Date] (if applicable)
- Monday, [Full Date]
- Tuesday, [Full Date]
- Wednesday, [Full Date]
- Thursday, [Full Date]
- Friday, [Full Date]
- Saturday, [Full Date] (if applicable)

#### 5.4 Sub-Group by Timing

Within each date, create three sub-sections:
1. **Before Market Open (BMO)**
2. **After Market Close (AMC)**
3. **Time Not Announced (TAS)**

Data is already sorted by timing from the script, so maintain this order.

#### 5.5 Within Each Timing Group

Companies are already sorted by market cap descending (script output):
- Mega-cap (>$200B) first
- Large-cap ($10B-$200B) second
- Mid-cap ($2B-$10B) third

This prioritization ensures the most market-moving companies are listed first.

#### 5.6 Calculate Summary Statistics

Compute:
- **Total Companies**: Count of all companies in dataset
- **Mega/Large Cap Count**: Count where marketCap >= $10B
- **Mid Cap Count**: Count where marketCap between $2B and $10B
- **Peak Day**: Day of week with most earnings announcements
- **Sector Distribution**: Count by sector (Technology, Healthcare, Financial, etc.)
- **Highest Market Cap Companies**: Top 5 companies by market cap
