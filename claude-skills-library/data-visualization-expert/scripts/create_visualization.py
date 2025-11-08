#!/usr/bin/env python3
"""
Professional Data Visualization Creator

This script creates publication-quality visualizations with best practices applied.

Usage:
    python create_visualization.py --type [chart_type] --input data.csv --output chart.png

Examples:
    python create_visualization.py --type bar --input sales.csv --x category --y value
    python create_visualization.py --type line --input timeseries.csv --x date --y revenue --hue product
    python create_visualization.py --type scatter --input data.csv --x feature1 --y feature2 --size value
    python create_visualization.py --type heatmap --input correlation.csv --output heatmap.png
    python create_visualization.py --type dashboard --input kpi_data.csv --output dashboard.png
"""

import argparse
import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from typing import Optional, List, Tuple

# Professional Style Configuration
STYLE_CONFIG = {
    'font.family': 'sans-serif',
    'font.sans-serif': ['Arial', 'Helvetica', 'DejaVu Sans'],
    'font.size': 11,
    'axes.titlesize': 14,
    'axes.labelsize': 12,
    'xtick.labelsize': 10,
    'ytick.labelsize': 10,
    'legend.fontsize': 10,
    'figure.titlesize': 16,
    'axes.grid': True,
    'grid.alpha': 0.3,
    'axes.facecolor': 'white',
    'figure.facecolor': 'white',
    'axes.edgecolor': '#333333',
    'axes.linewidth': 1.0,
}

# Professional Color Palettes
PALETTES = {
    'default': ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#6A994E', '#577590', '#F2CC8F'],
    'colorblind_safe': ['#E69F00', '#56B4E9', '#009E73', '#F0E442', '#0072B2', '#D55E00', '#CC79A7'],
    'tableau10': ['#4E79A7', '#F28E2B', '#E15759', '#76B7B2', '#59A14F', '#EDC948', '#B07AA1', '#FF9DA7'],
    'corporate': ['#003f5c', '#2f4b7c', '#665191', '#a05195', '#d45087', '#f95d6a', '#ff7c43', '#ffa600'],
    'sequential_blue': ['#f7fbff', '#deebf7', '#c6dbef', '#9ecae1', '#6baed6', '#4292c6', '#2171b5', '#084594'],
    'diverging_rdbu': ['#b2182b', '#d6604d', '#f4a582', '#fddbc7', '#d1e5f0', '#92c5de', '#4393c3', '#2166ac'],
    'positive_negative': ['#2E7D32', '#757575', '#C62828'],  # Green, Gray, Red
}

def setup_style(palette='default'):
    """Apply professional matplotlib style"""
    plt.style.use('seaborn-v0_8-whitegrid')
    for key, value in STYLE_CONFIG.items():
        plt.rcParams[key] = value
    return PALETTES.get(palette, PALETTES['default'])


