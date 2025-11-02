# US Market Bubble Detector - Changelog

## Version 2.1 (November 3, 2025)

### Critical Issue Fixed
**Problem Identified:** v2.0 allowed excessive qualitative adjustments based on unmeasured "narratives" and subjective impressions, leading to inflated bubble risk scores.

**Example Case (Nov 3, 2025):**
- Quantitative Score (Phase 2): 9 points (objective, data-driven)
- Qualitative Adjustment (v2.0): +2 points
  - Media Narrative: +1 (based on "elevated AI narrative" - NO DATA)
  - Valuation: +1 (P/E 30.8 - DOUBLE COUNTED, ignored fundamental backing)
- **Result**: 11/16 points → Euphoria phase → 40% risk budget (overly defensive)

**Root Cause:** Confirmation bias - analyst had bearish conclusion first, then adjusted qualitative points to match expectation.

### Changes in v2.1

#### 1. Stricter Qualitative Criteria (MAX +3, down from +5)

**A. Social Penetration (0-1 points)**
- **v2.0**: Loose criteria, "general awareness" acceptable
- **v2.1**: ALL three required:
  - Direct user report of non-investor recommendations
  - Specific examples with dates/names
  - Multiple independent sources (minimum 3)

**B. Media/Search Trends (0-1 points)**
- **v2.0**: Subjective "many reports" acceptable
- **v2.1**: BOTH required:
  - Google Trends 5x+ YoY (measured data)
  - Mainstream coverage confirmed (Time covers, TV specials with dates)
- **Critical**: "Elevated narrative" without data = 0 points

**C. Valuation Disconnect (0-1 points)**
- **v2.0**: P/E >25 alone sufficient
- **v2.1**: ALL required AND avoid double-counting:
  - P/E >25 (if NOT in Phase 2)
  - Fundamentals explicitly ignored in discourse
  - "This time is different" documented in major media
- **Self-check**: If companies have real earnings supporting valuations → 0 points

#### 2. Confirmation Bias Prevention

New mandatory checklist before adding ANY qualitative points:
```
□ Do I have concrete, measurable data? (not impressions)
□ Would an independent observer reach the same conclusion?
□ Am I avoiding double-counting with Phase 2 scores?
□ Have I documented specific evidence with sources?
```

#### 3. Granular Risk Phases

**New "Elevated Risk" Phase (8-9 points)**
- **v2.0**: 9 points = Euphoria = 40% risk budget (extreme defensive)
- **v2.1**: 9 points = Elevated Risk = 50-70% risk budget (balanced caution)

**Updated Risk Budget Matrix:**
| Score | Phase | v2.0 Risk Budget | v2.1 Risk Budget | Change |
|-------|-------|------------------|------------------|--------|
| 0-4 | Normal | 100% | 100% | - |
| 5-7 | Caution | 70% | 70-80% | More flexible |
| 8-9 | Elevated Risk | 40% (Euphoria) | 50-70% | **NEW PHASE** |
| 10-12 | Euphoria | 40% | 40-50% | More balanced |
| 13-15 | Critical | 20% | 20-30% | Reduced max |

#### 4. Maximum Score Reduction

- **v2.0**: 0-16 points (Phase 2: 12, Phase 3: -1 to +5)
- **v2.1**: 0-15 points (Phase 2: 12, Phase 3: 0 to +3)

### Impact on Nov 3, 2025 Analysis

**Under v2.0:**
- Score: 11/16 → Euphoria phase
- Risk Budget: 40%
- Positioning: Extreme defensive

**Under v2.1 (corrected):**
- Quantitative: 9/12 (unchanged, data-driven)
- Qualitative:
  - Media Narrative: 0 points (no Google Trends data)
  - Valuation: 0 points (AI has fundamental backing, double-counting)
- **Score: 9/15 → Elevated Risk phase**
- **Risk Budget: 50-70%**
- **Positioning: Cautious but not extreme**

### Key Learnings

1. **Data > Impressions**: "Elevated narrative" is not measurable evidence
2. **Avoid Double-Counting**: Valuation in Phase 2 quantitative ≠ add again in Phase 3
3. **Check Internal Consistency**: If report admits "AI has fundamental backing," then valuation disconnect score must be 0
4. **Independent Verification**: All qualitative points must be verifiable by independent observers

### Documentation Updates

- `SKILL.md`: Updated to v2.1 with strict criteria
- `references/implementation_guide.md`: Enhanced Phase 3 with bias prevention checklist
- `references/quick_reference.md`: Updated action matrix with new Elevated Risk phase
- `references/bubble_framework.md`: Updated risk budget table

---

## Version 2.0 (October 27, 2025)

### Initial Major Revision
- Introduced mandatory quantitative data collection
- Eliminated reliance on impressions and speculation
- Established clear threshold settings for each indicator
- Two-phase evaluation process: Quantitative → Qualitative

---

**Version Control:**
- v1.x: Original framework (deprecated)
- v2.0: Data-driven quantitative focus
- v2.1: Strict qualitative criteria + confirmation bias prevention
