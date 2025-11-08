#!/usr/bin/env python3
"""
Time Series Analysis Script

Performs comprehensive time series analysis:
- Trend and seasonality decomposition
- Stationarity tests
- Autocorrelation analysis
- Forecasting with multiple models
- Generates visualizations and reports

Usage:
    python timeseries_analysis.py <data_file> <value_col> [--date-col DATE_COL] [--forecast-periods N]

Example:
    python timeseries_analysis.py sales.csv sales --date-col date --forecast-periods 30
"""

import argparse
import os
import sys
import warnings
from pathlib import Path
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from scipy import stats
from statsmodels.tsa.seasonal import seasonal_decompose
from statsmodels.tsa.stattools import adfuller, kpss
from statsmodels.graphics.tsaplots import plot_acf, plot_pacf
from statsmodels.tsa.arima.model import ARIMA
from statsmodels.tsa.holtwinters import ExponentialSmoothing

# Set style
sns.set_style('whitegrid')
sns.set_context('notebook', font_scale=1.1)


class TimeSeriesAnalysis:
    """Comprehensive time series analysis"""

    def __init__(self, data_path, value_col, date_col=None, output_dir='timeseries_analysis'):
        """
        Initialize TimeSeriesAnalysis

        Args:
            data_path: Path to data file
            value_col: Name of value column
            date_col: Name of date column (auto-detected if None)
            output_dir: Directory to save outputs
        """
        self.data_path = data_path
        self.value_col = value_col
        self.date_col = date_col
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load and prepare data
        self.df = self._load_and_prepare_data()
        self.ts = self.df[value_col]

        self.report_lines = []

    def _load_and_prepare_data(self):
        """Load and prepare time series data"""
        file_ext = Path(self.data_path).suffix.lower()

        if file_ext == '.csv':
            df = pd.read_csv(self.data_path)
        elif file_ext in ['.xlsx', '.xls']:
            df = pd.read_excel(self.data_path)
        elif file_ext == '.parquet':
            df = pd.read_parquet(self.data_path)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")

        # Auto-detect date column if not provided
        if not self.date_col:
            date_cols = df.select_dtypes(include=['datetime64']).columns
            if len(date_cols) > 0:
                self.date_col = date_cols[0]
                print(f"Auto-detected date column: {self.date_col}")
            else:
                # Try to find column with 'date' or 'time' in name
                potential_date_cols = [col for col in df.columns if 'date' in col.lower() or 'time' in col.lower()]
                if potential_date_cols:
                    self.date_col = potential_date_cols[0]
                    print(f"Auto-detected date column: {self.date_col}")
                else:
                    print("Warning: No date column detected. Using index as date.")
                    df['index_date'] = pd.date_range(start='2020-01-01', periods=len(df), freq='D')
                    self.date_col = 'index_date'

        # Convert to datetime
        if self.date_col in df.columns:
            df[self.date_col] = pd.to_datetime(df[self.date_col])
            df = df.sort_values(self.date_col).set_index(self.date_col)

        # Handle missing values
        if df[self.value_col].isnull().any():
            n_missing = df[self.value_col].isnull().sum()
            print(f"Warning: {n_missing} missing values detected. Filling with interpolation.")
            df[self.value_col] = df[self.value_col].interpolate(method='linear')

        return df

    def _add_to_report(self, text):
        """Add line to report"""
        self.report_lines.append(text)
        print(text)

    def _save_fig(self, filename):
        """Save current figure"""
        plt.savefig(self.output_dir / filename, dpi=300, bbox_inches='tight')
        plt.close()

    def analyze_basic_stats(self):
        """Analyze basic time series statistics"""
        self._add_to_report("\n" + "="*80)
        self._add_to_report("TIME SERIES BASIC STATISTICS")
        self._add_to_report("="*80)

        self._add_to_report(f"\nData Points: {len(self.ts):,}")
        self._add_to_report(f"Date Range: {self.ts.index.min()} to {self.ts.index.max()}")
        self._add_to_report(f"Duration: {(self.ts.index.max() - self.ts.index.min()).days} days")

        # Infer frequency
        if len(self.ts) > 1:
            freq = pd.infer_freq(self.ts.index)
            if freq:
                self._add_to_report(f"Inferred Frequency: {freq}")
            else:
                self._add_to_report("Frequency: Irregular")

        self._add_to_report(f"\nMean: {self.ts.mean():.2f}")
        self._add_to_report(f"Median: {self.ts.median():.2f}")
        self._add_to_report(f"Std Dev: {self.ts.std():.2f}")
        self._add_to_report(f"Min: {self.ts.min():.2f}")
        self._add_to_report(f"Max: {self.ts.max():.2f}")
        self._add_to_report(f"Coefficient of Variation: {(self.ts.std() / self.ts.mean() * 100):.2f}%")

        # Visualize
        fig, axes = plt.subplots(2, 1, figsize=(14, 10))

        # Time series plot
        axes[0].plot(self.ts.index, self.ts.values, linewidth=1.5)
        axes[0].set_xlabel('Date')
        axes[0].set_ylabel(self.value_col)
        axes[0].set_title(f'Time Series: {self.value_col}')
        axes[0].grid(alpha=0.3)

        # Distribution
        axes[1].hist(self.ts.values, bins=50, edgecolor='black', alpha=0.7)
        axes[1].axvline(self.ts.mean(), color='red', linestyle='--', linewidth=2, label='Mean')
        axes[1].axvline(self.ts.median(), color='green', linestyle='--', linewidth=2, label='Median')
        axes[1].set_xlabel(self.value_col)
        axes[1].set_ylabel('Frequency')
        axes[1].set_title('Distribution')
        axes[1].legend()
        axes[1].grid(axis='y', alpha=0.3)

        plt.tight_layout()
        self._save_fig('basic_stats.png')

    def test_stationarity(self):
        """Test for stationarity"""
        self._add_to_report("\n" + "="*80)
        self._add_to_report("STATIONARITY TESTS")
        self._add_to_report("="*80)

        # Augmented Dickey-Fuller test
        adf_result = adfuller(self.ts.dropna())
        self._add_to_report("\nAugmented Dickey-Fuller Test:")
        self._add_to_report(f"  ADF Statistic: {adf_result[0]:.4f}")
        self._add_to_report(f"  p-value: {adf_result[1]:.4f}")
        self._add_to_report(f"  Critical Values:")
        for key, value in adf_result[4].items():
            self._add_to_report(f"    {key}: {value:.4f}")

        if adf_result[1] < 0.05:
            self._add_to_report("  ✓ Series is STATIONARY (p < 0.05)")
        else:
            self._add_to_report("  ✗ Series is NON-STATIONARY (p >= 0.05)")

        # KPSS test
        kpss_result = kpss(self.ts.dropna(), regression='ct')
        self._add_to_report("\nKPSS Test:")
        self._add_to_report(f"  KPSS Statistic: {kpss_result[0]:.4f}")
        self._add_to_report(f"  p-value: {kpss_result[1]:.4f}")
        self._add_to_report(f"  Critical Values:")
        for key, value in kpss_result[3].items():
            self._add_to_report(f"    {key}: {value:.4f}")

        if kpss_result[1] > 0.05:
            self._add_to_report("  ✓ Series is STATIONARY (p > 0.05)")
        else:
            self._add_to_report("  ✗ Series is NON-STATIONARY (p <= 0.05)")

        # Rolling statistics
        window = min(12, len(self.ts) // 4)
        rolling_mean = self.ts.rolling(window=window).mean()
        rolling_std = self.ts.rolling(window=window).std()

        plt.figure(figsize=(14, 6))
        plt.plot(self.ts.index, self.ts.values, label='Original', alpha=0.7)
        plt.plot(rolling_mean.index, rolling_mean.values, label=f'Rolling Mean (window={window})', linewidth=2)
        plt.plot(rolling_std.index, rolling_std.values, label=f'Rolling Std (window={window})', linewidth=2)
        plt.xlabel('Date')
        plt.ylabel(self.value_col)
        plt.title('Rolling Statistics')
        plt.legend()
        plt.grid(alpha=0.3)
        plt.tight_layout()
        self._save_fig('stationarity.png')

    def decompose_series(self):
        """Decompose time series into components"""
        self._add_to_report("\n" + "="*80)
        self._add_to_report("TIME SERIES DECOMPOSITION")
        self._add_to_report("="*80)

        # Determine period for decomposition
        # Try to infer from data or use common periods
        if len(self.ts) >= 24:
            period = 12  # Monthly seasonality
        elif len(self.ts) >= 14:
            period = 7   # Weekly seasonality
        else:
            self._add_to_report("\nInsufficient data for decomposition (need at least 2 full periods)")
            return

        try:
            # Additive decomposition
            decomposition_add = seasonal_decompose(self.ts, model='additive', period=period)

            fig, axes = plt.subplots(4, 1, figsize=(14, 12))

            decomposition_add.observed.plot(ax=axes[0])
            axes[0].set_ylabel('Observed')
            axes[0].set_title(f'Time Series Decomposition (Additive, period={period})')
            axes[0].grid(alpha=0.3)

            decomposition_add.trend.plot(ax=axes[1])
            axes[1].set_ylabel('Trend')
            axes[1].grid(alpha=0.3)

            decomposition_add.seasonal.plot(ax=axes[2])
            axes[2].set_ylabel('Seasonal')
            axes[2].grid(alpha=0.3)

            decomposition_add.resid.plot(ax=axes[3])
            axes[3].set_ylabel('Residual')
            axes[3].grid(alpha=0.3)

            plt.tight_layout()
            self._save_fig('decomposition_additive.png')

            # Calculate strength of trend and seasonality
            var_resid = np.var(decomposition_add.resid.dropna())
            var_trend = np.var(decomposition_add.trend.dropna())
            var_seasonal = np.var(decomposition_add.seasonal.dropna())

            strength_trend = max(0, 1 - var_resid / (var_trend + var_resid))
            strength_seasonal = max(0, 1 - var_resid / (var_seasonal + var_resid))

            self._add_to_report(f"\nStrength of Trend: {strength_trend:.4f}")
            self._add_to_report(f"Strength of Seasonality: {strength_seasonal:.4f}")

            if strength_trend > 0.6:
                self._add_to_report("  → Strong trend detected")
            elif strength_trend > 0.3:
                self._add_to_report("  → Moderate trend detected")
            else:
                self._add_to_report("  → Weak or no trend")

            if strength_seasonal > 0.6:
                self._add_to_report("  → Strong seasonality detected")
            elif strength_seasonal > 0.3:
                self._add_to_report("  → Moderate seasonality detected")
            else:
                self._add_to_report("  → Weak or no seasonality")

        except Exception as e:
            self._add_to_report(f"\nDecomposition failed: {str(e)}")

    def analyze_autocorrelation(self):
        """Analyze autocorrelation"""
        self._add_to_report("\n" + "="*80)
        self._add_to_report("AUTOCORRELATION ANALYSIS")
        self._add_to_report("="*80)

        fig, axes = plt.subplots(2, 1, figsize=(14, 10))

        # ACF
        plot_acf(self.ts.dropna(), lags=min(40, len(self.ts)//2), ax=axes[0])
        axes[0].set_title('Autocorrelation Function (ACF)')
        axes[0].grid(alpha=0.3)

        # PACF
        plot_pacf(self.ts.dropna(), lags=min(40, len(self.ts)//2), ax=axes[1])
        axes[1].set_title('Partial Autocorrelation Function (PACF)')
        axes[1].grid(alpha=0.3)

        plt.tight_layout()
        self._save_fig('autocorrelation.png')

        self._add_to_report("\nACF and PACF plots generated.")
        self._add_to_report("Use these to identify AR and MA orders for ARIMA modeling.")

    def forecast(self, periods=30):
        """Forecast future values"""
        self._add_to_report("\n" + "="*80)
        self._add_to_report(f"FORECASTING ({periods} periods ahead)")
        self._add_to_report("="*80)

        # Split data
        train_size = int(len(self.ts) * 0.8)
        train, test = self.ts[:train_size], self.ts[train_size:]

        forecasts = {}

        # Simple Moving Average
        window = min(12, len(train) // 4)
        sma_forecast = train.rolling(window=window).mean().iloc[-1]
        forecasts['Simple MA'] = sma_forecast

        # Exponential Smoothing
        try:
            model_es = ExponentialSmoothing(train, seasonal_periods=min(12, len(train)//2),
                                           trend='add', seasonal='add')
            fit_es = model_es.fit()
            es_forecast = fit_es.forecast(steps=len(test))
            forecasts['Exp Smoothing'] = es_forecast.mean()
        except:
            self._add_to_report("\nExponential Smoothing failed (insufficient data or no seasonality)")

        # ARIMA
        try:
            model_arima = ARIMA(train, order=(1, 1, 1))
            fit_arima = model_arima.fit()
            arima_forecast = fit_arima.forecast(steps=len(test))
            forecasts['ARIMA(1,1,1)'] = arima_forecast.mean()

            self._add_to_report(f"\nARIMA Model Summary:")
            self._add_to_report(f"  AIC: {fit_arima.aic:.2f}")
            self._add_to_report(f"  BIC: {fit_arima.bic:.2f}")
        except:
            self._add_to_report("\nARIMA modeling failed")

        # Evaluate on test set
        if len(test) > 0:
            self._add_to_report(f"\nTest Set Performance:")
            for name, pred in forecasts.items():
                if isinstance(pred, (int, float, np.number)):
                    pred_series = pd.Series([pred] * len(test), index=test.index)
                else:
                    pred_series = pred

                mae = np.mean(np.abs(test.values - pred_series.values))
                rmse = np.sqrt(np.mean((test.values - pred_series.values) ** 2))
                mape = np.mean(np.abs((test.values - pred_series.values) / test.values)) * 100

                self._add_to_report(f"  {name}:")
                self._add_to_report(f"    MAE: {mae:.2f}")
                self._add_to_report(f"    RMSE: {rmse:.2f}")
                self._add_to_report(f"    MAPE: {mape:.2f}%")

        # Generate future forecast
        try:
            model_final = ARIMA(self.ts, order=(1, 1, 1))
            fit_final = model_final.fit()
            future_forecast = fit_final.forecast(steps=periods)

            # Visualization
            plt.figure(figsize=(14, 6))
            plt.plot(self.ts.index, self.ts.values, label='Historical', linewidth=2)

            # Create future dates
            last_date = self.ts.index[-1]
            freq = pd.infer_freq(self.ts.index) or 'D'
            future_dates = pd.date_range(start=last_date, periods=periods+1, freq=freq)[1:]

            plt.plot(future_dates, future_forecast, label='Forecast', linewidth=2, color='red', linestyle='--')

            # Add confidence interval
            std_err = np.std(fit_final.resid)
            plt.fill_between(future_dates,
                           future_forecast - 1.96 * std_err,
                           future_forecast + 1.96 * std_err,
                           alpha=0.2, color='red', label='95% Confidence Interval')

            plt.xlabel('Date')
            plt.ylabel(self.value_col)
            plt.title(f'Forecast for Next {periods} Periods')
            plt.legend()
            plt.grid(alpha=0.3)
            plt.tight_layout()
            self._save_fig('forecast.png')

            # Save forecast to CSV
            forecast_df = pd.DataFrame({
                'Date': future_dates,
                'Forecast': future_forecast,
                'Lower_Bound': future_forecast - 1.96 * std_err,
                'Upper_Bound': future_forecast + 1.96 * std_err
            })
            forecast_df.to_csv(self.output_dir / 'forecast.csv', index=False)

            self._add_to_report(f"\nForecast saved to: {self.output_dir / 'forecast.csv'}")

        except Exception as e:
            self._add_to_report(f"\nForecast generation failed: {str(e)}")

    def generate_report(self, forecast_periods=30):
        """Generate complete time series analysis report"""
        self._add_to_report("="*80)
        self._add_to_report("TIME SERIES ANALYSIS REPORT")
        self._add_to_report(f"Data: {self.data_path}")
        self._add_to_report(f"Value Column: {self.value_col}")
        self._add_to_report("="*80)

        self.analyze_basic_stats()
        self.test_stationarity()
        self.decompose_series()
        self.analyze_autocorrelation()
        self.forecast(periods=forecast_periods)

        # Save report
        report_path = self.output_dir / 'timeseries_analysis_report.txt'
        with open(report_path, 'w') as f:
            f.write('\n'.join(self.report_lines))

        self._add_to_report(f"\n{'='*80}")
        self._add_to_report(f"Report saved to: {report_path}")
        self._add_to_report(f"Visualizations saved to: {self.output_dir}")
        self._add_to_report(f"{'='*80}")


def main():
    parser = argparse.ArgumentParser(
        description='Time Series Analysis Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python timeseries_analysis.py sales.csv sales_amount --date-col date
  python timeseries_analysis.py stock_prices.xlsx close --forecast-periods 60
  python timeseries_analysis.py data.csv value --output ts_results/
        """
    )

    parser.add_argument('data_file', help='Path to data file (CSV, Excel, etc.)')
    parser.add_argument('value_col', help='Value column name')
    parser.add_argument('--date-col', '-d', help='Date column name (auto-detected if not specified)')
    parser.add_argument('--forecast-periods', '-f', type=int, default=30,
                       help='Number of periods to forecast (default: 30)')
    parser.add_argument('--output', '-o', default='timeseries_analysis',
                       help='Output directory')

    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.data_file):
        print(f"Error: File not found: {args.data_file}")
        sys.exit(1)

    # Run analysis
    print(f"\nTime Series Analysis Tool")
    print(f"{'='*80}")
    print(f"Data: {args.data_file}")
    print(f"Value Column: {args.value_col}")
    print(f"Output: {args.output}\n")

    analysis = TimeSeriesAnalysis(args.data_file, args.value_col,
                                  date_col=args.date_col,
                                  output_dir=args.output)
    analysis.generate_report(forecast_periods=args.forecast_periods)

    print(f"\n{'='*80}")
    print("Time series analysis complete!")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    main()
