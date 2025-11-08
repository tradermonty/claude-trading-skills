"""
Professional Visualization Templates

Ready-to-use templates for common business visualizations with best practices built-in.

Usage:
    from visualization_templates import *

    # Create executive summary
    fig = executive_summary_template(data, metrics=['revenue', 'customers', 'retention'])

    # Create comparison chart
    fig = comparison_template(data, categories='product', values='sales', comparison='quarter')
"""

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np
from typing import List, Optional, Dict, Tuple

# Professional color palettes (colorblind-safe)
OKABE_ITO = {
    'orange': '#E69F00',
    'sky_blue': '#56B4E9',
    'bluish_green': '#009E73',
    'yellow': '#F0E442',
    'blue': '#0072B2',
    'vermillion': '#D55E00',
    'reddish_purple': '#CC79A7',
    'black': '#000000'
}

CORPORATE_BLUE = {
    'primary': '#003f5c',
    'secondary': '#2f4b7c',
    'accent1': '#f95d6a',
    'accent2': '#ffa600',
    'neutral': '#7f7f7f'
}

FINANCIAL = {
    'positive': '#2E7D32',  # Green
    'negative': '#C62828',  # Red
    'neutral': '#757575',   # Gray
    'primary': '#1565C0',   # Blue
    'secondary': '#F57C00'  # Orange
}


def setup_professional_style():
    """Apply consistent professional styling"""
    sns.set_style('whitegrid')
    plt.rcParams.update({
        'font.family': 'sans-serif',
        'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
        'font.size': 11,
        'axes.titlesize': 14,
        'axes.labelsize': 12,
        'axes.titleweight': 'bold',
        'figure.titlesize': 16,
        'figure.titleweight': 'bold',
        'grid.alpha': 0.3,
        'axes.facecolor': 'white',
        'figure.facecolor': 'white',
        'axes.edgecolor': '#333333'
    })


# ============================================================================
# EXECUTIVE TEMPLATES
# ============================================================================

def kpi_card(value, title, change_pct=None, sparkline_data=None, figsize=(3, 2.5)):
    """
    Create a KPI card with value, change indicator, and optional sparkline

    Args:
        value: Main KPI value
        title: KPI name
        change_pct: Percentage change (can be negative)
        sparkline_data: List/array of historical values for mini trend
        figsize: Figure size

    Returns:
        matplotlib Figure
    """
    setup_professional_style()
    fig, ax = plt.subplots(figsize=figsize)
    ax.axis('off')

    # Title
    ax.text(0.5, 0.92, title, ha='center', va='top',
            fontsize=12, fontweight='bold', transform=ax.transAxes, color='#333333')

    # Main value
    if value >= 1000000:
        value_str = f'{value/1000000:.2f}M'
    elif value >= 1000:
        value_str = f'{value/1000:.1f}K'
    else:
        value_str = f'{value:,.0f}'

    ax.text(0.5, 0.65, value_str, ha='center', va='center',
            fontsize=32, fontweight='bold', transform=ax.transAxes)

    # Change indicator
    if change_pct is not None:
        arrow = '↑' if change_pct > 0 else '↓' if change_pct < 0 else '→'
        color = FINANCIAL['positive'] if change_pct > 0 else FINANCIAL['negative'] if change_pct < 0 else FINANCIAL['neutral']
        ax.text(0.5, 0.42, f'{arrow} {abs(change_pct):.1f}%', ha='center', va='center',
                fontsize=14, color=color, transform=ax.transAxes)

    # Sparkline
    if sparkline_data is not None:
        ax_spark = fig.add_axes([0.15, 0.08, 0.7, 0.25])
        ax_spark.plot(sparkline_data, color='#666666', linewidth=1.5)
        ax_spark.fill_between(range(len(sparkline_data)), sparkline_data, alpha=0.2, color='#666666')
        ax_spark.axis('off')
        ax_spark.set_xlim(0, len(sparkline_data)-1)

    return fig


