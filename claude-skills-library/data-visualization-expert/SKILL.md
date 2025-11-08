---
name: data-visualization-expert
description: Professional data visualization skill specialized in creating reader-friendly, accessible, and aesthetically pleasing charts and dashboards. Use this skill when you need to create visualizations, choose appropriate chart types, design color schemes, create dashboards, or apply design best practices for data communication. Expertise includes visualization principles, color theory, typography, layout design, and accessibility guidelines.
---

# Data Visualization Expert

## Overview

Create publication-quality, accessible, and reader-friendly data visualizations that communicate insights effectively. This skill provides comprehensive guidance on visualization design principles, chart selection, color theory, dashboard design, and best practices for professional data communication.

## When to Use This Skill

Invoke this skill when working on tasks that involve:

- **Chart Creation:** Creating any type of chart or graph
- **Chart Selection:** Choosing the right visualization for your data
- **Color Design:** Selecting color palettes and ensuring accessibility
- **Dashboard Design:** Creating executive dashboards or operational monitors
- **Visual Design:** Improving readability and aesthetic appeal
- **Accessibility:** Ensuring visualizations work for colorblind viewers
- **Presentation Design:** Preparing visualizations for slides or reports
- **Data Communication:** Making insights clear and actionable

**Typical User Requests:**
- "Create a bar chart comparing sales by region"
- "What's the best way to visualize this time series data?"
- "Make this chart more readable and professional"
- "Design a dashboard showing our key metrics"
- "Choose colors that work for colorblind people"
- "How should I present this data in a presentation?"
- "Create visualizations that tell a story"

## Core Visualization Workflow

Follow this systematic approach when creating visualizations:

```
1. Understand the Goal
   ↓
2. Analyze the Data
   ↓
3. Select Chart Type
   ↓
4. Choose Color Palette
   ↓
5. Apply Design Principles
   ↓
6. Add Context & Annotations
   ↓
7. Ensure Accessibility
   ↓
8. Review & Refine
```

## Workflow 1: Choosing the Right Chart Type

### Step 1: Identify Your Communication Goal

**Ask yourself:**
- What insight am I trying to convey?
- What question does this visualization answer?
- What action should viewers take?

**Common Goals:**
- **Compare** values across categories → Bar Chart, Lollipop Chart
- **Show distribution** → Histogram, Box Plot, Violin Plot
- **Reveal relationship** → Scatter Plot, Line Chart
- **Display composition** → Stacked Bar, Tree Map, Pie Chart (sparingly)
- **Track change over time** → Line Chart, Area Chart
- **Show geographic patterns** → Choropleth Map, Symbol Map
- **Display hierarchical data** → Tree Map, Sunburst, Tree Diagram

### Step 2: Consider Your Data Characteristics

**Data Type:**
- **Categorical:** Bar chart, pie chart (2-5 categories only)
- **Continuous:** Line chart, scatter plot, histogram
- **Time series:** Line chart, area chart, sparkline
- **Geographic:** Map visualizations
- **Hierarchical:** Tree map, sunburst
- **Multivariate:** Scatter plot matrix, parallel coordinates, small multiples

**Data Volume:**
- **Few data points (<20):** Most chart types work
- **Medium (20-100):** Consider aggregation or small multiples
- **Many (>100):** Density plots, heatmaps, sampling, or interactive charts

### Step 3: Consult the Chart Selection Guide

Reference: `references/chart_selection_guide.md`

**Quick Selection:**

```
COMPARISON → Bar Chart (vertical/horizontal)
  ├─ Few categories → Vertical bar
  ├─ Many categories or long names → Horizontal bar
  ├─ Multiple groups → Grouped bar
  └─ Parts + Total → Stacked bar

DISTRIBUTION → Histogram + KDE
  ├─ Quick summary → Box Plot
  ├─ Full shape → Violin Plot
  └─ Compare groups → Side-by-side box plots

RELATIONSHIP → Scatter Plot
  ├─ Continuous time → Line Chart
  ├─ Correlation → Heatmap
  └─ 3+ variables → Bubble chart or color/size encoding

COMPOSITION → Stacked Bar Chart
  ├─ Simple (2-3 parts) → Pie chart (acceptable)
  ├─ Over time → Stacked area
  ├─ Hierarchy → Tree map
  └─ Sequential changes → Waterfall

TIME SERIES → Line Chart
  ├─ Volume/cumulative → Area chart
  ├─ Multiple metrics → Line chart (max 5 lines)
  └─ Compact trend → Sparkline
```

