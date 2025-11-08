# Chart Selection Guide

## Overview

Choosing the right chart type is critical for effective data communication. This guide helps you select the most appropriate visualization based on your data type and communication goal.

## Decision Framework

### Step 1: What is Your Goal?

- **Compare** values across categories or groups
- **Show distribution** of a variable
- **Reveal relationship** between two or more variables
- **Display composition** (parts of a whole)
- **Track change** over time
- **Analyze geographic** patterns
- **Show hierarchy** or flow

### Step 2: How Many Variables?

- **One variable:** Distribution, frequency
- **Two variables:** Relationship, comparison
- **Three+ variables:** Multidimensional analysis
- **Time series:** Temporal patterns

### Step 3: How Many Data Points?

- **Few (<20):** Most chart types work
- **Medium (20-100):** Consider aggregation or small multiples
- **Many (>100):** Density plots, aggregation, sampling, or interactive charts

## Chart Types by Purpose

### 1. COMPARISON

#### Bar Chart (Vertical/Horizontal)

**Best For:**
- Comparing values across categories
- Ranking items
- Showing changes between two time periods

**When to Use:**
- Discrete categories (not continuous data)
- Want precise value comparison
- Need to emphasize differences

**Variants:**
- **Grouped Bar:** Compare subcategories within main categories
- **Stacked Bar:** Show composition + comparison
- **Horizontal Bar:** Long category names, ranking display

**Best Practices:**
- Always start Y-axis at zero
- Order bars logically (by value, alphabetically, or chronologically)
- Limit to 10-12 bars (use horizontal if more)
- Use consistent color unless highlighting specific bar

**Example Use Cases:**
```
✅ Sales by product category
✅ Customer satisfaction by region
✅ Budget vs. actual by department
✅ Top 10 performing stores
```

**Code Example:**
```python
import matplotlib.pyplot as plt
import seaborn as sns

categories = ['Product A', 'Product B', 'Product C', 'Product D']
values = [245, 187, 312, 156]

plt.figure(figsize=(10, 6))
bars = plt.bar(categories, values, color='#2E86AB', edgecolor='black', alpha=0.8)
# Highlight maximum
bars[values.index(max(values))].set_color('#E63946')

plt.ylabel('Sales (Units)', fontsize=12)
plt.title('Product Sales Comparison Q4 2024', fontsize=14, fontweight='bold')
plt.grid(axis='y', alpha=0.3)
plt.tight_layout()
```

#### Column Chart

**Best For:** Same as bar chart, but vertical orientation
**Prefer When:** Time-based comparisons (months, quarters, years)

#### Lollipop Chart

**Best For:**
- Cleaner alternative to bar chart
- When exact values are labeled
- Reduces visual clutter

**Code Example:**
```python
plt.figure(figsize=(10, 6))
plt.hlines(y=range(len(categories)), xmin=0, xmax=values, color='gray', alpha=0.4)
plt.plot(values, range(len(categories)), 'o', markersize=10, color='#2E86AB')
plt.yticks(range(len(categories)), categories)
plt.xlabel('Sales (Units)')
plt.title('Product Sales - Lollipop Chart')
```

#### Bullet Chart

**Best For:**
- Comparing actual vs. target/budget
- Showing performance against benchmarks
- Executive dashboards

**Components:**
- Main bar (actual value)
- Target line (goal)
- Shaded ranges (poor/satisfactory/good)

### 2. DISTRIBUTION

#### Histogram

**Best For:**
- Understanding distribution of continuous variable
- Identifying skewness, modality
- Detecting outliers