def executive_summary_template(
    kpis: List[Dict],
    title: str = "Executive Summary",
    subtitle: str = "",
    figsize: Tuple[int, int] = (16, 10)
) -> plt.Figure:
    """
    Create executive summary dashboard with KPI cards

    Args:
        kpis: List of dicts with keys: 'title', 'value', 'change_pct', 'sparkline'
        title: Dashboard title
        subtitle: Subtitle or date range
        figsize: Figure size

    Example:
        kpis = [
            {'title': 'Revenue', 'value': 1234567, 'change_pct': 12.5, 'sparkline': [100,105,102,108,115,120]},
            {'title': 'Customers', 'value': 5432, 'change_pct': 5.2, 'sparkline': [90,92,95,97,98,100]},
            {'title': 'Retention', 'value': 89.5, 'change_pct': 1.2, 'sparkline': [85,86,87,88,89,89.5]}
        ]
    """
    setup_professional_style()
    fig = plt.figure(figsize=figsize)

    # Title
    fig.text(0.5, 0.96, title, ha='center', va='top', fontsize=20, fontweight='bold')
    if subtitle:
        fig.text(0.5, 0.93, subtitle, ha='center', va='top', fontsize=12, color='#666666')

    # Calculate layout
    n_kpis = len(kpis)
    cols = min(n_kpis, 4)
    rows = (n_kpis + cols - 1) // cols

    card_width = 0.21
    card_height = 0.28
    h_spacing = 0.03
    v_spacing = 0.04

    start_x = 0.5 - (cols * (card_width + h_spacing) - h_spacing) / 2
    start_y = 0.85

    # Create KPI cards
    for i, kpi in enumerate(kpis):
        row = i // cols
        col = i % cols

        ax = fig.add_axes([
            start_x + col * (card_width + h_spacing),
            start_y - row * (card_height + v_spacing) - card_height,
            card_width,
            card_height
        ])
        ax.axis('off')

        # Border
        border = plt.Rectangle((0, 0), 1, 1, fill=False, edgecolor='#CCCCCC',
                               linewidth=2, transform=ax.transAxes)
        ax.add_patch(border)

        # Title
        ax.text(0.5, 0.88, kpi['title'], ha='center', va='top',
                fontsize=11, fontweight='bold', transform=ax.transAxes)

        # Value
        value = kpi['value']
        if value >= 1000000:
            value_str = f'{value/1000000:.2f}M'
        elif value >= 1000:
            value_str = f'{value/1000:.1f}K'
        else:
            value_str = f'{value:,.1f}'

        ax.text(0.5, 0.60, value_str, ha='center', va='center',
                fontsize=28, fontweight='bold', transform=ax.transAxes)

        # Change
        change_pct = kpi.get('change_pct', 0)
        arrow = '↑' if change_pct > 0 else '↓' if change_pct < 0 else '→'
        color = FINANCIAL['positive'] if change_pct > 0 else FINANCIAL['negative'] if change_pct < 0 else FINANCIAL['neutral']
        ax.text(0.5, 0.38, f'{arrow} {abs(change_pct):.1f}%', ha='center', va='center',
                fontsize=13, color=color, transform=ax.transAxes)

        # Sparkline
        if 'sparkline' in kpi and kpi['sparkline']:
            ax_spark = fig.add_axes([
                start_x + col * (card_width + h_spacing) + 0.03,
                start_y - row * (card_height + v_spacing) - card_height + 0.03,
                card_width - 0.06,
                0.10
            ])
            data = kpi['sparkline']
            ax_spark.plot(data, color='#666666', linewidth=1.5)
            ax_spark.fill_between(range(len(data)), data, alpha=0.15, color='#666666')
            ax_spark.axis('off')

    return fig


# ============================================================================
# COMPARISON TEMPLATES
# ============================================================================

