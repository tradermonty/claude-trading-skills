"""
Data Visualization Template

Professional visualization templates for common data science tasks.
Copy and customize sections as needed for your analysis.

Dependencies:
    pip install matplotlib seaborn plotly pandas numpy
"""

import matplotlib.pyplot as plt
import seaborn as sns
import pandas as pd
import numpy as np

# Set professional style
sns.set_style('whitegrid')
sns.set_context('notebook', font_scale=1.2)
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.family'] = 'sans-serif'

# Professional color palettes
COLORS_QUALITATIVE = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#6A994E']
COLORS_SEQUENTIAL = sns.color_palette('Blues', n_colors=7)
COLORS_DIVERGING = sns.color_palette('RdBu', n_colors=7)


# ============================================================================
# DISTRIBUTION VISUALIZATIONS
# ============================================================================

def plot_distribution(data, column, title=None):
    """
    Plot distribution with histogram and KDE

    Args:
        data: DataFrame
        column: Column name to plot
        title: Plot title (optional)
    """
    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Histogram with KDE
    axes[0].hist(data[column].dropna(), bins=30, edgecolor='black',
                 alpha=0.7, density=True, color=COLORS_QUALITATIVE[0])
    data[column].plot(kind='density', ax=axes[0], linewidth=2,
                      color=COLORS_QUALITATIVE[1])
    axes[0].set_xlabel(column)
    axes[0].set_ylabel('Density')
    axes[0].set_title(title or f'{column} Distribution')
    axes[0].grid(alpha=0.3)

    # Box plot
    axes[1].boxplot(data[column].dropna())
    axes[1].set_ylabel(column)
    axes[1].set_title(f'{column} Box Plot')
    axes[1].grid(axis='y', alpha=0.3)

    plt.tight_layout()
    return fig


def plot_categorical_distribution(data, column, top_n=10, title=None):
    """
    Plot categorical variable distribution

    Args:
        data: DataFrame
        column: Column name to plot
        top_n: Number of top categories to show
        title: Plot title (optional)
    """
    value_counts = data[column].value_counts().head(top_n)

    fig, axes = plt.subplots(1, 2, figsize=(14, 5))

    # Bar chart
    value_counts.plot(kind='bar', ax=axes[0], color=COLORS_QUALITATIVE[0],
                      edgecolor='black', alpha=0.7)
    axes[0].set_xlabel(column)
    axes[0].set_ylabel('Count')
    axes[0].set_title(title or f'{column} Distribution')
    axes[0].grid(axis='y', alpha=0.3)
    axes[0].tick_params(axis='x', rotation=45)

    # Pie chart
    value_counts.plot(kind='pie', ax=axes[1], autopct='%1.1f%%',
                      startangle=90, colors=COLORS_QUALITATIVE)
    axes[1].set_ylabel('')
    axes[1].set_title(f'{column} Proportions')

    plt.tight_layout()
    return fig


# ============================================================================
# RELATIONSHIP VISUALIZATIONS
# ============================================================================

def plot_correlation_matrix(data, figsize=(12, 10)):
    """
    Plot correlation matrix heatmap

    Args:
        data: DataFrame with numerical columns
        figsize: Figure size tuple
    """
    # Calculate correlation
    corr = data.select_dtypes(include=[np.number]).corr()

    # Create heatmap
    fig, ax = plt.subplots(figsize=figsize)
    sns.heatmap(corr, annot=True, fmt='.2f', cmap='coolwarm', center=0,
                square=True, linewidths=1, cbar_kws={"shrink": 0.8}, ax=ax)
    ax.set_title('Correlation Matrix', fontsize=14, fontweight='bold')
    plt.tight_layout()
    return fig


def plot_scatter_with_regression(data, x_col, y_col, hue=None, title=None):
    """
    Scatter plot with regression line

    Args:
        data: DataFrame
        x_col: X-axis column name
        y_col: Y-axis column name
        hue: Column for color grouping (optional)
        title: Plot title (optional)
    """
    fig, ax = plt.subplots(figsize=(10, 6))

    if hue:
        for category in data[hue].unique():
            mask = data[hue] == category
            ax.scatter(data[mask][x_col], data[mask][y_col],
                      label=category, alpha=0.6, s=50)
    else:
        ax.scatter(data[x_col], data[y_col], alpha=0.6, s=50,
                  color=COLORS_QUALITATIVE[0])

        # Add regression line
        z = np.polyfit(data[x_col].dropna(), data[y_col].dropna(), 1)
        p = np.poly1d(z)
        ax.plot(data[x_col], p(data[x_col]), 'r--', linewidth=2,
                label=f'Trend: y={z[0]:.2f}x+{z[1]:.2f}')

    ax.set_xlabel(x_col)
    ax.set_ylabel(y_col)
    ax.set_title(title or f'{y_col} vs {x_col}')
    ax.legend()
    ax.grid(alpha=0.3)
    plt.tight_layout()
    return fig


