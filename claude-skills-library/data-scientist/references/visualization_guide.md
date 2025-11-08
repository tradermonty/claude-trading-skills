# Data Visualization Guide

## Overview

Effective visualization is essential for data exploration, communication, and insight discovery. This guide provides comprehensive patterns for different analysis scenarios.

## Visualization Principles

### Core Principles

1. **Purpose-Driven:** Every visualization should answer a specific question
2. **Clarity Over Complexity:** Simple, clear visualizations beat complex ones
3. **Accuracy:** Never mislead with inappropriate scales or chart types
4. **Accessibility:** Consider color blindness, ensure readability
5. **Context:** Provide necessary context (titles, labels, units, sample sizes)

### Choosing the Right Visualization

**Ask:**
1. What question am I answering?
2. What type of data do I have?
3. What relationship am I showing?
4. Who is the audience?

## Exploratory Data Analysis (EDA) Visualizations

### Univariate Analysis

#### Continuous Variables

**Histogram**
```python
import matplotlib.pyplot as plt
import seaborn as sns

# Basic histogram
plt.figure(figsize=(10, 6))
plt.hist(df['age'], bins=30, edgecolor='black', alpha=0.7)
plt.xlabel('Age')
plt.ylabel('Frequency')
plt.title('Age Distribution')
plt.grid(axis='y', alpha=0.3)
plt.show()

# With density curve
plt.figure(figsize=(10, 6))
sns.histplot(data=df, x='age', bins=30, kde=True)
plt.title('Age Distribution with Density Curve')
plt.show()
```
**When to use:** Understand distribution shape, identify skewness, detect outliers

**Box Plot**
```python
# Single variable
plt.figure(figsize=(8, 6))
sns.boxplot(y=df['salary'])
plt.title('Salary Distribution')
plt.ylabel('Salary ($)')
plt.show()

# Multiple variables
plt.figure(figsize=(12, 6))
df[['salary', 'bonus', 'stock_value']].boxplot()
plt.title('Compensation Components Distribution')
plt.ylabel('Amount ($)')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Quick summary statistics, identify outliers, compare distributions

**Violin Plot**
```python
plt.figure(figsize=(10, 6))
sns.violinplot(data=df, y='income')
plt.title('Income Distribution (Violin Plot)')
plt.show()

# With inner quartiles
sns.violinplot(data=df, y='income', inner='quartile')
plt.show()
```
**When to use:** Show full distribution shape, combine benefits of box plot and density

**Density Plot (KDE)**
```python
plt.figure(figsize=(10, 6))
df['age'].plot(kind='density')
plt.xlabel('Age')
plt.title('Age Density Distribution')
plt.show()

# Compare multiple distributions
plt.figure(figsize=(10, 6))
for category in df['category'].unique():
    df[df['category'] == category]['value'].plot(kind='density', label=category, alpha=0.7)
plt.xlabel('Value')
plt.title('Value Distribution by Category')
plt.legend()
plt.show()
```
**When to use:** Smooth distribution representation, compare multiple distributions

#### Categorical Variables

**Bar Chart**
```python
# Value counts
plt.figure(figsize=(10, 6))
df['category'].value_counts().plot(kind='bar', edgecolor='black')
plt.xlabel('Category')
plt.ylabel('Count')
plt.title('Category Distribution')
plt.xticks(rotation=45)
plt.show()

# Sorted by value
plt.figure(figsize=(10, 6))
df['category'].value_counts().sort_values().plot(kind='barh')
plt.xlabel('Count')
plt.ylabel('Category')
plt.title('Category Distribution (Sorted)')
plt.show()
```
**When to use:** Compare categories, show frequencies

**Pie Chart**
```python
plt.figure(figsize=(8, 8))
df['category'].value_counts().plot(kind='pie', autopct='%1.1f%%', startangle=90)
plt.title('Category Proportions')
plt.ylabel('')  # Hide y-label
plt.show()
```
**When to use:** Show proportions (use sparingly, bar charts often better)

**Count Plot**
```python
plt.figure(figsize=(10, 6))
sns.countplot(data=df, x='category', order=df['category'].value_counts().index)
plt.xlabel('Category')
plt.ylabel('Count')
plt.title('Category Counts')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Quick categorical frequency visualization