def comparison_bar_template(
    data: pd.DataFrame,
    category_col: str,
    value_col: str,
    title: str = "",
    highlight_max: bool = True,
    target_line: Optional[float] = None,
    figsize: Tuple[int, int] = (10, 6)
) -> plt.Figure:
    """
    Create comparison bar chart with best practices

    Args:
        data: DataFrame
        category_col: Column for categories
        value_col: Column for values
        title: Chart title
        highlight_max: Highlight the maximum value
        target_line: Add horizontal target line
        figsize: Figure size
    """
    setup_professional_style()
    fig, ax = plt.subplots(figsize=figsize)

    # Sort by value for better readability
    df = data.sort_values(value_col, ascending=True)

    # Create bars
    colors = [CORPORATE_BLUE['primary']] * len(df)
    if highlight_max:
        max_idx = df[value_col].idxmax()
        colors[list(df.index).index(max_idx)] = CORPORATE_BLUE['accent1']

    bars = ax.barh(df[category_col], df[value_col], color=colors, edgecolor='black', alpha=0.8)

    # Add value labels
    for i, (idx, row) in enumerate(df.iterrows()):
        value = row[value_col]
        ax.text(value + max(df[value_col]) * 0.02, i, f'{value:,.0f}',
                va='center', fontsize=10, fontweight='bold')

    # Target line
    if target_line:
        ax.axvline(target_line, color=FINANCIAL['neutral'], linestyle='--',
                   linewidth=2, label=f'Target: {target_line:,.0f}', alpha=0.7)
        ax.legend(loc='lower right')

    ax.set_xlabel(value_col, fontweight='bold')
    ax.set_ylabel('')

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    ax.grid(axis='x', alpha=0.3)
    ax.spines['top'].set_visible(False)
    ax.spines('right'].set_visible(False)

    plt.tight_layout()
    return fig


def grouped_comparison_template(
    data: pd.DataFrame,
    category_col: str,
    value_col: str,
    group_col: str,
    title: str = "",
    figsize: Tuple[int, int] = (12, 6)
) -> plt.Figure:
    """
    Create grouped bar chart for comparing groups across categories

    Args:
        data: DataFrame
        category_col: Column for main categories (x-axis)
        value_col: Column for values
        group_col: Column for grouping (different bars)
        title: Chart title
        figsize: Figure size
    """
    setup_professional_style()
    fig, ax = plt.subplots(figsize=figsize)

    # Pivot data for grouped bars
    pivot = data.pivot(index=category_col, columns=group_col, values=value_col)

    # Create grouped bars
    x = np.arange(len(pivot.index))
    width = 0.8 / len(pivot.columns)

    colors = list(OKABE_ITO.values())[:len(pivot.columns)]

    for i, (col, color) in enumerate(zip(pivot.columns, colors)):
        offset = width * i - width * (len(pivot.columns) - 1) / 2
        ax.bar(x + offset, pivot[col], width, label=col, color=color,
               edgecolor='black', alpha=0.8)

    ax.set_xlabel(category_col, fontweight='bold')
    ax.set_ylabel(value_col, fontweight='bold')
    ax.set_xticks(x)
    ax.set_xticklabels(pivot.index, rotation=45, ha='right')

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    ax.legend(title=group_col, frameon=True, shadow=True)
    ax.grid(axis='y', alpha=0.3)

    plt.tight_layout()
    return fig


# ============================================================================
# TREND TEMPLATES
# ============================================================================