### Step 4: Avoid Common Mistakes

**❌ Don't Use:**
- Pie charts with >5 segments (use bar chart instead)
- 3D charts (distorts perception)
- Dual Y-axes (can mislead)
- Too many colors (limit to 5-8 for categorical data)
- Inconsistent time intervals

**✅ Do Use:**
- Simple, clear chart types
- Appropriate scales (start Y-axis at zero for bar charts)
- Direct labels when possible (instead of legends)
- Consistent formatting

### Example: Choosing for Sales Analysis

**Scenario:** Compare sales across 5 product categories

**Decision Process:**
1. Goal: **Compare** values across categories
2. Data: 5 categorical values (products) with one numeric value (sales)
3. Chart Type: **Bar Chart** (vertical or horizontal)
4. Enhancements: Highlight top performer, add target line
5. Result: Clear comparison with immediate insight

**Implementation:**
```bash
python scripts/create_visualization.py \
  --type bar \
  --input sales_data.csv \
  --x product_category \
  --y sales_amount \
  --title "Q4 Product Sales Comparison" \
  --sort \
  --output product_sales.png
```

## Workflow 2: Applying Color Best Practices

### Step 1: Understand Color Purpose

**Color Should:**
- Encode information (categories, magnitude)
- Create visual hierarchy
- Guide attention to insights
- Maintain consistency across visualizations
- Work for all viewers (including colorblind)

**Color Should NOT:**
- Be purely decorative
- Use red/green for critical information (colorblind issue)
- Overwhelm with too many hues
- Lack sufficient contrast

### Step 2: Select Appropriate Palette Type

Reference: `references/visualization_principles.md` → "Color Theory"
Resource: `assets/color_palettes.json`

**Palette Types:**

**1. Qualitative (Categorical Data):**
- Use when: Showing distinct categories with no order
- Limit: 5-8 colors maximum
- Example: Product lines, regions, departments
- Recommended: Okabe-Ito (colorblind-safe), Tableau10

```python
# Okabe-Ito palette (colorblind-safe)
colors = ['#E69F00', '#56B4E9', '#009E73', '#F0E442',
          '#0072B2', '#D55E00', '#CC79A7']
```

**2. Sequential (Ordered Data):**
- Use when: Showing low-to-high progression
- Example: Population density, temperature, sales volume
- Recommended: Single hue (light to dark blue, green, etc.)

**3. Diverging (Data with Midpoint):**
- Use when: Data has meaningful center (zero, average)
- Example: Positive/negative, above/below average, correlation (-1 to +1)
- Recommended: Red-Blue, Brown-Teal (colorblind-safe)

**4. Semantic (Meaning-Based):**
- Use when: Colors have conventional meanings
- Green = positive/success, Red = negative/danger, Yellow = warning
- Caution: Cultural differences exist

### Step 3: Ensure Accessibility

**Colorblind Considerations:**
- 8% of males, 0.5% of females have color vision deficiency
- Most common: Red-green colorblindness

**Best Practices:**
1. **Use colorblind-safe palettes** (Okabe-Ito, Viridis)
2. **Don't rely on color alone** - add patterns, labels, or shapes
3. **Test with simulator** (Color Oracle, Coblis)
4. **Ensure contrast** - 4.5:1 for text, 3:1 for graphics (WCAG 2.1)

**Safe Color Combinations:**
- Blue + Orange (excellent contrast)
- Blue + Yellow
- Purple + Green
- Brown + Teal

**Avoid:**
- Red + Green (most problematic)
- Blue + Purple (for some types)
- Light green + Yellow

### Step 4: Apply Color Strategically

**Emphasis Pattern:**
- Main data: Primary color (e.g., blue)
- Highlight: Accent color (e.g., red/orange)
- Background data: Gray (de-emphasize)

**Example:**
```python
# All bars in gray except the maximum
colors = ['#CCCCCC'] * len(data)
colors[max_index] = '#E63946'  # Highlight in red
```

### Example: Colorblind-Safe Dashboard

**Scenario:** Create dashboard viewable by all users