### Bivariate Analysis

#### Continuous vs Continuous

**Scatter Plot**
```python
# Basic scatter plot
plt.figure(figsize=(10, 6))
plt.scatter(df['age'], df['income'], alpha=0.5)
plt.xlabel('Age')
plt.ylabel('Income ($)')
plt.title('Age vs Income')
plt.grid(alpha=0.3)
plt.show()

# With regression line
plt.figure(figsize=(10, 6))
sns.regplot(data=df, x='age', y='income', scatter_kws={'alpha': 0.5})
plt.title('Age vs Income with Trend Line')
plt.show()

# Colored by category
plt.figure(figsize=(10, 6))
for category in df['category'].unique():
    mask = df['category'] == category
    plt.scatter(df[mask]['age'], df[mask]['income'], label=category, alpha=0.6)
plt.xlabel('Age')
plt.ylabel('Income ($)')
plt.title('Age vs Income by Category')
plt.legend()
plt.grid(alpha=0.3)
plt.show()
```
**When to use:** Explore relationships, identify correlations, detect patterns

**Hexbin Plot**
```python
plt.figure(figsize=(10, 8))
plt.hexbin(df['age'], df['income'], gridsize=30, cmap='Blues')
plt.colorbar(label='Count')
plt.xlabel('Age')
plt.ylabel('Income ($)')
plt.title('Age vs Income (Hexbin)')
plt.show()
```
**When to use:** Large datasets where scatter plot becomes cluttered

**2D Density Plot**
```python
plt.figure(figsize=(10, 8))
sns.kdeplot(data=df, x='age', y='income', cmap='Blues', fill=True, levels=10)
plt.xlabel('Age')
plt.ylabel('Income ($)')
plt.title('Age vs Income Density')
plt.show()
```
**When to use:** Show density of points, identify concentration areas

**Joint Plot**
```python
sns.jointplot(data=df, x='age', y='income', kind='scatter', height=8)
plt.show()

# With hexbin
sns.jointplot(data=df, x='age', y='income', kind='hex', height=8)
plt.show()

# With regression
sns.jointplot(data=df, x='age', y='income', kind='reg', height=8)
plt.show()
```
**When to use:** Show bivariate relationship plus marginal distributions

#### Continuous vs Categorical

**Box Plot by Category**
```python
plt.figure(figsize=(12, 6))
sns.boxplot(data=df, x='category', y='salary')
plt.xlabel('Category')
plt.ylabel('Salary ($)')
plt.title('Salary Distribution by Category')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Compare distributions across categories

**Violin Plot by Category**
```python
plt.figure(figsize=(12, 6))
sns.violinplot(data=df, x='category', y='salary')
plt.xlabel('Category')
plt.ylabel('Salary ($)')
plt.title('Salary Distribution by Category')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Show full distribution shape across categories

**Strip Plot / Swarm Plot**
```python
# Strip plot (random jitter)
plt.figure(figsize=(12, 6))
sns.stripplot(data=df, x='category', y='salary', alpha=0.5, jitter=True)
plt.xlabel('Category')
plt.ylabel('Salary ($)')
plt.title('Salary by Category (Strip Plot)')
plt.xticks(rotation=45)
plt.show()

# Swarm plot (non-overlapping)
plt.figure(figsize=(12, 6))
sns.swarmplot(data=df, x='category', y='salary')
plt.xlabel('Category')
plt.ylabel('Salary ($)')
plt.title('Salary by Category (Swarm Plot)')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Show individual points (small to medium datasets)

**Combined Box + Strip Plot**
```python
plt.figure(figsize=(12, 6))
sns.boxplot(data=df, x='category', y='salary', color='lightgray')
sns.stripplot(data=df, x='category', y='salary', color='red', alpha=0.3, jitter=True)
plt.xlabel('Category')
plt.ylabel('Salary ($)')
plt.title('Salary Distribution by Category (Box + Strip)')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Show both summary statistics and individual points

#### Categorical vs Categorical