def trend_with_forecast_template(
    historical_data: pd.Series,
    forecast_data: Optional[pd.Series] = None,
    confidence_lower: Optional[pd.Series] = None,
    confidence_upper: Optional[pd.Series] = None,
    title: str = "",
    ylabel: str = "",
    figsize: Tuple[int, int] = (12, 6)
) -> plt.Figure:
    """
    Create trend line with optional forecast and confidence intervals

    Args:
        historical_data: Historical time series (pd.Series with datetime index)
        forecast_data: Forecasted values (optional)
        confidence_lower: Lower confidence bound (optional)
        confidence_upper: Upper confidence bound (optional)
        title: Chart title
        ylabel: Y-axis label
        figsize: Figure size
    """
    setup_professional_style()
    fig, ax = plt.subplots(figsize=figsize)

    # Historical line
    ax.plot(historical_data.index, historical_data.values,
            color=CORPORATE_BLUE['primary'], linewidth=2.5, label='Historical', marker='o', markersize=4)

    # Forecast line
    if forecast_data is not None:
        ax.plot(forecast_data.index, forecast_data.values,
                color=CORPORATE_BLUE['accent2'], linewidth=2.5, linestyle='--',
                label='Forecast', marker='s', markersize=4)

        # Confidence interval
        if confidence_lower is not None and confidence_upper is not None:
            ax.fill_between(forecast_data.index, confidence_lower, confidence_upper,
                           color=CORPORATE_BLUE['accent2'], alpha=0.2, label='95% CI')

    # Vertical line separating historical and forecast
    if forecast_data is not None:
        sep_date = forecast_data.index[0]
        ax.axvline(sep_date, color='gray', linestyle=':', linewidth=2, alpha=0.5)
        ax.text(sep_date, ax.get_ylim()[1], ' Forecast →', ha='left', va='top',
                fontsize=10, color='gray')

    ax.set_ylabel(ylabel, fontweight='bold')
    ax.set_xlabel('Date', fontweight='bold')

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    ax.legend(loc='best', frameon=True, shadow=True)
    ax.grid(alpha=0.3)

    plt.xticks(rotation=45, ha='right')
    plt.tight_layout()
    return fig


# ============================================================================
# CORRELATION / RELATIONSHIP TEMPLATES
# ============================================================================

def correlation_heatmap_template(
    correlation_matrix: pd.DataFrame,
    title: str = "Correlation Matrix",
    figsize: Tuple[int, int] = (10, 8)
) -> plt.Figure:
    """
    Create professional correlation heatmap with annotations

    Args:
        correlation_matrix: Correlation matrix (DataFrame)
        title: Chart title
        figsize: Figure size
    """
    setup_professional_style()
    fig, ax = plt.subplots(figsize=figsize)

    # Create mask for upper triangle (optional: show only lower triangle)
    mask = np.triu(np.ones_like(correlation_matrix, dtype=bool))

    # Create heatmap
    sns.heatmap(correlation_matrix, mask=mask, annot=True, fmt='.2f',
                cmap='RdBu_r', center=0, square=True, linewidths=1,
                cbar_kws={'label': 'Correlation Coefficient', 'shrink': 0.8},
                vmin=-1, vmax=1, ax=ax)

    ax.set_title(title, fontweight='bold', pad=20)

    plt.tight_layout()
    return fig


# ============================================================================
# WATERFALL TEMPLATE
# ============================================================================

