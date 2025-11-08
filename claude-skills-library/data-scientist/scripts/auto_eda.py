#!/usr/bin/env python3
"""
Automated Exploratory Data Analysis (EDA) Script

This script performs comprehensive automated EDA on tabular data:
- Data quality assessment (missing values, duplicates, data types)
- Univariate analysis (distributions, outliers)
- Bivariate analysis (correlations, relationships with target)
- Generates visualizations and summary report

Usage:
    python auto_eda.py <data_file> [--target TARGET_COL] [--output OUTPUT_DIR]

Example:
    python auto_eda.py data.csv --target price --output eda_results/
"""

import argparse
import os
import sys
from pathlib import Path
import warnings
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns
from scipy import stats

# Set style
sns.set_style('whitegrid')
sns.set_context('notebook', font_scale=1.1)


class AutoEDA:
    """Automated Exploratory Data Analysis"""

    def __init__(self, data_path, target_col=None, output_dir='eda_output'):
        """
        Initialize AutoEDA

        Args:
            data_path: Path to data file (CSV, Excel, etc.)
            target_col: Name of target column (optional)
            output_dir: Directory to save outputs
        """
        self.data_path = data_path
        self.target_col = target_col
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load data
        self.df = self._load_data()
        self.report_lines = []

    def _load_data(self):
        """Load data from file"""
        file_ext = Path(self.data_path).suffix.lower()

        if file_ext == '.csv':
            return pd.read_csv(self.data_path)
        elif file_ext in ['.xlsx', '.xls']:
            return pd.read_excel(self.data_path)
        elif file_ext == '.parquet':
            return pd.read_parquet(self.data_path)
        elif file_ext == '.json':
            return pd.read_json(self.data_path)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")

    def _add_to_report(self, text):
        """Add line to report"""
        self.report_lines.append(text)
        print(text)

    def _save_fig(self, filename):
        """Save current figure"""
        plt.savefig(self.output_dir / filename, dpi=300, bbox_inches='tight')
        plt.close()

    def analyze_data_quality(self):
        """Analyze data quality"""
        self._add_to_report("\n" + "="*80)
        self._add_to_report("DATA QUALITY ASSESSMENT")
        self._add_to_report("="*80)

        # Basic info
        self._add_to_report(f"\nDataset Shape: {self.df.shape[0]:,} rows × {self.df.shape[1]} columns")
        self._add_to_report(f"Memory Usage: {self.df.memory_usage(deep=True).sum() / 1024**2:.2f} MB")

        # Data types
        self._add_to_report("\nData Types:")
        dtype_counts = self.df.dtypes.value_counts()
        for dtype, count in dtype_counts.items():
            self._add_to_report(f"  {dtype}: {count} columns")

        # Missing values
        missing = self.df.isnull().sum()
        missing_pct = (missing / len(self.df)) * 100
        missing_df = pd.DataFrame({
            'Missing_Count': missing,
            'Missing_Percentage': missing_pct
        }).sort_values('Missing_Count', ascending=False)

        if missing.sum() > 0:
            self._add_to_report(f"\nMissing Values: {missing.sum():,} total")
            self._add_to_report("\nTop 10 Columns with Missing Values:")
            for col, row in missing_df.head(10).iterrows():
                if row['Missing_Count'] > 0:
                    self._add_to_report(f"  {col}: {row['Missing_Count']:,} ({row['Missing_Percentage']:.2f}%)")

            # Visualize missing values
            cols_with_missing = missing_df[missing_df['Missing_Count'] > 0].head(20)
            if len(cols_with_missing) > 0:
                plt.figure(figsize=(10, max(6, len(cols_with_missing) * 0.3)))
                plt.barh(range(len(cols_with_missing)), cols_with_missing['Missing_Percentage'])
                plt.yticks(range(len(cols_with_missing)), cols_with_missing.index)
                plt.xlabel('Missing Percentage (%)')
                plt.title('Top 20 Columns with Missing Values')
                plt.gca().invert_yaxis()
                self._save_fig('missing_values.png')
        else:
            self._add_to_report("\nNo missing values found!")

        # Duplicates
        n_duplicates = self.df.duplicated().sum()
        if n_duplicates > 0:
            self._add_to_report(f"\nDuplicate Rows: {n_duplicates:,} ({n_duplicates/len(self.df)*100:.2f}%)")
        else:
            self._add_to_report("\nNo duplicate rows found!")

        # High cardinality columns
        self._add_to_report("\nColumn Cardinality:")
        for col in self.df.columns:
            n_unique = self.df[col].nunique()
            pct_unique = (n_unique / len(self.df)) * 100
            if pct_unique > 95:
                self._add_to_report(f"  {col}: {n_unique:,} unique ({pct_unique:.1f}%) - HIGH CARDINALITY")
            elif n_unique == 1:
                self._add_to_report(f"  {col}: {n_unique} unique - CONSTANT")

    def analyze_numerical(self):
        """Analyze numerical columns"""
        num_cols = self.df.select_dtypes(include=[np.number]).columns.tolist()

        if not num_cols:
            self._add_to_report("\nNo numerical columns found.")
            return

        self._add_to_report("\n" + "="*80)
        self._add_to_report("NUMERICAL FEATURES ANALYSIS")
        self._add_to_report("="*80)

        # Statistical summary
        self._add_to_report("\nStatistical Summary:")
        summary = self.df[num_cols].describe().T
        summary['skew'] = self.df[num_cols].skew()
        summary['kurtosis'] = self.df[num_cols].kurtosis()

        self._add_to_report(str(summary))

        # Identify skewed features
        skewed_features = summary[abs(summary['skew']) > 1].sort_values('skew', ascending=False)
        if len(skewed_features) > 0:
            self._add_to_report(f"\nHighly Skewed Features (|skew| > 1): {len(skewed_features)}")
            for col in skewed_features.index[:5]:
                self._add_to_report(f"  {col}: skew = {summary.loc[col, 'skew']:.2f}")

        # Distribution plots
        n_cols = min(3, len(num_cols))
        n_rows = (len(num_cols) + n_cols - 1) // n_cols

        fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 4*n_rows))
        axes = axes.flatten() if n_rows > 1 or n_cols > 1 else [axes]

        for idx, col in enumerate(num_cols):
            if idx < len(axes):
                axes[idx].hist(self.df[col].dropna(), bins=30, edgecolor='black', alpha=0.7)
                axes[idx].set_title(f'{col}\n(skew: {summary.loc[col, "skew"]:.2f})')
                axes[idx].set_xlabel(col)
                axes[idx].set_ylabel('Frequency')
                axes[idx].grid(axis='y', alpha=0.3)

        # Remove extra subplots
        for idx in range(len(num_cols), len(axes)):
            fig.delaxes(axes[idx])

        plt.tight_layout()
        self._save_fig('numerical_distributions.png')

        # Box plots for outlier detection
        fig, axes = plt.subplots(n_rows, n_cols, figsize=(15, 4*n_rows))
        axes = axes.flatten() if n_rows > 1 or n_cols > 1 else [axes]

        for idx, col in enumerate(num_cols):
            if idx < len(axes):
                axes[idx].boxplot(self.df[col].dropna())
                axes[idx].set_title(col)
                axes[idx].set_ylabel('Value')
                axes[idx].grid(axis='y', alpha=0.3)

        for idx in range(len(num_cols), len(axes)):
            fig.delaxes(axes[idx])

        plt.tight_layout()
        self._save_fig('numerical_boxplots.png')

        # Correlation matrix
        if len(num_cols) > 1:
            plt.figure(figsize=(min(14, len(num_cols)), min(12, len(num_cols))))
            corr = self.df[num_cols].corr()
            sns.heatmap(corr, annot=True if len(num_cols) <= 10 else False,
                       fmt='.2f', cmap='coolwarm', center=0,
                       square=True, linewidths=1, cbar_kws={"shrink": 0.8})
            plt.title('Correlation Matrix')
            plt.tight_layout()
            self._save_fig('correlation_matrix.png')

            # High correlations
            high_corr = []
            for i in range(len(corr.columns)):
                for j in range(i+1, len(corr.columns)):
                    if abs(corr.iloc[i, j]) > 0.7:
                        high_corr.append((corr.columns[i], corr.columns[j], corr.iloc[i, j]))

            if high_corr:
                self._add_to_report(f"\nHigh Correlations (|r| > 0.7): {len(high_corr)}")
                for col1, col2, corr_val in sorted(high_corr, key=lambda x: abs(x[2]), reverse=True)[:10]:
                    self._add_to_report(f"  {col1} <-> {col2}: {corr_val:.3f}")

    def analyze_categorical(self):
        """Analyze categorical columns"""
        cat_cols = self.df.select_dtypes(include=['object', 'category']).columns.tolist()

        if not cat_cols:
            self._add_to_report("\nNo categorical columns found.")
            return

        self._add_to_report("\n" + "="*80)
        self._add_to_report("CATEGORICAL FEATURES ANALYSIS")
        self._add_to_report("="*80)

        for col in cat_cols:
            n_unique = self.df[col].nunique()
            n_missing = self.df[col].isnull().sum()

            self._add_to_report(f"\n{col}:")
            self._add_to_report(f"  Unique values: {n_unique}")
            self._add_to_report(f"  Missing values: {n_missing}")

            if n_unique <= 20:
                value_counts = self.df[col].value_counts()
                self._add_to_report(f"  Top categories:")
                for cat, count in value_counts.head(10).items():
                    pct = count / len(self.df) * 100
                    self._add_to_report(f"    {cat}: {count:,} ({pct:.1f}%)")

                # Visualization
                plt.figure(figsize=(10, max(6, min(n_unique * 0.4, 12))))
                value_counts.head(20).plot(kind='barh', edgecolor='black', alpha=0.7)
                plt.xlabel('Count')
                plt.title(f'{col} Distribution')
                plt.gca().invert_yaxis()
                plt.tight_layout()
                self._save_fig(f'categorical_{col}.png')
            else:
                self._add_to_report(f"  High cardinality - showing top 5 only")
                value_counts = self.df[col].value_counts()
                for cat, count in value_counts.head(5).items():
                    pct = count / len(self.df) * 100
                    self._add_to_report(f"    {cat}: {count:,} ({pct:.1f}%)")

    def analyze_target(self):
        """Analyze target variable and relationships"""
        if not self.target_col or self.target_col not in self.df.columns:
            return

        self._add_to_report("\n" + "="*80)
        self._add_to_report(f"TARGET VARIABLE ANALYSIS: {self.target_col}")
        self._add_to_report("="*80)

        target = self.df[self.target_col]

        # Target distribution
        if pd.api.types.is_numeric_dtype(target):
            self._add_to_report(f"\nTarget Type: Numerical (Regression Problem)")
            self._add_to_report(f"  Mean: {target.mean():.2f}")
            self._add_to_report(f"  Median: {target.median():.2f}")
            self._add_to_report(f"  Std Dev: {target.std():.2f}")
            self._add_to_report(f"  Min: {target.min():.2f}")
            self._add_to_report(f"  Max: {target.max():.2f}")
            self._add_to_report(f"  Skewness: {target.skew():.2f}")

            # Target distribution plot
            fig, axes = plt.subplots(1, 2, figsize=(14, 5))

            axes[0].hist(target.dropna(), bins=30, edgecolor='black', alpha=0.7)
            axes[0].set_xlabel(self.target_col)
            axes[0].set_ylabel('Frequency')
            axes[0].set_title(f'{self.target_col} Distribution')
            axes[0].grid(axis='y', alpha=0.3)

            axes[1].boxplot(target.dropna())
            axes[1].set_ylabel(self.target_col)
            axes[1].set_title(f'{self.target_col} Box Plot')
            axes[1].grid(axis='y', alpha=0.3)

            plt.tight_layout()
            self._save_fig('target_distribution.png')

            # Correlations with target
            num_cols = self.df.select_dtypes(include=[np.number]).columns.tolist()
            if self.target_col in num_cols:
                num_cols.remove(self.target_col)

            if num_cols:
                correlations = self.df[num_cols + [self.target_col]].corr()[self.target_col].drop(self.target_col)
                correlations = correlations.sort_values(ascending=False)

                self._add_to_report(f"\nTop Correlations with Target:")
                for col, corr in correlations.head(10).items():
                    self._add_to_report(f"  {col}: {corr:.3f}")

                # Visualization
                plt.figure(figsize=(10, max(6, len(correlations.head(20)) * 0.3)))
                correlations.head(20).plot(kind='barh', color=['green' if x > 0 else 'red' for x in correlations.head(20)])
                plt.xlabel('Correlation with Target')
                plt.title(f'Top 20 Feature Correlations with {self.target_col}')
                plt.gca().invert_yaxis()
                plt.axvline(x=0, color='black', linestyle='-', linewidth=0.5)
                plt.tight_layout()
                self._save_fig('target_correlations.png')

        else:
            self._add_to_report(f"\nTarget Type: Categorical (Classification Problem)")
            value_counts = target.value_counts()
            self._add_to_report(f"  Number of classes: {len(value_counts)}")
            self._add_to_report(f"\nClass Distribution:")

            for cls, count in value_counts.items():
                pct = count / len(target) * 100
                self._add_to_report(f"  {cls}: {count:,} ({pct:.1f}%)")

            # Check imbalance
            if len(value_counts) >= 2:
                imbalance_ratio = value_counts.iloc[0] / value_counts.iloc[-1]
                if imbalance_ratio > 3:
                    self._add_to_report(f"\n⚠ WARNING: Class imbalance detected (ratio: {imbalance_ratio:.1f}:1)")

            # Visualization
            fig, axes = plt.subplots(1, 2, figsize=(14, 5))

            value_counts.plot(kind='bar', ax=axes[0], edgecolor='black', alpha=0.7)
            axes[0].set_xlabel(self.target_col)
            axes[0].set_ylabel('Count')
            axes[0].set_title(f'{self.target_col} Distribution')
            axes[0].grid(axis='y', alpha=0.3)
            axes[0].tick_params(axis='x', rotation=45)

            value_counts.plot(kind='pie', ax=axes[1], autopct='%1.1f%%', startangle=90)
            axes[1].set_ylabel('')
            axes[1].set_title(f'{self.target_col} Proportions')

            plt.tight_layout()
            self._save_fig('target_distribution.png')

    def generate_report(self):
        """Generate complete EDA report"""
        self._add_to_report("\n" + "="*80)
        self._add_to_report("AUTOMATED EDA REPORT")
        self._add_to_report(f"Data: {self.data_path}")
        self._add_to_report("="*80)

        # Run all analyses
        self.analyze_data_quality()
        self.analyze_numerical()
        self.analyze_categorical()
        self.analyze_target()

        # Save report
        report_path = self.output_dir / 'eda_report.txt'
        with open(report_path, 'w') as f:
            f.write('\n'.join(self.report_lines))

        self._add_to_report(f"\n{'='*80}")
        self._add_to_report(f"Report saved to: {report_path}")
        self._add_to_report(f"Visualizations saved to: {self.output_dir}")
        self._add_to_report(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description='Automated Exploratory Data Analysis',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python auto_eda.py data.csv
  python auto_eda.py data.csv --target price
  python auto_eda.py sales_data.xlsx --target revenue --output results/
        """
    )

    parser.add_argument('data_file', help='Path to data file (CSV, Excel, etc.)')
    parser.add_argument('--target', '-t', help='Target column name')
    parser.add_argument('--output', '-o', default='eda_output', help='Output directory')

    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.data_file):
        print(f"Error: File not found: {args.data_file}")
        sys.exit(1)

    # Run EDA
    print(f"\nRunning Automated EDA on: {args.data_file}")
    print(f"Output directory: {args.output}\n")

    eda = AutoEDA(args.data_file, target_col=args.target, output_dir=args.output)
    eda.generate_report()


if __name__ == '__main__':
    main()