**Grouped Bar Chart**
```python
pd.crosstab(df['category1'], df['category2']).plot(kind='bar', figsize=(12, 6))
plt.xlabel('Category 1')
plt.ylabel('Count')
plt.title('Category 1 vs Category 2')
plt.legend(title='Category 2')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Compare counts across two categorical variables

**Stacked Bar Chart**
```python
pd.crosstab(df['category1'], df['category2']).plot(kind='bar', stacked=True, figsize=(12, 6))
plt.xlabel('Category 1')
plt.ylabel('Count')
plt.title('Category 1 vs Category 2 (Stacked)')
plt.legend(title='Category 2')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Show composition and total

**Heatmap (Confusion Matrix Style)**
```python
plt.figure(figsize=(10, 8))
crosstab = pd.crosstab(df['category1'], df['category2'])
sns.heatmap(crosstab, annot=True, fmt='d', cmap='Blues')
plt.xlabel('Category 2')
plt.ylabel('Category 1')
plt.title('Category 1 vs Category 2 Heatmap')
plt.show()
```
**When to use:** Show relationship strength between categories

### Multivariate Analysis

**Correlation Matrix Heatmap**
```python
plt.figure(figsize=(12, 10))
correlation = df.select_dtypes(include=[np.number]).corr()
sns.heatmap(correlation, annot=True, fmt='.2f', cmap='coolwarm', center=0,
            square=True, linewidths=1, cbar_kws={"shrink": 0.8})
plt.title('Correlation Matrix')
plt.tight_layout()
plt.show()
```
**When to use:** Identify correlations, multicollinearity detection

**Pair Plot**
```python
sns.pairplot(df[['feature1', 'feature2', 'feature3', 'target']],
             hue='target', diag_kind='kde', height=3)
plt.show()
```
**When to use:** Explore relationships between multiple variables

**Parallel Coordinates**
```python
from pandas.plotting import parallel_coordinates

plt.figure(figsize=(12, 6))
parallel_coordinates(df[['feature1', 'feature2', 'feature3', 'category']],
                     'category', colormap='viridis')
plt.xlabel('Features')
plt.ylabel('Values')
plt.title('Parallel Coordinates Plot')
plt.legend(loc='best')
plt.xticks(rotation=45)
plt.show()
```
**When to use:** Compare patterns across categories with multiple features

**3D Scatter Plot**
```python
from mpl_toolkits.mplot3d import Axes3D

fig = plt.figure(figsize=(12, 8))
ax = fig.add_subplot(111, projection='3d')
scatter = ax.scatter(df['feature1'], df['feature2'], df['feature3'],
                     c=df['target'], cmap='viridis', alpha=0.6)
ax.set_xlabel('Feature 1')
ax.set_ylabel('Feature 2')
ax.set_zlabel('Feature 3')
ax.set_title('3D Scatter Plot')
plt.colorbar(scatter, label='Target')
plt.show()
```
**When to use:** Visualize 3D relationships (use sparingly, hard to interpret)

## Time Series Visualizations

**Line Plot**
```python
plt.figure(figsize=(14, 6))
plt.plot(df['date'], df['value'], linewidth=2)
plt.xlabel('Date')
plt.ylabel('Value')
plt.title('Time Series Plot')
plt.grid(alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()

# Multiple series
plt.figure(figsize=(14, 6))
for series in ['series1', 'series2', 'series3']:
    plt.plot(df['date'], df[series], label=series, linewidth=2)
plt.xlabel('Date')
plt.ylabel('Value')
plt.title('Multiple Time Series')
plt.legend()
plt.grid(alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```
**When to use:** Show trends over time, compare multiple series

**Area Plot**
```python
plt.figure(figsize=(14, 6))
plt.fill_between(df['date'], df['value'], alpha=0.3)
plt.plot(df['date'], df['value'], linewidth=2)
plt.xlabel('Date')
plt.ylabel('Value')
plt.title('Area Plot')
plt.grid(alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```
**When to use:** Emphasize magnitude of change

**Stacked Area Plot**
```python
plt.figure(figsize=(14, 6))
df_pivot = df.pivot(index='date', columns='category', values='value')
df_pivot.plot(kind='area', stacked=True, figsize=(14, 6), alpha=0.7)
plt.xlabel('Date')
plt.ylabel('Value')
plt.title('Stacked Area Chart')
plt.legend(loc='best')
plt.grid(alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```
**When to use:** Show composition over time

