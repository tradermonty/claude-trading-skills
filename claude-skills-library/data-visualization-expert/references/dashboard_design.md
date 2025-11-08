# Dashboard Design Guide

## Overview

Dashboards are visual interfaces that display key metrics and insights at a glance. Effective dashboard design combines data visualization principles, information hierarchy, and user experience design to enable quick decision-making.

## Dashboard Purpose and Types

### 1. Strategic Dashboards

**Purpose:** Executive-level monitoring of key business metrics

**Characteristics:**
- High-level KPIs only
- Monthly/quarterly timeframes
- Minimal interactivity
- Focus on trends and targets
- Print-friendly

**Typical Metrics:**
- Revenue, profit, market share
- Customer satisfaction scores
- Strategic initiative progress

**Update Frequency:** Weekly or monthly

**Example Layout:**
```
┌─────────────────────────────────────────────────┐
│  KPI Cards (Revenue, Profit, Market Share)     │
├─────────────────────────────────────────────────┤
│  Revenue Trend Line Chart (12 months)          │
├──────────────────────┬──────────────────────────┤
│  Regional Performance│  Product Mix (Tree Map)  │
│  (Map)               │                          │
└──────────────────────┴──────────────────────────┘
```

### 2. Operational Dashboards

**Purpose:** Real-time monitoring of operations

**Characteristics:**
- Real-time or near-real-time updates
- Current status focus
- Alert indicators
- Drill-down capability
- Large screen display

**Typical Metrics:**
- Server uptime, response times
- Inventory levels
- Order fulfillment status
- Call center queue length

**Update Frequency:** Real-time to hourly

**Example Layout:**
```
┌─────────────────────────────────────────────────┐
│  Status Indicators (🟢 All Systems Operational) │
├─────────┬─────────┬─────────┬──────────┬────────┤
│ Orders  │ Active  │ Avg     │ Error    │ Uptime │
│ Today   │ Users   │ Response│ Rate     │ %      │
│ 1,234   │ 567     │ 234ms   │ 0.02%    │ 99.9%  │
├─────────┴─────────┴─────────┴──────────┴────────┤
│  Hourly Transaction Volume (Line Chart)         │
├──────────────────────┬──────────────────────────┤
│  Top Errors (Bar)    │  Geographic Activity(Map)│
└──────────────────────┴──────────────────────────┘
```

### 3. Analytical Dashboards

**Purpose:** Deep data exploration and analysis

**Characteristics:**
- Rich interactivity (filters, drill-down)
- Detailed data tables
- Multiple views
- Export capabilities
- Complex relationships

**Typical Content:**
- Detailed segmentation
- Cohort analysis
- Funnel analysis
- Correlation exploration

**Update Frequency:** Daily or on-demand

**Example Layout:**
```
┌─────────────────────────────────────────────────┐
│  Filters: [Date Range] [Region] [Product Line] │
├─────────────────────────────────────────────────┤
│  Main Metric Trend with Comparison              │
├──────────────────────┬──────────────────────────┤
│  Segmentation        │  Detailed Breakdown      │
│  (Grouped Bar)       │  (Data Table)            │
└──────────────────────┴──────────────────────────┘
```

## Information Hierarchy

### F-Pattern and Z-Pattern

**F-Pattern (Western Reading):**
```
High ┌─────────────────────┐
     │ 1 ←←←←←← Most Important
     │ ↓
     │ 2 ←←←← Secondary
     │ ↓
     │ 3 ←← Details
Low  └─────────────────────┘
```

**Design Implications:**
- Place most critical KPIs top-left
- Secondary metrics in middle
- Supporting details at bottom
- Left column for navigation or filters

### Visual Weight

**Elements that Draw Attention (Most → Least):**
1. Bright colors (red, orange)
2. Large size
3. Bold text
4. Position (top-left)
5. Isolation (whitespace around)
6. Motion (animations, blinking)

**Use Strategically:**
- Reserve bright colors for alerts or key insights
- Size elements proportionally to importance
- Don't compete for attention (max 1-2 focal points per screen)

## Layout Principles

### Grid System

**12-Column Grid (Flexible):**
```
Full Width:     [12 columns]
Half & Half:    [6] [6]
Thirds:         [4] [4] [4]
2/3 + 1/3:      [8] [4]
Quarters:       [3] [3] [3] [3]
```