**Solution:**
1. Use Okabe-Ito palette for categories
2. Use Blue-Orange for comparisons
3. Add patterns to bars (diagonal lines, dots)
4. Include value labels directly on charts
5. Test with Color Oracle simulator

```python
# Implementation
from visualization_templates import executive_summary_template

kpis = [
    {'title': 'Revenue', 'value': 1234567, 'change_pct': 12.5},
    {'title': 'Customers', 'value': 5432, 'change_pct': 5.2}
]

fig = executive_summary_template(kpis, title='Q4 Dashboard')
fig.savefig('accessible_dashboard.png', dpi=300)
```

## Workflow 3: Designing Professional Dashboards

### Step 1: Define Dashboard Purpose and Audience

**Dashboard Types:**

**1. Strategic (Executive):**
- Audience: C-level executives
- Content: High-level KPIs, trends, targets
- Update: Weekly/monthly
- Focus: Strategic decision-making

**2. Operational:**
- Audience: Managers, operations team
- Content: Real-time metrics, status indicators
- Update: Real-time to hourly
- Focus: Day-to-day operations

**3. Analytical:**
- Audience: Analysts, data teams
- Content: Detailed data, drill-down, filters
- Update: Daily or on-demand
- Focus: Deep exploration

### Step 2: Apply Information Hierarchy

Reference: `references/dashboard_design.md`

**F-Pattern Layout (Western Reading):**
```
┌─────────────────────────────┐
│ 1. Most Important (Top-Left)│
│    ↓                        │
│ 2. Secondary (Middle)       │
│    ↓                        │
│ 3. Details (Bottom)         │
└─────────────────────────────┘
```

**Layout Guidelines:**
- **Top Row:** 3-5 KPI cards with sparklines
- **Middle:** Primary visualization (largest chart)
- **Bottom:** Supporting charts and tables
- **Whitespace:** 20-30% of dashboard should be empty space

### Step 3: Design KPI Cards

**Components:**
- **Metric Name:** Clear, concise (10-12pt)
- **Value:** Large, bold (28-36pt)
- **Change Indicator:** Arrow + percentage with color
- **Sparkline:** Optional mini-trend (last 7-30 periods)
- **Comparison:** "vs last month/year"

**Color Coding:**
```
↑ Green: Positive change
↓ Red: Negative change
→ Gray: No significant change
```

**Example:**
```python
from visualization_templates import kpi_card

fig = kpi_card(
    value=1234567,
    title='Monthly Revenue',
    change_pct=12.5,
    sparkline_data=[100, 105, 102, 108, 115, 120]
)
```

### Step 4: Maintain Consistency

**Style Guide Elements:**
- Font: Single family (Arial, Helvetica, Roboto)
- Colors: Consistent palette across all charts
- Spacing: Regular margins (16px, 24px, 32px increments)
- Grid: 12-column system for alignment
- Chart styles: Same border, gridline, and label format

### Example: Executive Dashboard

**Scenario:** Create monthly executive summary

**Requirements:**
- 4 key metrics (Revenue, Customers, Retention, NPS)
- 2 trend charts (Revenue over time, Regional breakdown)
- Suitable for presentation
- Print-friendly

**Implementation:**
```python
from visualization_templates import executive_summary_template

kpis = [
    {
        'title': 'Revenue',
        'value': 1234567,
        'change_pct': 12.5,
        'sparkline': [100, 105, 102, 108, 115, 120]
    },
    {
        'title': 'Customers',
        'value': 5432,
        'change_pct': 5.2,
        'sparkline': [90, 92, 95, 97, 98, 100]
    },
    {
        'title': 'Retention',
        'value': 89.5,
        'change_pct': 1.2,
        'sparkline': [85, 86, 87, 88, 89, 89.5]
    },
    {
        'title': 'NPS',
        'value': 72,
        'change_pct': 8.0,
        'sparkline': [65, 67, 68, 70, 71, 72]
    }
]

fig = executive_summary_template(
    kpis=kpis,
    title='Q4 2024 Executive Summary',
    subtitle='October - December 2024',
    figsize=(16, 10)
)

fig.savefig('executive_summary.pdf', dpi=300, bbox_inches='tight')
```

## Workflow 4: Creating Story-Driven Visualizations

### Step 1: Define Your Narrative

**Story Structure:**
1. **Context:** Establish baseline or background
2. **Insight:** Reveal the key finding
3. **Action:** What should viewer do with this information?