**Seasonal Decomposition**
```python
from statsmodels.tsa.seasonal import seasonal_decompose

decomposition = seasonal_decompose(df['value'], model='additive', period=12)

fig, axes = plt.subplots(4, 1, figsize=(14, 10))
decomposition.observed.plot(ax=axes[0], title='Observed')
decomposition.trend.plot(ax=axes[1], title='Trend')
decomposition.seasonal.plot(ax=axes[2], title='Seasonal')
decomposition.resid.plot(ax=axes[3], title='Residual')
plt.tight_layout()
plt.show()
```
**When to use:** Understand trend, seasonality, and residuals

**Rolling Statistics**
```python
plt.figure(figsize=(14, 6))
plt.plot(df['date'], df['value'], label='Original', alpha=0.5)
plt.plot(df['date'], df['value'].rolling(window=30).mean(),
         label='30-day MA', linewidth=2)
plt.plot(df['date'], df['value'].rolling(window=90).mean(),
         label='90-day MA', linewidth=2)
plt.xlabel('Date')
plt.ylabel('Value')
plt.title('Time Series with Moving Averages')
plt.legend()
plt.grid(alpha=0.3)
plt.xticks(rotation=45)
plt.tight_layout()
plt.show()
```
**When to use:** Smooth noise, identify trends

## Model Performance Visualizations

**Confusion Matrix**
```python
from sklearn.metrics import confusion_matrix
import seaborn as sns

cm = confusion_matrix(y_true, y_pred)

plt.figure(figsize=(8, 6))
sns.heatmap(cm, annot=True, fmt='d', cmap='Blues',
            xticklabels=['Negative', 'Positive'],
            yticklabels=['Negative', 'Positive'])
plt.xlabel('Predicted')
plt.ylabel('Actual')
plt.title('Confusion Matrix')
plt.show()
```
**When to use:** Understand classification errors

**ROC Curve**
```python
from sklearn.metrics import roc_curve, auc

fpr, tpr, thresholds = roc_curve(y_true, y_pred_proba)
roc_auc = auc(fpr, tpr)

plt.figure(figsize=(8, 6))
plt.plot(fpr, tpr, linewidth=2, label=f'ROC curve (AUC = {roc_auc:.2f})')
plt.plot([0, 1], [0, 1], 'k--', label='Random Classifier')
plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.xlabel('False Positive Rate')
plt.ylabel('True Positive Rate')
plt.title('Receiver Operating Characteristic (ROC) Curve')
plt.legend(loc="lower right")
plt.grid(alpha=0.3)
plt.show()
```
**When to use:** Evaluate binary classifier performance

**Precision-Recall Curve**
```python
from sklearn.metrics import precision_recall_curve, average_precision_score

precision, recall, thresholds = precision_recall_curve(y_true, y_pred_proba)
ap_score = average_precision_score(y_true, y_pred_proba)

plt.figure(figsize=(8, 6))
plt.plot(recall, precision, linewidth=2, label=f'PR curve (AP = {ap_score:.2f})')
plt.xlabel('Recall')
plt.ylabel('Precision')
plt.title('Precision-Recall Curve')
plt.legend(loc="lower left")
plt.grid(alpha=0.3)
plt.xlim([0.0, 1.0])
plt.ylim([0.0, 1.05])
plt.show()
```
**When to use:** Evaluate binary classifier on imbalanced data