def create_bar_chart(
    data: pd.DataFrame,
    x: str,
    y: str,
    hue: Optional[str] = None,
    horizontal: bool = False,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    palette: str = 'default',
    figsize: Tuple[int, int] = (10, 6),
    sort: bool = False,
    top_n: Optional[int] = None
) -> plt.Figure:
    """
    Create a professional bar chart

    Args:
        data: DataFrame with data
        x: Column for x-axis (categories)
        y: Column for y-axis (values)
        hue: Column for grouping (optional)
        horizontal: If True, creates horizontal bar chart
        title: Chart title
        xlabel, ylabel: Axis labels
        palette: Color palette name
        figsize: Figure size
        sort: If True, sort bars by value
        top_n: Show only top N categories
    """
    colors = setup_style(palette)
    fig, ax = plt.subplots(figsize=figsize)

    # Process data
    df = data.copy()
    if top_n:
        if hue:
            # Keep top N by grouped sum
            top_categories = df.groupby(x)[y].sum().nlargest(top_n).index
            df = df[df[x].isin(top_categories)]
        else:
            df = df.nlargest(top_n, y)

    if sort and not hue:
        df = df.sort_values(y)

    # Create chart
    if horizontal:
        if hue:
            sns.barplot(data=df, y=x, x=y, hue=hue, palette=colors, ax=ax, edgecolor='black', alpha=0.8)
        else:
            sns.barplot(data=df, y=x, x=y, color=colors[0], ax=ax, edgecolor='black', alpha=0.8)
        ax.set_xlabel(ylabel or y)
        ax.set_ylabel(xlabel or x)
    else:
        if hue:
            sns.barplot(data=df, x=x, y=y, hue=hue, palette=colors, ax=ax, edgecolor='black', alpha=0.8)
        else:
            sns.barplot(data=df, x=x, y=y, color=colors[0], ax=ax, edgecolor='black', alpha=0.8)
        ax.set_xlabel(xlabel or x)
        ax.set_ylabel(ylabel or y)
        plt.xticks(rotation=45, ha='right')

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    ax.grid(axis='x' if horizontal else 'y', alpha=0.3)

    if hue:
        ax.legend(title=hue, frameon=True, shadow=True)

    plt.tight_layout()
    return fig


def create_line_chart(
    data: pd.DataFrame,
    x: str,
    y: str,
    hue: Optional[str] = None,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    palette: str = 'default',
    figsize: Tuple[int, int] = (12, 6),
    markers: bool = False,
    show_area: bool = False
) -> plt.Figure:
    """Create a professional line chart"""
    colors = setup_style(palette)
    fig, ax = plt.subplots(figsize=figsize)

    df = data.copy()

    # Convert x to datetime if it looks like dates
    try:
        df[x] = pd.to_datetime(df[x])
    except:
        pass

    if hue:
        for i, category in enumerate(df[hue].unique()):
            subset = df[df[hue] == category].sort_values(x)
            color = colors[i % len(colors)]
            ax.plot(subset[x], subset[y], label=category, linewidth=2.5,
                   color=color, marker='o' if markers else None, markersize=5)
            if show_area:
                ax.fill_between(subset[x], 0, subset[y], alpha=0.2, color=color)
    else:
        df = df.sort_values(x)
        ax.plot(df[x], df[y], linewidth=2.5, color=colors[0],
               marker='o' if markers else None, markersize=5)
        if show_area:
            ax.fill_between(df[x], 0, df[y], alpha=0.2, color=colors[0])

    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    ax.grid(alpha=0.3)

    if hue:
        ax.legend(title=hue, frameon=True, shadow=True, loc='best')

    # Rotate x-axis labels if they're dates
    if pd.api.types.is_datetime64_any_dtype(df[x]):
        plt.xticks(rotation=45, ha='right')

    plt.tight_layout()
    return fig


def create_scatter_plot(
    data: pd.DataFrame,
    x: str,
    y: str,
    hue: Optional[str] = None,
    size: Optional[str] = None,
    title: str = "",
    xlabel: str = "",
    ylabel: str = "",
    palette: str = 'default',
    figsize: Tuple[int, int] = (10, 8),
    show_trendline: bool = False
) -> plt.Figure:
    """Create a professional scatter plot"""
    colors = setup_style(palette)
    fig, ax = plt.subplots(figsize=figsize)

    df = data.copy().dropna(subset=[x, y])

    # Prepare size parameter
    sizes = None
    if size:
        sizes = df[size]
        # Normalize sizes to reasonable range
        sizes = ((sizes - sizes.min()) / (sizes.max() - sizes.min()) * 500) + 50

    if hue:
        for i, category in enumerate(df[hue].unique()):
            subset = df[df[hue] == category]
            s = sizes[subset.index] if size else 100
            ax.scatter(subset[x], subset[y], s=s, alpha=0.6,
                      c=[colors[i % len(colors)]], edgecolors='black',
                      linewidth=0.5, label=category)
    else:
        s = sizes if size else 100
        ax.scatter(df[x], df[y], s=s, alpha=0.6,
                  c=colors[0], edgecolors='black', linewidth=0.5)

    # Add trendline
    if show_trendline:
        z = np.polyfit(df[x], df[y], 1)
        p = np.poly1d(z)
        ax.plot(df[x], p(df[x]), "r--", alpha=0.8, linewidth=2,
               label=f'Trend: y={z[0]:.2f}x+{z[1]:.2f}')

    ax.set_xlabel(xlabel or x)
    ax.set_ylabel(ylabel or y)

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    ax.grid(alpha=0.3)

    if hue or show_trendline:
        ax.legend(title=hue if hue else None, frameon=True, shadow=True)

    plt.tight_layout()
    return fig