def plot_pairplot(data, hue=None, vars=None):
    """
    Create pair plot for multiple variables

    Args:
        data: DataFrame
        hue: Column for color grouping (optional)
        vars: List of columns to include (optional, uses all numeric if None)
    """
    if vars is None:
        vars = data.select_dtypes(include=[np.number]).columns.tolist()

    g = sns.pairplot(data[vars + ([hue] if hue else [])],
                     hue=hue, diag_kind='kde', height=3,
                     plot_kws={'alpha': 0.6})
    g.fig.suptitle('Pairwise Relationships', y=1.01, fontsize=14,
                   fontweight='bold')
    return g.fig


# ============================================================================
# TIME SERIES VISUALIZATIONS
# ============================================================================

def plot_time_series(data, date_col, value_col, title=None):
    """
    Plot time series with moving averages

    Args:
        data: DataFrame
        date_col: Date column name
        value_col: Value column name
        title: Plot title (optional)
    """
    fig, ax = plt.subplots(figsize=(14, 6))

    # Original series
    ax.plot(data[date_col], data[value_col], label='Original',
            linewidth=1.5, alpha=0.7, color=COLORS_QUALITATIVE[0])

    # Moving averages
    if len(data) >= 30:
        ma_30 = data[value_col].rolling(window=30).mean()
        ax.plot(data[date_col], ma_30, label='30-period MA',
                linewidth=2, color=COLORS_QUALITATIVE[1])

    if len(data) >= 90:
        ma_90 = data[value_col].rolling(window=90).mean()
        ax.plot(data[date_col], ma_90, label='90-period MA',
                linewidth=2, color=COLORS_QUALITATIVE[2])

    ax.set_xlabel('Date')
    ax.set_ylabel(value_col)
    ax.set_title(title or f'{value_col} Over Time')
    ax.legend()
    ax.grid(alpha=0.3)
    plt.xticks(rotation=45)
    plt.tight_layout()
    return fig


def plot_seasonal_decomposition(data, value_col, period=12):
    """
    Plot seasonal decomposition

    Args:
        data: DataFrame with datetime index
        value_col: Value column name
        period: Seasonality period
    """
    from statsmodels.tsa.seasonal import seasonal_decompose

    decomposition = seasonal_decompose(data[value_col], model='additive',
                                      period=period)

    fig, axes = plt.subplots(4, 1, figsize=(14, 12))

    decomposition.observed.plot(ax=axes[0])
    axes[0].set_ylabel('Observed')
    axes[0].set_title(f'Seasonal Decomposition (period={period})')
    axes[0].grid(alpha=0.3)

    decomposition.trend.plot(ax=axes[1])
    axes[1].set_ylabel('Trend')
    axes[1].grid(alpha=0.3)

    decomposition.seasonal.plot(ax=axes[2])
    axes[2].set_ylabel('Seasonal')
    axes[2].grid(alpha=0.3)

    decomposition.resid.plot(ax=axes[3])
    axes[3].set_ylabel('Residual')
    axes[3].grid(alpha=0.3)

    plt.tight_layout()
    return fig


# ============================================================================
# MODEL PERFORMANCE VISUALIZATIONS
# ============================================================================

def plot_confusion_matrix(y_true, y_pred, labels=None, title='Confusion Matrix'):
    """
    Plot confusion matrix

    Args:
        y_true: True labels
        y_pred: Predicted labels
        labels: Class labels (optional)
        title: Plot title
    """
    from sklearn.metrics import confusion_matrix

    cm = confusion_matrix(y_true, y_pred)

    fig, ax = plt.subplots(figsize=(8, 6))
    sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
                xticklabels=labels or ['Negative', 'Positive'],
                yticklabels=labels or ['Negative', 'Positive'], ax=ax)
    ax.set_xlabel('Predicted')
    ax.set_ylabel('Actual')
    ax.set_title(title)
    plt.tight_layout()
    return fig


def plot_roc_curve(y_true, y_pred_proba, title='ROC Curve'):
    """
    Plot ROC curve

    Args:
        y_true: True labels
        y_pred_proba: Predicted probabilities
        title: Plot title
    """
    from sklearn.metrics import roc_curve, auc

    fpr, tpr, _ = roc_curve(y_true, y_pred_proba)
    roc_auc = auc(fpr, tpr)

    fig, ax = plt.subplots(figsize=(8, 6))
    ax.plot(fpr, tpr, linewidth=2, label=f'ROC curve (AUC = {roc_auc:.2f})',
            color=COLORS_QUALITATIVE[0])
    ax.plot([0, 1], [0, 1], 'k--', label='Random Classifier', linewidth=1)
    ax.set_xlim([0.0, 1.0])
    ax.set_ylim([0.0, 1.05])
    ax.set_xlabel('False Positive Rate')
    ax.set_ylabel('True Positive Rate')
    ax.set_title(title)
    ax.legend(loc="lower right")
    ax.grid(alpha=0.3)
    plt.tight_layout()
    return fig