def waterfall_chart_template(
    categories: List[str],
    values: List[float],
    title: str = "Waterfall Analysis",
    start_label: str = "Start",
    end_label: str = "End",
    figsize: Tuple[int, int] = (12, 6)
) -> plt.Figure:
    """
    Create waterfall chart for sequential changes

    Args:
        categories: List of category names (including start and end)
        values: List of values (changes, first and last are totals)
        title: Chart title
        start_label: Label for starting value
        end_label: Label for ending value
        figsize: Figure size

    Example:
        categories = ['Start', '+Revenue', '-COGS', '-OpEx', 'End']
        values = [100, 50, -30, -15, 105]
    """
    setup_professional_style()
    fig, ax = plt.subplots(figsize=figsize)

    # Calculate cumulative positions
    cumsum = np.cumsum([0] + values[:-1])

    # Colors: gray for start/end, green for positive, red for negative
    colors = []
    for i, v in enumerate(values):
        if i == 0 or i == len(values) - 1:
            colors.append(FINANCIAL['neutral'])
        elif v > 0:
            colors.append(FINANCIAL['positive'])
        else:
            colors.append(FINANCIAL['negative'])

    # Create bars
    bars = ax.bar(range(len(categories)), values, bottom=cumsum,
                   color=colors, edgecolor='black', alpha=0.8)

    # Add connectors
    for i in range(len(categories) - 1):
        ax.plot([i + 0.4, i + 1 - 0.4],
                [cumsum[i] + values[i], cumsum[i] + values[i]],
                'k--', linewidth=1, alpha=0.5)

    # Add value labels
    for i, (cat, val, pos) in enumerate(zip(categories, values, cumsum)):
        if i == 0 or i == len(values) - 1:
            label_pos = pos + val / 2
        else:
            label_pos = pos + val + (5 if val > 0 else -5)

        ax.text(i, label_pos, f'{val:+.0f}' if i not in [0, len(values)-1] else f'{val:.0f}',
                ha='center', va='center', fontweight='bold', fontsize=10,
                bbox=dict(boxstyle='round,pad=0.3', facecolor='white', edgecolor='none', alpha=0.8))

    ax.set_xticks(range(len(categories)))
    ax.set_xticklabels(categories)
    ax.set_ylabel('Value', fontweight='bold')

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    ax.grid(axis='y', alpha=0.3)
    ax.axhline(0, color='black', linewidth=0.8)

    plt.tight_layout()
    return fig


# ============================================================================
# EXAMPLE USAGE
# ============================================================================

if __name__ == '__main__':
    # Example: KPI Card
    fig1 = kpi_card(
        value=1234567,
        title='Monthly Revenue',
        change_pct=12.5,
        sparkline_data=[100, 105, 102, 108, 115, 120, 123]
    )
    fig1.savefig('kpi_card_example.png', dpi=150, bbox_inches='tight')
    print("✅ Created kpi_card_example.png")

    # Example: Executive Summary
    kpis = [
        {'title': 'Revenue', 'value': 1234567, 'change_pct': 12.5, 'sparkline': [100,105,102,108,115,120]},
        {'title': 'Customers', 'value': 5432, 'change_pct': 5.2, 'sparkline': [90,92,95,97,98,100]},
        {'title': 'Retention %', 'value': 89.5, 'change_pct': 1.2, 'sparkline': [85,86,87,88,89,89.5]},
        {'title': 'NPS Score', 'value': 72, 'change_pct': 8.0, 'sparkline': [65,67,68,70,71,72]}
    ]
    fig2 = executive_summary_template(kpis, title='Q4 2024 Executive Summary', subtitle='October - December 2024')
    fig2.savefig('executive_summary_example.png', dpi=150, bbox_inches='tight')
    print("✅ Created executive_summary_example.png")

    # Example: Comparison Bar
    data = pd.DataFrame({
        'Product': ['Product A', 'Product B', 'Product C', 'Product D', 'Product E'],
        'Sales': [245, 187, 312, 156, 278]
    })
    fig3 = comparison_bar_template(data, 'Product', 'Sales',
                                   title='Product Sales Comparison',
                                   highlight_max=True, target_line=250)
    fig3.savefig('comparison_bar_example.png', dpi=150, bbox_inches='tight')
    print("✅ Created comparison_bar_example.png")

    # Example: Waterfall Chart
    fig4 = waterfall_chart_template(
        categories=['Q3 Revenue', '+New Sales', '+Upsells', '-Churn', '-Discounts', 'Q4 Revenue'],
        values=[100, 25, 15, -12, -8, 120],
        title='Q4 Revenue Bridge Analysis'
    )
    fig4.savefig('waterfall_example.png', dpi=150, bbox_inches='tight')
    print("✅ Created waterfall_example.png")

    plt.close('all')
    print("\n✅ All example templates created successfully!")