def create_heatmap(
    data: pd.DataFrame,
    title: str = "",
    palette: str = 'diverging_rdbu',
    figsize: Tuple[int, int] = (10, 8),
    annot: bool = True,
    fmt: str = '.2f',
    vmin: Optional[float] = None,
    vmax: Optional[float] = None,
    center: Optional[float] = None
) -> plt.Figure:
    """Create a professional heatmap (e.g., correlation matrix)"""
    setup_style(palette)

    # Use seaborn's default for heatmap
    cmap = PALETTES.get(palette, 'RdBu_r')
    if isinstance(cmap, list):
        cmap = 'RdBu_r'  # Fallback to standard colormap

    fig, ax = plt.subplots(figsize=figsize)

    sns.heatmap(data, annot=annot, fmt=fmt, cmap=cmap,
                center=center, vmin=vmin, vmax=vmax,
                square=True, linewidths=1, cbar_kws={'label': 'Value'},
                ax=ax)

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    plt.tight_layout()
    return fig


def create_distribution_plot(
    data: pd.DataFrame,
    column: str,
    hue: Optional[str] = None,
    title: str = "",
    xlabel: str = "",
    palette: str = 'default',
    figsize: Tuple[int, int] = (12, 6),
    plot_type: str = 'hist'  # 'hist', 'kde', 'box', 'violin'
) -> plt.Figure:
    """Create distribution visualization"""
    colors = setup_style(palette)

    if plot_type in ['hist', 'kde']:
        fig, ax = plt.subplots(figsize=figsize)

        if hue:
            for i, category in enumerate(data[hue].unique()):
                subset = data[data[hue] == category][column].dropna()
                if plot_type == 'hist':
                    ax.hist(subset, bins=30, alpha=0.6, label=category,
                           color=colors[i % len(colors)], edgecolor='black')
                else:  # kde
                    subset.plot(kind='density', ax=ax, label=category,
                               color=colors[i % len(colors)], linewidth=2)
        else:
            if plot_type == 'hist':
                ax.hist(data[column].dropna(), bins=30, alpha=0.7,
                       color=colors[0], edgecolor='black')
                # Add KDE overlay
                data[column].dropna().plot(kind='density', ax=ax,
                                          color='red', linewidth=2, label='KDE')
            else:  # kde
                data[column].dropna().plot(kind='density', ax=ax,
                                          color=colors[0], linewidth=2)

        ax.set_xlabel(xlabel or column)
        ax.set_ylabel('Density' if plot_type == 'kde' else 'Frequency')

        if hue or plot_type == 'hist':
            ax.legend(frameon=True, shadow=True)

    elif plot_type in ['box', 'violin']:
        fig, ax = plt.subplots(figsize=figsize)

        if hue:
            if plot_type == 'box':
                sns.boxplot(data=data, x=hue, y=column, palette=colors, ax=ax)
            else:
                sns.violinplot(data=data, x=hue, y=column, palette=colors, ax=ax, inner='quartile')
            plt.xticks(rotation=45, ha='right')
        else:
            if plot_type == 'box':
                sns.boxplot(data=data, y=column, color=colors[0], ax=ax)
            else:
                sns.violinplot(data=data, y=column, color=colors[0], ax=ax, inner='quartile')

        ax.set_ylabel(column)

    if title:
        ax.set_title(title, fontweight='bold', pad=20)

    ax.grid(alpha=0.3)
    plt.tight_layout()
    return fig