**Example:**
- Context: "Historical sales have been flat for 3 years"
- Insight: "New product line drove 45% growth in Q4"
- Action: "Invest more resources in new product development"

### Step 2: Use Visual Emphasis

**Techniques:**

**1. Color Contrast:**
- Key element: Bright color (red, orange)
- Others: Gray or muted colors

```python
# Highlight one bar
colors = ['#CCCCCC'] * 5
colors[3] = '#E63946'  # Highlight 4th bar
```

**2. Annotations:**
- Add arrows, text boxes, or callouts
- Keep text concise (5-8 words)
- Position near relevant data

```python
ax.annotate('45% increase',
            xy=(date, value),
            xytext=(10, 10),
            textcoords='offset points',
            fontsize=12,
            fontweight='bold',
            color='#E63946',
            arrowprops=dict(arrowstyle='->', color='#E63946'))
```

**3. Size:**
- Make important elements larger
- Reduce size of supporting elements

**4. Position:**
- Place critical insight in top-left (F-pattern)

### Step 3: Add Context

**Essential Elements:**
- **Title:** Clear, descriptive, includes key insight
- **Axes Labels:** Include units (¥, %, etc.)
- **Legends:** When needed, but prefer direct labeling
- **Source:** Data source and date
- **Notes:** Important caveats or methodology

**Good Title Examples:**
```
❌ "Sales Over Time"
✅ "Sales Jumped 45% After New Product Launch in Q4"

❌ "Customer Satisfaction"
✅ "Customer Satisfaction Reaches All-Time High of 8.9/10"
```

### Step 4: Progressive Disclosure

**For Complex Stories:**
1. Start with summary/conclusion
2. Show high-level view
3. Allow drill-down to details
4. Provide data table for reference

**Dashboard Pattern:**
```
Top: Summary statement + key number
Middle: Primary chart showing main insight
Bottom: Supporting details and breakdowns
```

### Example: Product Launch Analysis

**Scenario:** Show impact of new product launch on revenue

**Story:**
- Context: Revenue flat for 12 months
- Event: New product launched in September
- Impact: 45% revenue increase in Q4
- Action: Scale up production and marketing

**Visualization Approach:**
1. Line chart showing 18-month revenue trend
2. Vertical line marking launch date
3. Annotation highlighting 45% increase
4. Color: Gray before launch, Blue after launch
5. Title: "New Product Drives 45% Revenue Growth in Q4"

```python
import matplotlib.pyplot as plt
import pandas as pd

fig, ax = plt.subplots(figsize=(12, 6))

# Pre-launch (gray)
ax.plot(dates[:9], revenue[:9], color='#CCCCCC', linewidth=2, label='Before Launch')

# Post-launch (blue)
ax.plot(dates[8:], revenue[8:], color='#2E86AB', linewidth=3, label='After Launch', marker='o')

# Launch date line
ax.axvline(launch_date, color='#666666', linestyle='--', linewidth=2, alpha=0.7)
ax.text(launch_date, ax.get_ylim()[1], ' Product Launch', ha='left', va='top')

# Highlight annotation
ax.annotate('↑ 45% increase',
            xy=(dates[-1], revenue[-1]),
            xytext=(-50, 20),
            textcoords='offset points',
            fontsize=14,
            fontweight='bold',
            color='#E63946',
            arrowprops=dict(arrowstyle='->', lw=2, color='#E63946'))

ax.set_title('New Product Drives 45% Revenue Growth in Q4', fontweight='bold', fontsize=16)
ax.set_ylabel('Revenue (¥ Million)', fontweight='bold')
ax.legend()
ax.grid(alpha=0.3)
plt.tight_layout()
```

## Workflow 5: Ensuring Accessibility and Readability

### Step 1: Test for Colorblindness

**Tools:**
- Color Oracle (free desktop app)
- Coblis - Color Blindness Simulator (online)
- Chrome DevTools Accessibility features

**Process:**
1. Create visualization
2. Run through colorblind simulator
3. Check if information is still clear
4. If not, add patterns, labels, or adjust colors

### Step 2: Check Contrast Ratios

**WCAG 2.1 Standards:**
- Normal text: 4.5:1 minimum
- Large text (18pt+): 3:1 minimum
- Graphics: 3:1 minimum