**Best Practices:**
- Align to grid for visual consistency
- Use consistent gutters (16-24px typical)
- Maintain aspect ratios across similar charts
- Responsive: Stack columns on smaller screens

### Spacing and Rhythm

**Spacing Scale (8px base):**
```
XS: 8px   - Between related elements
S:  16px  - Between chart components
M:  24px  - Between distinct sections
L:  32px  - Between major sections
XL: 48px  - Between dashboard sections
```

**Vertical Rhythm:**
- Consistent spacing between rows
- Group related visualizations
- Separate sections with increased whitespace
- Avoid random spacing

### Responsive Design

**Breakpoints:**
```
Mobile:    < 768px   (Stack vertically)
Tablet:    768-1024px (2-column layout)
Desktop:   1024-1440px (3-column layout)
Large:     > 1440px  (4-column or wide charts)
```

**Responsive Strategy:**
- Prioritize mobile: What's most important?
- Simplify on small screens (fewer filters, larger touch targets)
- Hide secondary details on mobile
- Consider separate mobile dashboard

## KPI Design

### Number Display

**Formatting Guidelines:**
```python
# Bad
Revenue: 1234567.89

# Good
Revenue: ¥1.23M
Revenue: $1,234,568
Revenue: 1.2M (if space limited)
```

**Rounding Rules:**
- 0-999: Show full number (234)
- 1K-999K: Show with K (234K)
- 1M+: Show with M (1.23M)
- <1: Show 2 decimal places (0.87)
- Percentages: 1 decimal (45.3%)

### Delta Indicators

**Show Change:**
```
Revenue
¥1.23M
↑ 12.5% vs last month
```

**Color Coding:**
```
🟢 Green: Positive change (↑)
🔴 Red: Negative change (↓)
⚪ Gray: No significant change (→)

Note: Consider if increase is always good
(e.g., churn rate: increase is BAD)
```

**Components:**
- Current value (large, bold)
- Change indicator (arrow + percentage)
- Comparison period (small text)
- Sparkline (optional, shows trend)

### KPI Cards

**Standard KPI Card Layout:**
```
┌─────────────────────┐
│ METRIC NAME         │
│                     │
│   1,234   ↑ 12.5%  │
│   [Sparkline____/‾] │
│                     │
│ vs last month       │
└─────────────────────┘
```

**Design Specifications:**
- Card size: 200-300px wide, 120-180px tall
- Padding: 16-24px
- Metric value: 28-36pt
- Delta: 14-16pt
- Label: 10-12pt, uppercase or bold

**Python Example:**
```python
def create_kpi_card(value, change_pct, sparkline_data, title):
    fig, ax = plt.subplots(figsize=(3, 2))

    # Remove axes
    ax.axis('off')

    # Title
    ax.text(0.5, 0.9, title, ha='center', va='top',
            fontsize=10, fontweight='bold', transform=ax.transAxes)

    # Value
    ax.text(0.5, 0.6, f'{value:,.0f}', ha='center', va='center',
            fontsize=32, fontweight='bold', transform=ax.transAxes)

    # Delta
    arrow = '↑' if change_pct > 0 else '↓' if change_pct < 0 else '→'
    color = 'green' if change_pct > 0 else 'red' if change_pct < 0 else 'gray'
    ax.text(0.5, 0.4, f'{arrow} {abs(change_pct):.1f}%', ha='center', va='center',
            fontsize=14, color=color, transform=ax.transAxes)

    # Sparkline
    ax_spark = fig.add_axes([0.2, 0.1, 0.6, 0.2])
    ax_spark.plot(sparkline_data, color='gray', linewidth=1)
    ax_spark.fill_between(range(len(sparkline_data)), sparkline_data, alpha=0.2, color='gray')
    ax_spark.axis('off')

    return fig
```

## Chart Integration

### Chart Sizing

**Recommended Sizes:**
```
KPI Card:           200×150px to 300×180px
Small Chart:        400×300px
Medium Chart:       600×400px
Large Chart:        800×500px
Full Width Chart:   1200×400px
```