def create_dashboard(
    data: pd.DataFrame,
    kpis: List[dict],
    charts: List[dict],
    title: str = "Dashboard",
    figsize: Tuple[int, int] = (16, 12)
) -> plt.Figure:
    """
    Create a dashboard with KPIs and multiple charts

    Args:
        data: DataFrame with data
        kpis: List of KPI dicts with keys: 'name', 'value', 'change_pct', 'sparkline_col'
        charts: List of chart configs with keys: 'type', 'x', 'y', 'title', etc.
        title: Dashboard title
        figsize: Figure size

    Example kpis:
        [
            {'name': 'Revenue', 'value': 1234567, 'change_pct': 12.5, 'sparkline_col': 'daily_revenue'},
            {'name': 'Customers', 'value': 5432, 'change_pct': -2.1, 'sparkline_col': 'daily_customers'}
        ]
    """
    setup_style()
    fig = plt.figure(figsize=figsize)

    # Create grid: KPIs on top, charts below
    n_kpis = len(kpis)
    n_charts = len(charts)

    # Overall title
    fig.suptitle(title, fontsize=20, fontweight='bold', y=0.98)

    # KPI row
    kpi_height = 0.12
    for i, kpi in enumerate(kpis):
        ax = fig.add_axes([0.05 + i * (0.9 / n_kpis), 0.85, 0.85 / n_kpis, kpi_height])
        ax.axis('off')

        # KPI name
        ax.text(0.5, 0.85, kpi['name'], ha='center', va='top',
                fontsize=12, fontweight='bold', transform=ax.transAxes)

        # KPI value
        value_str = f"{kpi['value']:,.0f}" if kpi['value'] >= 1 else f"{kpi['value']:.2f}"
        ax.text(0.5, 0.5, value_str, ha='center', va='center',
                fontsize=24, fontweight='bold', transform=ax.transAxes)

        # Change indicator
        change = kpi.get('change_pct', 0)
        arrow = '↑' if change > 0 else '↓' if change < 0 else '→'
        color = 'green' if change > 0 else 'red' if change < 0 else 'gray'
        ax.text(0.5, 0.25, f'{arrow} {abs(change):.1f}%', ha='center', va='center',
                fontsize=14, color=color, transform=ax.transAxes)

    # Charts grid
    chart_rows = (n_charts + 1) // 2
    chart_cols = 2 if n_charts > 1 else 1

    chart_start_y = 0.70
    chart_height = (chart_start_y - 0.05) / chart_rows

    for i, chart_config in enumerate(charts):
        row = i // chart_cols
        col = i % chart_cols

        ax = fig.add_axes([
            0.05 + col * 0.47,
            chart_start_y - (row + 1) * chart_height + 0.02,
            0.43,
            chart_height - 0.04
        ])

        chart_type = chart_config.get('type', 'bar')

        if chart_type == 'bar':
            subset = data[[chart_config['x'], chart_config['y']]].dropna()
            ax.bar(subset[chart_config['x']], subset[chart_config['y']],
                   color='#2E86AB', edgecolor='black', alpha=0.8)
            ax.set_xlabel(chart_config['x'])
            ax.set_ylabel(chart_config['y'])
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        elif chart_type == 'line':
            subset = data[[chart_config['x'], chart_config['y']]].dropna()
            ax.plot(subset[chart_config['x']], subset[chart_config['y']],
                    color='#2E86AB', linewidth=2, marker='o')
            ax.set_xlabel(chart_config['x'])
            ax.set_ylabel(chart_config['y'])
            plt.setp(ax.xaxis.get_majorticklabels(), rotation=45, ha='right')

        ax.set_title(chart_config.get('title', ''), fontweight='bold', fontsize=12)
        ax.grid(alpha=0.3)

    return fig