def plot_feature_importance(feature_names, importances, top_n=20,
                           title='Feature Importance'):
    """
    Plot feature importance

    Args:
        feature_names: List of feature names
        importances: Feature importance values
        top_n: Number of top features to show
        title: Plot title
    """
    # Create DataFrame and sort
    importance_df = pd.DataFrame({
        'feature': feature_names,
        'importance': importances
    }).sort_values('importance', ascending=False).head(top_n)

    fig, ax = plt.subplots(figsize=(10, max(6, top_n * 0.3)))
    ax.barh(range(len(importance_df)), importance_df['importance'],
            color=COLORS_QUALITATIVE[0], alpha=0.7)
    ax.set_yticks(range(len(importance_df)))
    ax.set_yticklabels(importance_df['feature'])
    ax.set_xlabel('Importance')
    ax.set_title(title)
    ax.invert_yaxis()
    ax.grid(axis='x', alpha=0.3)
    plt.tight_layout()
    return fig


def plot_residuals(y_true, y_pred, title='Residual Analysis'):
    """
    Plot residual analysis for regression

    Args:
        y_true: True values
        y_pred: Predicted values
        title: Plot title
    """
    residuals = y_true - y_pred

    fig, axes = plt.subplots(1, 3, figsize=(16, 5))

    # Residuals vs Predicted
    axes[0].scatter(y_pred, residuals, alpha=0.5, color=COLORS_QUALITATIVE[0])
    axes[0].axhline(y=0, color='r', linestyle='--', linewidth=2)
    axes[0].set_xlabel('Predicted Values')
    axes[0].set_ylabel('Residuals')
    axes[0].set_title('Residuals vs Predicted')
    axes[0].grid(alpha=0.3)

    # Residual distribution
    axes[1].hist(residuals, bins=30, edgecolor='black', alpha=0.7,
                color=COLORS_QUALITATIVE[1])
    axes[1].set_xlabel('Residuals')
    axes[1].set_ylabel('Frequency')
    axes[1].set_title('Residual Distribution')
    axes[1].grid(axis='y', alpha=0.3)

    # Q-Q plot
    from scipy import stats
    stats.probplot(residuals, dist="norm", plot=axes[2])
    axes[2].set_title('Q-Q Plot')
    axes[2].grid(alpha=0.3)

    fig.suptitle(title, fontsize=14, fontweight='bold', y=1.02)
    plt.tight_layout()
    return fig


def plot_learning_curves(train_sizes, train_scores, val_scores,
                         title='Learning Curves'):
    """
    Plot learning curves

    Args:
        train_sizes: Training set sizes
        train_scores: Training scores
        val_scores: Validation scores
        title: Plot title
    """
    train_mean = np.mean(train_scores, axis=1)
    train_std = np.std(train_scores, axis=1)
    val_mean = np.mean(val_scores, axis=1)
    val_std = np.std(val_scores, axis=1)

    fig, ax = plt.subplots(figsize=(10, 6))

    ax.plot(train_sizes, train_mean, label='Training score',
            linewidth=2, color=COLORS_QUALITATIVE[0])
    ax.fill_between(train_sizes, train_mean - train_std, train_mean + train_std,
                     alpha=0.2, color=COLORS_QUALITATIVE[0])

    ax.plot(train_sizes, val_mean, label='Validation score',
            linewidth=2, color=COLORS_QUALITATIVE[1])
    ax.fill_between(train_sizes, val_mean - val_std, val_mean + val_std,
                     alpha=0.2, color=COLORS_QUALITATIVE[1])

    ax.set_xlabel('Training Set Size')
    ax.set_ylabel('Score')
    ax.set_title(title)
    ax.legend(loc='best')
    ax.grid(alpha=0.3)
    plt.tight_layout()
    return fig


# ============================================================================
# USAGE EXAMPLES
# ============================================================================

if __name__ == '__main__':
    # Example usage with sample data

    # Create sample data
    np.random.seed(42)
    sample_data = pd.DataFrame({
        'numeric_var': np.random.randn(1000),
        'category': np.random.choice(['A', 'B', 'C'], 1000),
        'value': np.random.rand(1000) * 100,
        'target': np.random.choice([0, 1], 1000)
    })

    # Distribution plots
    fig1 = plot_distribution(sample_data, 'numeric_var')
    plt.savefig('example_distribution.png', dpi=300, bbox_inches='tight')

    # Categorical distribution
    fig2 = plot_categorical_distribution(sample_data, 'category')
    plt.savefig('example_categorical.png', dpi=300, bbox_inches='tight')

    # Correlation matrix
    fig3 = plot_correlation_matrix(sample_data)
    plt.savefig('example_correlation.png', dpi=300, bbox_inches='tight')

    print("Example visualizations saved!")