**Tools:**
- WebAIM Contrast Checker
- Colour Contrast Analyser

**Common Issues:**
- Light gray text on white background (insufficient)
- Yellow on white (insufficient)
- Light blue on white (borderline)

### Step 3: Ensure Font Readability

**Best Practices:**
- **Font Family:** Sans-serif for digital (Arial, Helvetica, Roboto)
- **Minimum Size:** 10-11pt for body text, 8-9pt minimum for labels
- **Hierarchy:** Use 2-3 sizes maximum
  - Title: 16-20pt, bold
  - Labels: 12-14pt
  - Annotations: 10-12pt

**Avoid:**
- All caps (harder to read)
- Light font weights (<400)
- Decorative or script fonts

### Step 4: Test on Target Medium

**Considerations by Medium:**

**1. Presentation (Projector):**
- Larger fonts (minimum 14pt)
- High contrast
- Simple charts
- Avoid fine details

**2. Print:**
- 300 DPI minimum
- Consider B&W printing
- Include data tables

**3. Dashboard (Screen):**
- Responsive design
- Interactive elements clear
- Touch targets 44×44px minimum (mobile)

**4. Report (PDF):**
- Embedded fonts
- Vector graphics (SVG) when possible
- Consistent with document style

### Example: Accessible Presentation Chart

**Scenario:** Chart for conference presentation

**Requirements:**
- Visible from back of room
- Works on projector (often low contrast)
- Colorblind-safe
- Clear on photos/screenshots

**Solution:**
```python
import matplotlib.pyplot as plt
import seaborn as sns

# Setup
plt.rcParams['font.size'] = 14  # Larger default
plt.rcParams['axes.titlesize'] = 20
plt.rcParams['axes.labelsize'] = 16

fig, ax = plt.subplots(figsize=(12, 7))

# Use high-contrast, colorblind-safe colors
colors = ['#0072B2', '#E69F00']  # Blue and Orange

# Create chart with clear distinction
ax.bar(categories, values, color=colors[0], edgecolor='black', linewidth=2)

# Large, bold labels
ax.set_title('Clear Title Visible From Back Row', fontweight='bold', fontsize=24, pad=20)
ax.set_ylabel('Value (Units)', fontweight='bold', fontsize=18)

# High contrast grid
ax.grid(axis='y', alpha=0.5, linewidth=1.5, color='#666666')

# Direct labels (no legend needed)
for i, (cat, val) in enumerate(zip(categories, values)):
    ax.text(i, val + 10, f'{val}', ha='center', fontsize=16, fontweight='bold')

# Clean style
ax.spines['top'].set_visible(False)
ax.spines['right'].set_visible(False)

plt.tight_layout()
fig.savefig('presentation_chart.png', dpi=300, facecolor='white')
```

## Quick Start Examples

### Example 1: Simple Bar Chart

```bash
python scripts/create_visualization.py \
  --type bar \
  --input sales.csv \
  --x product \
  --y revenue \
  --title "Product Revenue Comparison Q4 2024" \
  --ylabel "Revenue (¥ Million)" \
  --palette colorblind_safe \
  --sort \
  --output revenue_chart.png
```

### Example 2: Time Series with Trend

```bash
python scripts/create_visualization.py \
  --type line \
  --input monthly_sales.csv \
  --x date \
  --y sales \
  --hue region \
  --title "Regional Sales Trends" \
  --markers \
  --palette tableau10 \
  --output sales_trend.png
```

### Example 3: Scatter Plot with Trendline

```bash
python scripts/create_visualization.py \
  --type scatter \
  --input marketing.csv \
  --x spend \
  --y revenue \
  --size customer_count \
  --title "Marketing ROI Analysis" \
  --trendline \
  --output roi_analysis.png
```

### Example 4: Executive KPI Cards

```python
from visualization_templates import kpi_card

# Create individual KPI card
fig = kpi_card(
    value=1234567,
    title='Monthly Revenue',
    change_pct=12.5,
    sparkline_data=[100, 105, 102, 108, 115, 120],
    figsize=(3, 2.5)
)
fig.savefig('revenue_kpi.png', dpi=150, bbox_inches='tight')
```

### Example 5: Full Dashboard