**Aspect Ratios:**
- Cards: 3:2 or 4:3
- Time series: 16:9 or 3:2
- Bar charts: 4:3 or 3:2
- Maps: Depends on geography

### Title and Annotations

**Chart Titles:**
- Descriptive, not just metric name
- Include key insight when possible
- 14-16pt, bold
- Position: Top-left or centered

```
❌ "Revenue"
✅ "Revenue Exceeds Target by 12% in Q4"

❌ "Customer Count"
✅ "Active Customers Growing Steadily (+15% YoY)"
```

**Annotations:**
- Highlight key events or anomalies
- Use arrows and text boxes
- Keep concise (5-8 words)
- Match annotation color to data element

### Consistent Styling

**Style Guide:**
```python
DASHBOARD_STYLE = {
    'font_family': 'Arial',
    'title_size': 16,
    'label_size': 12,
    'tick_size': 10,
    'color_primary': '#2E86AB',
    'color_secondary': '#A23B72',
    'color_positive': '#2E7D32',
    'color_negative': '#C62828',
    'color_neutral': '#757575',
    'grid_alpha': 0.3,
    'grid_color': '#CCCCCC'
}
```

**Apply Consistently:**
- Same color palette across all charts
- Same font family and sizes
- Same gridline style
- Same margins and padding

## Interactivity

### Filters

**Filter Types:**
1. **Time Range:** Date picker, relative dates
2. **Categorical:** Dropdown, multi-select
3. **Numeric:** Sliders, range inputs
4. **Search:** Text input for searching

**Filter Placement:**
```
Option 1: Top of dashboard (above all content)
Option 2: Left sidebar (persistent)
Option 3: Inline above each chart (chart-specific)
```

**Best Practices:**
- Show applied filters clearly
- Provide "Reset" or "Clear All" option
- Use smart defaults (last 30 days, all regions)
- Limit to 3-5 filter options (avoid filter overload)
- Show count of filtered items: "Showing 145 of 1,234 items"

### Drill-Down

**Patterns:**
1. **Click to Details:** Chart → Detail view
2. **Hierarchical:** Region → Country → City
3. **Modal/Popup:** Overlay with more details
4. **Linked Dashboards:** Button to related dashboard

**Visual Cues:**
- Cursor changes to pointer on hover
- Highlight on hover
- Breadcrumb trail for navigation back
- "Back" button when drilled down

### Tooltips

**Include in Tooltips:**
- Exact value (if not labeled)
- Category/date
- Additional context (% of total, change from previous)
- Sample size (for averages)

**Design:**
- Appear on hover, not click
- Position near cursor, but don't obscure data
- Use semi-transparent background
- 2-4 lines of text maximum
- Match dashboard style

```python
# Plotly tooltip example
import plotly.graph_objects as go

fig = go.Figure(data=go.Bar(
    x=categories,
    y=values,
    hovertemplate='<b>%{x}</b><br>' +
                  'Sales: ¥%{y:,.0f}<br>' +
                  'Change: +12.5%<br>' +
                  '<extra></extra>'  # Remove trace name
))
```

## Color in Dashboards

### Dashboard Color Schemes

**Monochromatic + Accent:**
```
Background: White (#FFFFFF) or Light Gray (#F5F5F5)
Primary Data: Blue (#2E86AB)
Secondary Data: Light Blue (#A3CEF1)
Accent (Alerts): Red (#E63946)
Neutral Text: Dark Gray (#333333)
```

**Purpose-Driven Colors:**
```
Success/Positive: Green (#2E7D32)
Warning: Yellow/Orange (#FFA726)
Error/Negative: Red (#C62828)
Info: Blue (#1976D2)
Neutral: Gray (#757575)
```

### Semantic Colors

**Traffic Light System:**
```
🟢 Green: On Track (≥ 100% of target)
🟡 Yellow: At Risk (80-99% of target)
🔴 Red: Critical (< 80% of target)
```

**Alternative (Color-Blind Safe):**
```
✓ Blue: On Track
⚠ Orange: At Risk
✕ Red: Critical
```

### Background Colors