**Learning Curves**
```python
from sklearn.model_selection import learning_curve

train_sizes, train_scores, val_scores = learning_curve(
    estimator, X, y, cv=5, train_sizes=np.linspace(0.1, 1.0, 10),
    scoring='accuracy', n_jobs=-1
)

train_mean = np.mean(train_scores, axis=1)
train_std = np.std(train_scores, axis=1)
val_mean = np.mean(val_scores, axis=1)
val_std = np.std(val_scores, axis=1)

plt.figure(figsize=(10, 6))
plt.plot(train_sizes, train_mean, label='Training score', linewidth=2)
plt.fill_between(train_sizes, train_mean - train_std, train_mean + train_std, alpha=0.2)
plt.plot(train_sizes, val_mean, label='Validation score', linewidth=2)
plt.fill_between(train_sizes, val_mean - val_std, val_mean + val_std, alpha=0.2)
plt.xlabel('Training Set Size')
plt.ylabel('Score')
plt.title('Learning Curves')
plt.legend(loc='best')
plt.grid(alpha=0.3)
plt.tight_layout()
plt.show()
```
**When to use:** Diagnose overfitting/underfitting, determine if more data helps

**Residual Plot**
```python
residuals = y_true - y_pred

fig, axes = plt.subplots(1, 2, figsize=(14, 5))

# Residuals vs Predicted
axes[0].scatter(y_pred, residuals, alpha=0.5)
axes[0].axhline(y=0, color='r', linestyle='--', linewidth=2)
axes[0].set_xlabel('Predicted Values')
axes[0].set_ylabel('Residuals')
axes[0].set_title('Residuals vs Predicted')
axes[0].grid(alpha=0.3)

# Residual distribution
axes[1].hist(residuals, bins=30, edgecolor='black', alpha=0.7)
axes[1].set_xlabel('Residuals')
axes[1].set_ylabel('Frequency')
axes[1].set_title('Residual Distribution')
axes[1].grid(axis='y', alpha=0.3)

plt.tight_layout()
plt.show()
```
**When to use:** Validate regression assumptions, detect heteroscedasticity

**Feature Importance**
```python
# From tree-based model
feature_importance = pd.DataFrame({
    'feature': feature_names,
    'importance': model.feature_importances_
}).sort_values('importance', ascending=False).head(20)

plt.figure(figsize=(10, 8))
plt.barh(range(len(feature_importance)), feature_importance['importance'])
plt.yticks(range(len(feature_importance)), feature_importance['feature'])
plt.xlabel('Importance')
plt.title('Top 20 Feature Importances')
plt.gca().invert_yaxis()
plt.tight_layout()
plt.show()
```
**When to use:** Understand model drivers, feature selection

**SHAP Values Visualization**
```python
import shap

explainer = shap.TreeExplainer(model)
shap_values = explainer.shap_values(X)

# Summary plot
plt.figure(figsize=(10, 8))
shap.summary_plot(shap_values, X, plot_type="bar", show=False)
plt.title('SHAP Feature Importance')
plt.tight_layout()
plt.show()

# Detailed summary plot
shap.summary_plot(shap_values, X, show=False)
plt.tight_layout()
plt.show()
```
**When to use:** Understand feature impact, model interpretability

**Actual vs Predicted**
```python
plt.figure(figsize=(8, 8))
plt.scatter(y_true, y_pred, alpha=0.5)
plt.plot([y_true.min(), y_true.max()], [y_true.min(), y_true.max()],
         'r--', linewidth=2, label='Perfect Prediction')
plt.xlabel('Actual Values')
plt.ylabel('Predicted Values')
plt.title('Actual vs Predicted')
plt.legend()
plt.grid(alpha=0.3)
plt.tight_layout()
plt.show()
```
**When to use:** Assess regression model performance visually

## Best Practices

### 1. Clear Labeling

Always include:
- **Title:** Clear, descriptive
- **Axis labels:** With units
- **Legend:** When multiple series
- **Annotations:** For important points

```python
plt.figure(figsize=(10, 6))
plt.plot(x, y, linewidth=2, color='#2E86AB', label='Sales')
plt.xlabel('Month', fontsize=12)
plt.ylabel('Sales ($1000s)', fontsize=12)
plt.title('Monthly Sales Trend - Q1 2024', fontsize=14, fontweight='bold')
plt.legend(fontsize=10)
plt.grid(alpha=0.3, linestyle='--')
plt.annotate('Peak Sales', xy=(peak_x, peak_y), xytext=(peak_x+1, peak_y+5),
             arrowprops=dict(arrowstyle='->', color='red'))
plt.tight_layout()
plt.show()
```

### 2. Color Choices