```python
from visualization_templates import executive_summary_template

kpis = [
    {'title': 'Revenue', 'value': 1234567, 'change_pct': 12.5, 'sparkline': [100,105,108,115,120]},
    {'title': 'Customers', 'value': 5432, 'change_pct': 5.2, 'sparkline': [90,92,95,98,100]},
    {'title': 'Retention %', 'value': 89.5, 'change_pct': 1.2, 'sparkline': [85,86,88,89,89.5]},
    {'title': 'NPS', 'value': 72, 'change_pct': 8.0, 'sparkline': [65,68,70,71,72]}
]

fig = executive_summary_template(
    kpis=kpis,
    title='Q4 2024 Performance Dashboard',
    subtitle='October - December 2024',
    figsize=(16, 10)
)
fig.savefig('dashboard.pdf', dpi=300, bbox_inches='tight')
```

## Resources

This skill includes the following resources:

### References (Load on-demand for guidance)

1. **`visualization_principles.md`** - Core design principles
   - Clarity, accuracy, accessibility guidelines
   - Color theory and palettes
   - Typography and layout principles
   - Storytelling techniques

2. **`chart_selection_guide.md`** - Comprehensive chart type guide
   - Decision tree for chart selection
   - 30+ chart types with use cases
   - When to use and when to avoid specific charts
   - Code examples for each type

3. **`dashboard_design.md`** - Dashboard best practices
   - Layout principles and grid systems
   - KPI card design
   - Interactivity and filters
   - Performance optimization

### Scripts (Executable tools)

1. **`create_visualization.py`** - Command-line visualization creator
   - Supports 6 chart types: bar, line, scatter, heatmap, distribution, dashboard
   - Professional styling built-in
   - Multiple color palettes
   - Export to PNG, PDF, SVG

### Assets (Templates and resources for output)

1. **`visualization_templates.py`** - Ready-to-use Python templates
   - KPI cards
   - Executive summaries
   - Comparison charts
   - Trend analysis
   - Waterfall charts
   - Correlation heatmaps

2. **`color_palettes.json`** - Comprehensive color palette library
   - Qualitative (categorical data)
   - Sequential (ordered data)
   - Diverging (data with midpoint)
   - Business and industry-specific
   - Accessibility-focused palettes
   - Usage guidelines

## Best Practices Checklist

### Before Creating Visualization

- [ ] Understand the insight you want to communicate
- [ ] Know your audience and their needs
- [ ] Identify the appropriate chart type for your data
- [ ] Consider the medium (screen, print, presentation)

### During Creation

- [ ] Use appropriate chart type for data and goal
- [ ] Apply colorblind-safe palette
- [ ] Ensure sufficient contrast (4.5:1 text, 3:1 graphics)
- [ ] Start bar chart Y-axis at zero (unless good reason)
- [ ] Label axes with units
- [ ] Use direct labels instead of legends when possible
- [ ] Add clear, descriptive title (include key insight)
- [ ] Remove chartjunk (unnecessary decoration)
- [ ] Use consistent formatting across related charts

### After Creation

- [ ] Test with colorblind simulator
- [ ] Check contrast ratios
- [ ] Verify readability at target size/distance
- [ ] Review for accuracy and honesty
- [ ] Add data source and date
- [ ] Get feedback from representative user

## Common Mistakes to Avoid

❌ **Using pie charts for many categories** → Use horizontal bar chart
❌ **3D effects** → Use 2D charts with proper visual encoding
❌ **Dual Y-axes** → Use indexed values or separate charts
❌ **Red-green color scheme** → Use blue-orange or other colorblind-safe combinations
❌ **Too many colors** → Limit to 5-8 for categorical data
❌ **Truncated Y-axis (bar charts)** → Start at zero
❌ **Missing labels/units** → Always label axes and include units
❌ **Cluttered layout** → Use whitespace, simplify

## Additional Resources

**Books:**
- "The Visual Display of Quantitative Information" by Edward Tufte
- "Storytelling with Data" by Cole Nussbaumer Knaflic
- "Information Dashboard Design" by Stephen Few

**Online Tools:**
- ColorBrewer 2.0 - Color palette generator
- Coolors.co - Color scheme generator
- WebAIM Contrast Checker - Accessibility testing
- Color Oracle - Colorblindness simulator

**Python Libraries:**
- Matplotlib - Foundation visualization library
- Seaborn - Statistical visualizations
- Plotly - Interactive charts
- Altair - Declarative visualization