**Best Practices:**
- **Light backgrounds preferred** (white, light gray)
- Dark backgrounds for large displays (less eye strain)
- Avoid pure white (#FFFFFF) → Use off-white (#F8F8F8)
- Sufficient contrast with text and charts

**Card Backgrounds:**
```
Default: White (#FFFFFF)
Emphasis: Light Color (#E3F2FD - light blue)
Alert: Light Red (#FFEBEE)
Success: Light Green (#E8F5E9)
```

## Performance Considerations

### Loading States

**Progressive Loading:**
1. Show skeleton screens or placeholders
2. Load KPIs first (fast queries)
3. Load main charts next
4. Load detailed tables last

**Loading Indicators:**
```
┌─────────────────────┐
│ ⟳ Loading...        │
│ ▮▮▮▮▯▯▯▯▯▯ 40%     │
└─────────────────────┘
```

**Perceived Performance:**
- Show something immediately (even if placeholder)
- Animate transitions smoothly
- Provide feedback for all actions
- Show time estimate for long operations

### Data Refresh

**Update Strategies:**
1. **Full Refresh:** Reload entire dashboard
2. **Incremental:** Update only changed data
3. **Polling:** Check for updates periodically
4. **Push:** Server sends updates when ready

**User Controls:**
```
[Auto-refresh: ✓ ON]  [Interval: 5 min ▼]  [Refresh Now]
Last updated: 2 minutes ago
```

### Optimization Techniques

**Data:**
- Aggregate at database level
- Cache frequently accessed queries
- Use indexed columns for filters
- Limit row count (pagination)
- Pre-calculate complex metrics

**Rendering:**
- Lazy load off-screen charts
- Use canvas for large datasets (>10K points)
- Debounce filter changes (wait 300ms before applying)
- Virtualize long lists/tables

## Accessibility

### Keyboard Navigation

**Requirements:**
- All interactive elements accessible via Tab key
- Enter/Space activates buttons
- Arrow keys navigate within components
- Esc closes modals/dropdowns

**Focus Indicators:**
```css
/* Visible focus outline */
:focus {
    outline: 2px solid #2E86AB;
    outline-offset: 2px;
}
```

### Screen Reader Support

**ARIA Labels:**
```html
<div role="img" aria-label="Bar chart showing sales by region. North region leads with 450 units.">
    [Chart visualization]
</div>
```

**Alt Text for Charts:**
- Describe the chart type
- State the key insight
- Provide data table alternative

### Text Alternatives

**Provide:**
- Data tables for all charts
- CSV export option
- Text summary of key findings
- High-contrast mode option

## Mobile Dashboard Design

### Mobile-First Principles

**Simplify:**
- Show 3-4 KPIs maximum
- Single-column layout
- Larger touch targets (44×44px minimum)
- Collapsible sections

**Mobile Layout Pattern:**
```
┌─────────────────────┐
│  Header / Filters   │
├─────────────────────┤
│  Primary KPI        │
├─────────────────────┤
│  Chart 1 (Full)     │
├─────────────────────┤
│  Chart 2 (Full)     │
├─────────────────────┤
│  [Show More]        │
└─────────────────────┘
```

### Responsive Charts

**Adaptation Strategies:**
1. **Simplify:** Fewer data points, remove details
2. **Rotate:** Horizontal bar → Vertical bar
3. **Replace:** Complex chart → Simple chart or table
4. **Hide:** Remove non-essential charts

**Mobile Chart Sizes:**
```
Full Width: 100% (min 320px)
Height: 250-300px (landscape oriented)
```

## Dashboard Best Practices Checklist

### ✓ Content

- [ ] Clear purpose and target audience identified
- [ ] 5-9 visualizations maximum per screen
- [ ] Most important metrics prominent (top-left)
- [ ] Key insights annotated or highlighted
- [ ] All metrics have clear labels and units
- [ ] Data sources and update times shown

### ✓ Design

- [ ] Consistent color palette (≤5 colors)
- [ ] Adequate whitespace (not cramped)
- [ ] Aligned to grid system
- [ ] Consistent fonts and sizes
- [ ] Sufficient contrast (4.5:1 text, 3:1 graphics)
- [ ] Works on target screen sizes

### ✓ Usability

- [ ] Loads in <3 seconds (initial view)
- [ ] Filters are intuitive and well-placed
- [ ] Interactive elements have hover states
- [ ] Tooltips provide additional context
- [ ] Mobile-responsive (if needed)
- [ ] Keyboard accessible

### ✓ Accuracy

- [ ] Data is current and correct
- [ ] Axes start at appropriate values
- [ ] Time periods are consistent
- [ ] Comparisons are fair (same time periods, normalized)
- [ ] Sample sizes indicated where relevant

## Common Dashboard Mistakes

### ❌ 1. Too Much Information

**Problem:** Overwhelming, hard to find insights
**Solution:** Limit to 5-9 key metrics, use drill-down for details

### ❌ 2. No Visual Hierarchy

**Problem:** All elements compete for attention
**Solution:** Vary size, color, and position to guide eye

### ❌ 3. Inconsistent Styling

**Problem:** Looks unprofessional, confusing
**Solution:** Create and follow a style guide

### ❌ 4. Poor Color Choices

**Problem:** Inaccessible, meaningless colors
**Solution:** Use purpose-driven colors, test for color blindness

### ❌ 5. No Context

**Problem:** Can't tell if metrics are good or bad
**Solution:** Show targets, comparisons, trends

### ❌ 6. Inappropriate Chart Types

**Problem:** Misleading or hard to read
**Solution:** Follow chart selection guidelines

### ❌ 7. No Mobile Support

**Problem:** Unusable on phones/tablets
**Solution:** Responsive design or separate mobile dashboard

### ❌ 8. Slow Loading

**Problem:** Users lose patience, switch away
**Solution:** Optimize queries, show loading states, progressive loading

## Dashboard Examples by Industry

### E-Commerce

**Key Metrics:**
- Revenue, Orders, AOV (Average Order Value)
- Conversion Rate, Cart Abandonment
- Customer Acquisition Cost (CAC)

**Charts:**
- Revenue trend (line chart)
- Traffic sources (stacked bar)
- Top products (horizontal bar)
- Geographic heat map

### SaaS

**Key Metrics:**
- MRR (Monthly Recurring Revenue), Churn Rate
- Active Users (DAU/MAU)
- Customer Lifetime Value (LTV)

**Charts:**
- MRR trend with cohorts (area chart)
- User growth (line chart)
- Churn rate by segment (grouped bar)
- Feature adoption (funnel)

### Manufacturing

**Key Metrics:**
- Production Volume, Cycle Time
- Quality Defect Rate, OEE (Overall Equipment Effectiveness)
- Inventory Levels

**Charts:**
- Production by line (stacked bar)
- Downtime analysis (waterfall)
- Quality trends (control chart)
- Inventory status (bullet charts)

### Financial Services

**Key Metrics:**
- Assets Under Management (AUM), ROI
- Client Acquisition, Retention Rate
- Compliance Metrics

**Charts:**
- Portfolio performance (line chart with benchmark)
- Asset allocation (tree map)
- Risk distribution (heat map)
- Client growth (area chart)

## Tools and Frameworks

**Python:**
- **Plotly Dash:** Full-featured framework
- **Streamlit:** Rapid prototyping
- **Panel (HoloViz):** Flexible, works with multiple viz libraries
- **Voila:** Turn Jupyter notebooks into dashboards

**JavaScript:**
- **D3.js:** Full control, steep learning curve
- **Chart.js + Dashboard template:** Quick setup
- **Apache ECharts:** Feature-rich, good docs
- **Highcharts:** Commercial, excellent support

**BI Tools:**
- **Tableau:** Drag-and-drop, powerful
- **Power BI:** Microsoft ecosystem, affordable
- **Looker (Google):** SQL-based, enterprise
- **Metabase:** Open-source, simple
- **Grafana:** Time-series focused, monitoring

**Design Tools:**
- **Figma:** Collaborative, prototyping
- **Sketch:** Mac-only, design systems
- **Adobe XD:** Prototyping, Adobe integration

## References

**Books:**
- "Information Dashboard Design" by Stephen Few
- "The Big Book of Dashboards" by Steve Wexler et al.
- "Designing Data-Intensive Applications" by Martin Kleppmann

**Online Resources:**
- Dashboard Design Patterns (UI Patterns)
- Real-world dashboard examples (Dribbble, Behance)
- Dashboard Best Practices (Tableau, Power BI docs)