```python
# Professional color palettes
colors_qualitative = ['#2E86AB', '#A23B72', '#F18F01', '#C73E1D', '#6A994E']
colors_sequential = sns.color_palette('Blues', n_colors=5)
colors_diverging = sns.color_palette('RdBu', n_colors=7)

# Colorblind-friendly
sns.set_palette('colorblind')
```

### 3. Consistent Styling

```python
# Set global style
sns.set_style('whitegrid')
sns.set_context('notebook', font_scale=1.2)

# Custom style
plt.rcParams['figure.figsize'] = (12, 6)
plt.rcParams['font.size'] = 11
plt.rcParams['axes.labelsize'] = 12
plt.rcParams['axes.titlesize'] = 14
plt.rcParams['xtick.labelsize'] = 10
plt.rcParams['ytick.labelsize'] = 10
plt.rcParams['legend.fontsize'] = 10
```

### 4. Appropriate Scale

```python
# Log scale for skewed data
plt.yscale('log')

# Broken axis for outliers
from matplotlib.patches import Rectangle
# (Implementation of broken axis)

# Start y-axis at 0 when appropriate
plt.ylim(bottom=0)
```

### 5. Aspect Ratio

```python
# Standard sizes
plt.figure(figsize=(12, 6))   # Wide for time series
plt.figure(figsize=(8, 8))    # Square for scatter plots
plt.figure(figsize=(10, 6))   # Standard

# Adjust for specific visualizations
sns.set_aspect(1)  # Force square aspect ratio
```

## Visualization Workflow Template

```python
def create_exploratory_report(df, target_col=None):
    """
    Create comprehensive exploratory visualization report
    """
    # 1. Dataset Overview
    print(f"Dataset shape: {df.shape}")
    print(f"Missing values:\n{df.isnull().sum()}")

    # 2. Numerical features
    num_cols = df.select_dtypes(include=[np.number]).columns

    # Distribution plots
    n_cols = 3
    n_rows = (len(num_cols) + n_cols - 1) // n_cols
    fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 4*n_rows))
    axes = axes.flatten()

    for idx, col in enumerate(num_cols):
        axes[idx].hist(df[col].dropna(), bins=30, edgecolor='black', alpha=0.7)
        axes[idx].set_title(f'{col} Distribution')
        axes[idx].set_xlabel(col)
        axes[idx].set_ylabel('Frequency')

    plt.tight_layout()
    plt.show()

    # 3. Correlation matrix
    plt.figure(figsize=(12, 10))
    sns.heatmap(df[num_cols].corr(), annot=True, fmt='.2f', cmap='coolwarm', center=0)
    plt.title('Correlation Matrix')
    plt.tight_layout()
    plt.show()

    # 4. Categorical features
    cat_cols = df.select_dtypes(include=['object', 'category']).columns

    for col in cat_cols:
        plt.figure(figsize=(10, 6))
        df[col].value_counts().head(10).plot(kind='barh')
        plt.title(f'{col} Distribution (Top 10)')
        plt.xlabel('Count')
        plt.tight_layout()
        plt.show()

    # 5. Target analysis (if provided)
    if target_col:
        for col in num_cols:
            if col != target_col:
                plt.figure(figsize=(10, 6))
                plt.scatter(df[col], df[target_col], alpha=0.5)
                plt.xlabel(col)
                plt.ylabel(target_col)
                plt.title(f'{col} vs {target_col}')
                plt.grid(alpha=0.3)
                plt.tight_layout()
                plt.show()
```

## Quick Reference: Chart Selection

| **Question** | **Chart Type** |
|--------------|----------------|
| What is the distribution? | Histogram, Box Plot, Violin Plot |
| How do categories compare? | Bar Chart, Box Plot by Category |
| What's the relationship between X and Y? | Scatter Plot, Regression Plot |
| How has this changed over time? | Line Chart, Area Chart |
| What are the proportions? | Pie Chart, Stacked Bar |
| How do multiple variables relate? | Pair Plot, Correlation Heatmap |
| How are data points grouped? | Scatter with colors, Parallel Coordinates |
| What are the model errors? | Residual Plot, Confusion Matrix |
| How important are features? | Bar Chart, SHAP Plots |