**Best Practices:**
- Choose appropriate bin size (Sturges' rule: bins ≈ 1 + log₂(n))
- Show density curve (KDE) for smoothed view
- Include mean/median lines
- Label axes with units

**Code Example:**
```python
plt.figure(figsize=(10, 6))
plt.hist(data, bins=30, edgecolor='black', alpha=0.7, color='#2E86AB', density=True)
# Add KDE
from scipy import stats
density = stats.gaussian_kde(data)
x_range = np.linspace(data.min(), data.max(), 100)
plt.plot(x_range, density(x_range), 'r-', linewidth=2, label='KDE')
# Add mean line
plt.axvline(data.mean(), color='green', linestyle='--', linewidth=2, label=f'Mean: {data.mean():.2f}')
plt.xlabel('Value')
plt.ylabel('Density')
plt.legend()
plt.title('Distribution of Customer Age')
```

#### Box Plot (Box-and-Whisker)

**Best For:**
- Quick summary statistics (median, quartiles, outliers)
- Comparing distributions across groups
- Detecting outliers

**Components:**
- Box: IQR (25th to 75th percentile)
- Line in box: Median
- Whiskers: Extend to 1.5 × IQR
- Points: Outliers beyond whiskers

**When to Use:**
- Compare multiple distributions
- Focus on median and spread, not shape
- Identify outliers

**Code Example:**
```python
plt.figure(figsize=(10, 6))
bp = plt.boxplot([group1, group2, group3], labels=['Group A', 'Group B', 'Group C'],
                  patch_artist=True, notch=True)
for patch in bp['boxes']:
    patch.set_facecolor('#2E86AB')
    patch.set_alpha(0.7)
plt.ylabel('Value')
plt.title('Distribution Comparison Across Groups')
plt.grid(axis='y', alpha=0.3)
```

#### Violin Plot

**Best For:**
- Showing full distribution shape
- Combining benefits of box plot and density plot
- Comparing distributions

**Advantage Over Box Plot:** Shows multimodal distributions

**Code Example:**
```python
import seaborn as sns
plt.figure(figsize=(10, 6))
sns.violinplot(data=df, x='category', y='value', palette='Set2', inner='quartile')
plt.title('Value Distribution by Category')
```

#### Density Plot (KDE)

**Best For:**
- Smooth distribution representation
- Comparing multiple distributions on same plot
- When sample size is large

**Best Practices:**
- Adjust bandwidth for smoothing
- Use transparency (alpha) when overlaying multiple distributions

### 3. RELATIONSHIP

#### Scatter Plot

**Best For:**
- Showing relationship between two continuous variables
- Identifying correlation, clusters, outliers
- Revealing patterns and trends

**Enhancements:**
- **Size:** Add third variable (bubble chart)
- **Color:** Add fourth variable (hue)
- **Trend line:** Show correlation
- **Annotations:** Label outliers or interesting points

**Code Example:**
```python
plt.figure(figsize=(10, 6))
scatter = plt.scatter(x, y, c=categories, s=sizes, alpha=0.6, cmap='viridis', edgecolors='black')
# Add trend line
z = np.polyfit(x, y, 1)
p = np.poly1d(z)
plt.plot(x, p(x), "r--", linewidth=2, label=f'Trend: y={z[0]:.2f}x+{z[1]:.2f}')
plt.xlabel('Marketing Spend ($)')
plt.ylabel('Revenue ($)')
plt.title('Marketing Spend vs Revenue')
plt.colorbar(scatter, label='Product Category')
plt.legend()
```

#### Line Chart

**Best For:**
- Showing trends over time
- Multiple time series comparison
- Continuous data

**Best Practices:**
- Time on X-axis (left to right)
- Start Y-axis at zero (unless showing small variations)
- Use different line styles for multiple series
- Maximum 5-7 lines (more becomes cluttered)
- Highlight important series with color/thickness

**Code Example:**
```python
plt.figure(figsize=(12, 6))
plt.plot(dates, series1, linewidth=2, color='#2E86AB', label='Product A')
plt.plot(dates, series2, linewidth=2, color='#E63946', label='Product B', linestyle='--')
# Shade recession periods
plt.axvspan(recession_start, recession_end, alpha=0.2, color='gray', label='Recession')
plt.xlabel('Date')
plt.ylabel('Sales (Units)')
plt.title('Product Sales Over Time')
plt.legend()
plt.grid(alpha=0.3)
```

#### Heat Map

**Best For:**
- Correlation matrices
- Time-based patterns (day of week × hour)
- Showing intensity across two categorical dimensions

**Color Choice:**
- **Sequential:** Single metric (light to dark)
- **Diverging:** Positive/negative values (red-white-blue)

**Code Example:**
```python
import seaborn as sns
plt.figure(figsize=(10, 8))
sns.heatmap(correlation_matrix, annot=True, fmt='.2f', cmap='RdBu_r',
            center=0, square=True, linewidths=1, cbar_kws={'label': 'Correlation'})
plt.title('Feature Correlation Matrix')
```

#### Bubble Chart

**Best For:**
- Three-dimensional data (X, Y, size)
- Showing magnitude with position

**Caution:** Hard to compare bubble sizes accurately

### 4. COMPOSITION (Parts of Whole)

#### Pie Chart

**Best For:**
- Showing simple proportions (2-5 segments)
- When exact values aren't critical
- Single snapshot in time

**⚠️ Use Sparingly:**
- Hard to compare angles
- Difficult with many categories
- Consider bar chart instead

**When Acceptable:**
- 2-3 categories only
- One segment is dominant (>50%)
- Showing market share or percentage breakdown

**Best Practices:**
- Order from largest to smallest
- Start at 12 o'clock position
- Limit to 5 segments maximum
- Label with percentages
- Consider donut chart for cleaner look

**Code Example:**
```python
plt.figure(figsize=(8, 8))
colors = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D']
explode = (0.05, 0, 0, 0)  # Emphasize largest segment
plt.pie(values, labels=labels, autopct='%1.1f%%', startangle=90,
        colors=colors, explode=explode, shadow=False)
plt.title('Market Share by Competitor')
```

#### Stacked Bar Chart

**Best For:**
- Comparing total and composition across categories
- Showing subcategory contributions
- Time-based composition

**Types:**
- **Stacked (Absolute):** Show total and parts
- **100% Stacked:** Show proportions only

**Best Practices:**
- Order segments logically (largest to smallest)
- Limit to 4-5 segments
- Use consistent colors across charts
- Consider grouped bar if comparison is priority

**Code Example:**
```python
plt.figure(figsize=(12, 6))
bottom = np.zeros(len(categories))
for i, segment in enumerate(segments):
    plt.bar(categories, values[segment], bottom=bottom,
            label=segment, color=colors[i], edgecolor='white')
    bottom += values[segment]
plt.ylabel('Sales ($)')
plt.xlabel('Quarter')
plt.title('Sales Composition by Product Line')
plt.legend(title='Product')
```

#### Tree Map

**Best For:**
- Hierarchical data with many categories
- Space-efficient composition
- Showing nested proportions

**Best Practices:**
- Use area to encode value
- Use color to encode category or metric
- Limit depth to 2-3 levels
- Label largest rectangles only

#### Waterfall Chart

**Best For:**
- Showing cumulative effect of sequential values
- Bridge between starting and ending values
- Financial analysis (P&L breakdown)

**Components:**
- Starting value
- Incremental increases/decreases
- Ending value

**Code Example:**
```python
import matplotlib.pyplot as plt

categories = ['Start', '+Revenue', '-COGS', '-OpEx', '-Tax', 'End']
values = [100, 50, -30, -15, -5, 100]  # Cumulative

# Calculate positions
cumsum = np.cumsum([0] + values[:-1])

plt.figure(figsize=(12, 6))
colors = ['gray' if i == 0 or i == len(values)-1 else
          'green' if v > 0 else 'red' for i, v in enumerate(values)]
plt.bar(range(len(categories)), values, bottom=cumsum, color=colors, edgecolor='black')
plt.xticks(range(len(categories)), categories)
plt.ylabel('Value ($M)')
plt.title('Profit Waterfall Analysis')
plt.grid(axis='y', alpha=0.3)
```

### 5. TIME SERIES

#### Line Chart

**Best For:** Continuous time series, trends over time (see above)

#### Area Chart

**Best For:**
- Showing cumulative totals over time
- Emphasizing magnitude of change
- Volume or quantity over time

**Types:**
- **Simple Area:** Single metric
- **Stacked Area:** Multiple metrics (composition over time)

**Best Practices:**
- Use transparency for overlapping areas
- Order series from least to most volatile
- Consider line chart if area obscures data

**Code Example:**
```python
plt.figure(figsize=(12, 6))
plt.fill_between(dates, 0, values, alpha=0.3, color='#2E86AB', label='Sales Volume')
plt.plot(dates, values, color='#2E86AB', linewidth=2)
plt.xlabel('Date')
plt.ylabel('Units Sold')
plt.title('Monthly Sales Volume')
plt.legend()
plt.grid(alpha=0.3)
```

#### Sparklines

**Best For:**
- Showing trends in compact space
- Dashboard metrics
- In-line with text or tables

**Characteristics:**
- Small (1-2 inches wide)
- No axes labels
- Minimal decoration
- Shows trend, not precise values

#### Calendar Heat Map

**Best For:**
- Daily patterns over long periods
- Activity tracking (GitHub contributions style)
- Identifying weekly/monthly patterns

### 6. GEOGRAPHIC

#### Choropleth Map

**Best For:**
- Regional comparisons
- Geographic distribution of metrics
- Administrative boundaries

**Best Practices:**
- Use sequential or diverging color palette
- Normalize by population/area when appropriate
- Include legend and scale
- Consider population cartogram for fairness

#### Symbol Map (Bubble Map)

**Best For:**
- Showing values at specific locations
- Comparing magnitudes across geography
- Point data (cities, stores)

**Components:**
- Base map
- Circles scaled by value
- Color can encode additional dimension

#### Flow Map

**Best For:**
- Origin-destination data
- Migration patterns
- Trade routes

**Characteristics:**
- Arrows show direction
- Line thickness shows volume

### 7. HIERARCHY

#### Tree Diagram

**Best For:**
- Organizational charts
- Taxonomies
- Decision trees

#### Sunburst Diagram

**Best For:**
- Hierarchical proportions
- Multi-level composition
- Drill-down visualization

**Advantage Over Tree Map:** Shows hierarchy more clearly

#### Dendrogram

**Best For:**
- Clustering results
- Hierarchical relationships
- Phylogenetic trees

### 8. MULTIVARIATE

#### Parallel Coordinates

**Best For:**
- Comparing across many dimensions
- Finding patterns in high-dimensional data
- Visualizing trade-offs

**Best Practices:**
- Normalize scales
- Order dimensions logically
- Use color to highlight patterns
- Limit to <10 dimensions

#### Radar/Spider Chart

**Best For:**
- Comparing profiles across multiple dimensions
- Showing strengths/weaknesses
- Skills or performance assessment

**⚠️ Caution:**
- Hard to read with many variables
- Area can be misleading
- Consider small multiples of bar charts instead

**When Appropriate:**
- 3-8 dimensions
- Comparing 2-3 entities
- Dimensions are comparable

#### Small Multiples (Facets)

**Best For:**
- Comparing patterns across groups
- Avoiding cluttered single chart
- Standardizing comparisons

**Trellis/Facet Grid Pattern:**
```python
import seaborn as sns
g = sns.FacetGrid(df, col='category', col_wrap=3, height=4)
g.map(plt.scatter, 'x', 'y', alpha=0.6)
g.set_titles('{col_name}')
g.set_axis_labels('X Variable', 'Y Variable')
```

## Chart Selection Decision Tree

```
START: What do you want to show?

1. COMPARISON (Across Categories)
   ├─ Few categories (<10) → Bar Chart
   ├─ Many categories (>10) → Horizontal Bar Chart (top 10) or Lollipop
   ├─ Multiple groups → Grouped Bar Chart
   └─ Parts + Total → Stacked Bar Chart

2. DISTRIBUTION (One Variable)
   ├─ Continuous → Histogram + KDE
   ├─ Quick summary → Box Plot
   ├─ Full shape → Violin Plot
   └─ Compare groups → Box Plot or Violin Plot

3. RELATIONSHIP (Two Variables)
   ├─ Both continuous → Scatter Plot
   ├─ Add 3rd variable → Bubble Chart (size) or Color
   ├─ Time series → Line Chart
   ├─ Correlation → Heat Map
   └─ Many variables → Parallel Coordinates

4. COMPOSITION (Parts of Whole)
   ├─ Simple (2-3 parts) → Pie Chart or Donut
   ├─ Across categories → Stacked Bar
   ├─ Across time → Stacked Area
   ├─ Hierarchy → Tree Map or Sunburst
   └─ Sequential changes → Waterfall Chart

5. TIME SERIES
   ├─ Single metric → Line Chart
   ├─ Volume/cumulative → Area Chart
   ├─ Multiple metrics → Line Chart (max 5 lines)
   ├─ Compact trend → Sparkline
   └─ Daily patterns → Calendar Heat Map

6. GEOGRAPHIC
   ├─ By region → Choropleth Map
   ├─ By location → Symbol/Bubble Map
   └─ Flow → Flow Map

7. HIERARCHY
   ├─ Org structure → Tree Diagram
   ├─ Proportions → Sunburst or Tree Map
   └─ Clustering → Dendrogram
```

## Common Combinations

### Dashboard Layouts

**Executive Dashboard:**
```
Row 1: KPI Cards (4-6 metrics with sparklines)
Row 2: Main Insight (Large area chart or line chart)
Row 3: Supporting Details (2 bar charts or 1 table + 1 chart)
Row 4: Geographical View (Map with key regions highlighted)
```

**Operations Dashboard:**
```
Left: Real-time metrics (Gauge charts or number cards)
Center: Time series (Line chart with annotations)
Right: Status breakdown (Stacked bar or tree map)
Bottom: Detailed table with filtering
```

**Sales Dashboard:**
```
Top: Sales by Region (Map)
Middle Left: Top Products (Horizontal bar)
Middle Right: Sales Trend (Line chart)
Bottom: Sales by Channel (Stacked bar, 100%)
```

## When NOT to Use Certain Charts

### ❌ Avoid 3D Charts
**Why:** Perspective distortion, hard to read values accurately
**Use Instead:** 2D equivalents with proper visual encoding

### ❌ Avoid Pie Charts (Usually)
**Why:** Angles hard to compare, especially with many slices
**Use Instead:** Horizontal bar chart (easier comparison)

### ❌ Avoid Dual Y-Axes
**Why:** Can mislead by suggesting correlation
**Use Instead:** Indexed values (both start at 100) or separate charts

### ❌ Avoid Radar Charts (Usually)
**Why:** Area can mislead, hard to read
**Use Instead:** Small multiples of bar charts or parallel coordinates

### ❌ Avoid Too Many Colors
**Why:** Overwhelming, hard to distinguish
**Use Instead:** Grayscale + 1-2 accent colors for emphasis

## Quick Reference Table

| Goal | Data Type | Best Chart | Alternative |
|------|-----------|-----------|-------------|
| Compare categories | Categorical | Bar Chart | Lollipop, Dot Plot |
| Show distribution | Continuous | Histogram + KDE | Box Plot, Violin Plot |
| Show relationship | 2 Continuous | Scatter Plot | Line Chart (if time) |
| Show composition | Categorical | Stacked Bar | Tree Map, Pie (if 2-3 parts) |
| Show trend | Time Series | Line Chart | Area Chart |
| Show parts of whole | Categorical | 100% Stacked Bar | Pie Chart (if simple) |
| Compare profiles | Multiple Dimensions | Small Multiples | Parallel Coordinates |
| Show geography | Location Data | Choropleth Map | Symbol Map |
| Show hierarchy | Hierarchical | Tree Map | Sunburst, Tree Diagram |
| Show deviation | From baseline | Diverging Bar | Bullet Chart |

## Tools and Libraries

**Python:**
- Matplotlib: Foundation, full control
- Seaborn: Statistical visualizations, beautiful defaults
- Plotly: Interactive charts
- Altair: Declarative grammar
- Bokeh: Interactive dashboards

**R:**
- ggplot2: Grammar of graphics
- plotly: Interactive
- shiny: Dashboards

**JavaScript:**
- D3.js: Full control, steep learning curve
- Chart.js: Simple, fast
- Highcharts: Feature-rich
- ECharts: Powerful, from Apache

**BI Tools:**
- Tableau: Drag-and-drop, powerful
- Power BI: Microsoft ecosystem
- Looker: SQL-based
- Qlik: Associative engine