def main():
    parser = argparse.ArgumentParser(description='Create professional data visualizations')
    parser.add_argument('--type', required=True,
                       choices=['bar', 'line', 'scatter', 'heatmap', 'distribution', 'dashboard'],
                       help='Type of visualization to create')
    parser.add_argument('--input', required=True, help='Input CSV file')
    parser.add_argument('--output', required=True, help='Output image file (png, pdf, svg)')
    parser.add_argument('--x', help='Column for x-axis')
    parser.add_argument('--y', help='Column for y-axis')
    parser.add_argument('--hue', help='Column for color grouping')
    parser.add_argument('--size', help='Column for size (scatter plot)')
    parser.add_argument('--title', default='', help='Chart title')
    parser.add_argument('--xlabel', default='', help='X-axis label')
    parser.add_argument('--ylabel', default='', help='Y-axis label')
    parser.add_argument('--palette', default='default', help='Color palette')
    parser.add_argument('--horizontal', action='store_true', help='Horizontal bar chart')
    parser.add_argument('--sort', action='store_true', help='Sort bars by value')
    parser.add_argument('--top-n', type=int, help='Show only top N items')
    parser.add_argument('--trendline', action='store_true', help='Add trendline (scatter)')
    parser.add_argument('--markers', action='store_true', help='Add markers (line chart)')
    parser.add_argument('--area', action='store_true', help='Fill area under line')
    parser.add_argument('--plot-type', default='hist',
                       choices=['hist', 'kde', 'box', 'violin'],
                       help='Distribution plot type')
    parser.add_argument('--dpi', type=int, default=300, help='Output DPI')

    args = parser.parse_args()

    # Load data
    try:
        data = pd.read_csv(args.input)
        print(f"✅ Loaded data: {data.shape[0]} rows, {data.shape[1]} columns")
    except Exception as e:
        print(f"❌ Error loading file: {e}")
        sys.exit(1)

    # Create visualization
    try:
        if args.type == 'bar':
            if not args.x or not args.y:
                print("❌ Bar chart requires --x and --y arguments")
                sys.exit(1)
            fig = create_bar_chart(
                data, args.x, args.y, args.hue, args.horizontal,
                args.title, args.xlabel, args.ylabel, args.palette,
                sort=args.sort, top_n=args.top_n
            )

        elif args.type == 'line':
            if not args.x or not args.y:
                print("❌ Line chart requires --x and --y arguments")
                sys.exit(1)
            fig = create_line_chart(
                data, args.x, args.y, args.hue,
                args.title, args.xlabel, args.ylabel, args.palette,
                markers=args.markers, show_area=args.area
            )

        elif args.type == 'scatter':
            if not args.x or not args.y:
                print("❌ Scatter plot requires --x and --y arguments")
                sys.exit(1)
            fig = create_scatter_plot(
                data, args.x, args.y, args.hue, args.size,
                args.title, args.xlabel, args.ylabel, args.palette,
                show_trendline=args.trendline
            )

        elif args.type == 'heatmap':
            fig = create_heatmap(data, args.title, args.palette, annot=True)

        elif args.type == 'distribution':
            if not args.x:
                print("❌ Distribution plot requires --x argument")
                sys.exit(1)
            fig = create_distribution_plot(
                data, args.x, args.hue, args.title, args.xlabel,
                args.palette, plot_type=args.plot_type
            )

        elif args.type == 'dashboard':
            print("❌ Dashboard creation requires Python API usage")
            print("   See script documentation for dashboard usage")
            sys.exit(1)

        # Save
        output_path = Path(args.output)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        fig.savefig(output_path, dpi=args.dpi, bbox_inches='tight', facecolor='white')
        print(f"✅ Saved visualization: {output_path}")

    except Exception as e:
        print(f"❌ Error creating visualization: {e}")
        import traceback
        traceback.print_exc()
        sys.exit(1)


if __name__ == '__main__':
    main()
