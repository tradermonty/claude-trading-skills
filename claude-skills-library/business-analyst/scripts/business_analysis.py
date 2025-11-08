#!/usr/bin/env python3
"""
Business Analysis Toolkit
==========================

A comprehensive toolkit for business analysts to perform common analysis tasks:
- Financial analysis (ROI, NPV, Payback Period)
- Business metrics calculation
- Data profiling and quality assessment
- Trend analysis
- Comparative analysis

Usage:
    python business_analysis.py <command> [options]

Commands:
    financial       - Perform financial analysis (ROI, NPV, etc.)
    metrics         - Calculate business metrics
    profile         - Profile dataset for quality assessment
    compare         - Compare options using weighted scoring

Examples:
    python business_analysis.py financial --investment 10000000 --annual-benefit 3000000 --years 3
    python business_analysis.py profile data.csv
    python business_analysis.py compare options.json
"""

import argparse
import json
import sys
from typing import Dict, List, Tuple
import pandas as pd
import numpy as np
from datetime import datetime

class FinancialAnalyzer:
    """Financial analysis calculations for business cases"""

    @staticmethod
    def calculate_roi(total_benefit: float, total_cost: float) -> float:
        """Calculate Return on Investment

        Args:
            total_benefit: Total benefits over period
            total_cost: Total costs over period

        Returns:
            ROI as percentage
        """
        if total_cost == 0:
            raise ValueError("Total cost cannot be zero")
        return ((total_benefit - total_cost) / total_cost) * 100

    @staticmethod
    def calculate_payback_period(initial_investment: float, annual_cash_flow: float) -> float:
        """Calculate payback period in years

        Args:
            initial_investment: Upfront investment amount
            annual_cash_flow: Annual net cash flow

        Returns:
            Payback period in years
        """
        if annual_cash_flow <= 0:
            raise ValueError("Annual cash flow must be positive")
        return initial_investment / annual_cash_flow

    @staticmethod
    def calculate_npv(cash_flows: List[float], discount_rate: float = 0.10) -> float:
        """Calculate Net Present Value

        Args:
            cash_flows: List of cash flows by year (Year 0 is initial investment, negative)
            discount_rate: Discount rate (default 10%)

        Returns:
            NPV value
        """
        npv = 0.0
        for year, cash_flow in enumerate(cash_flows):
            npv += cash_flow / ((1 + discount_rate) ** year)
        return npv

    @staticmethod
    def calculate_irr(cash_flows: List[float], guess: float = 0.10) -> float:
        """Calculate Internal Rate of Return

        Args:
            cash_flows: List of cash flows by year
            guess: Initial guess for IRR

        Returns:
            IRR as percentage
        """
        # Simple Newton-Raphson method
        rate = guess
        max_iterations = 100
        tolerance = 0.0001

        for _ in range(max_iterations):
            npv = sum(cf / ((1 + rate) ** i) for i, cf in enumerate(cash_flows))
            npv_derivative = sum(-i * cf / ((1 + rate) ** (i + 1)) for i, cf in enumerate(cash_flows))

            if abs(npv) < tolerance:
                return rate * 100

            if npv_derivative == 0:
                break

            rate = rate - npv / npv_derivative

        return rate * 100

    @staticmethod
    def sensitivity_analysis(
        base_investment: float,
        base_annual_benefit: float,
        years: int,
        discount_rate: float = 0.10
    ) -> Dict[str, Dict[str, float]]:
        """Perform sensitivity analysis on NPV

        Returns:
            Dictionary with best/likely/worst case scenarios
        """
        scenarios = {}

        # Best case: +20% benefit, -10% cost
        best_benefit = base_annual_benefit * 1.20
        best_cost = base_investment * 0.90
        best_cash_flows = [-best_cost] + [best_benefit] * years
        scenarios['best'] = {
            'npv': FinancialAnalyzer.calculate_npv(best_cash_flows, discount_rate),
            'roi': FinancialAnalyzer.calculate_roi(best_benefit * years, best_cost),
            'payback': FinancialAnalyzer.calculate_payback_period(best_cost, best_benefit)
        }

        # Most likely
        likely_cash_flows = [-base_investment] + [base_annual_benefit] * years
        scenarios['likely'] = {
            'npv': FinancialAnalyzer.calculate_npv(likely_cash_flows, discount_rate),
            'roi': FinancialAnalyzer.calculate_roi(base_annual_benefit * years, base_investment),
            'payback': FinancialAnalyzer.calculate_payback_period(base_investment, base_annual_benefit)
        }

        # Worst case: -20% benefit, +10% cost
        worst_benefit = base_annual_benefit * 0.80
        worst_cost = base_investment * 1.10
        worst_cash_flows = [-worst_cost] + [worst_benefit] * years
        scenarios['worst'] = {
            'npv': FinancialAnalyzer.calculate_npv(worst_cash_flows, discount_rate),
            'roi': FinancialAnalyzer.calculate_roi(worst_benefit * years, worst_cost),
            'payback': FinancialAnalyzer.calculate_payback_period(worst_cost, worst_benefit)
        }

        return scenarios

class BusinessMetrics:
    """Common business metrics calculations"""

    @staticmethod
    def calculate_csat(ratings: List[int]) -> Dict[str, float]:
        """Calculate Customer Satisfaction Score

        Args:
            ratings: List of customer ratings (1-10 scale)

        Returns:
            Dict with average, satisfied %, promoter %
        """
        if not ratings:
            return {'average': 0, 'satisfied_pct': 0, 'promoter_pct': 0}

        avg = np.mean(ratings)
        satisfied_pct = len([r for r in ratings if r >= 7]) / len(ratings) * 100
        promoter_pct = len([r for r in ratings if r >= 9]) / len(ratings) * 100

        return {
            'average': round(avg, 2),
            'satisfied_pct': round(satisfied_pct, 1),
            'promoter_pct': round(promoter_pct, 1),
            'total_responses': len(ratings)
        }

    @staticmethod
    def calculate_nps(promoters: int, detractors: int, total: int) -> float:
        """Calculate Net Promoter Score

        Args:
            promoters: Number of promoters (9-10 rating)
            detractors: Number of detractors (0-6 rating)
            total: Total number of respondents

        Returns:
            NPS score (-100 to 100)
        """
        if total == 0:
            return 0.0
        return ((promoters - detractors) / total) * 100

    @staticmethod
    def calculate_churn_rate(customers_lost: int, customers_start: int) -> float:
        """Calculate churn rate

        Returns:
            Churn rate as percentage
        """
        if customers_start == 0:
            return 0.0
        return (customers_lost / customers_start) * 100

    @staticmethod
    def calculate_cltv(
        avg_purchase_value: float,
        purchase_frequency: float,
        customer_lifespan: float
    ) -> float:
        """Calculate Customer Lifetime Value

        Args:
            avg_purchase_value: Average purchase amount
            purchase_frequency: Purchases per year
            customer_lifespan: Expected years as customer

        Returns:
            Customer lifetime value
        """
        return avg_purchase_value * purchase_frequency * customer_lifespan

class DataProfiler:
    """Data profiling and quality assessment"""

    @staticmethod
    def profile_dataset(df: pd.DataFrame) -> Dict:
        """Generate comprehensive data profile

        Args:
            df: Pandas DataFrame to profile

        Returns:
            Profile dictionary with quality metrics
        """
        profile = {
            'overview': {
                'total_rows': len(df),
                'total_columns': len(df.columns),
                'memory_usage_mb': df.memory_usage(deep=True).sum() / (1024 * 1024)
            },
            'columns': {}
        }

        for col in df.columns:
            col_profile = {
                'data_type': str(df[col].dtype),
                'null_count': int(df[col].isnull().sum()),
                'null_pct': round((df[col].isnull().sum() / len(df)) * 100, 2),
                'unique_count': int(df[col].nunique()),
                'unique_pct': round((df[col].nunique() / len(df)) * 100, 2)
            }

            # Numeric columns
            if pd.api.types.is_numeric_dtype(df[col]):
                col_profile.update({
                    'min': float(df[col].min()) if not df[col].isnull().all() else None,
                    'max': float(df[col].max()) if not df[col].isnull().all() else None,
                    'mean': float(df[col].mean()) if not df[col].isnull().all() else None,
                    'median': float(df[col].median()) if not df[col].isnull().all() else None,
                    'std': float(df[col].std()) if not df[col].isnull().all() else None
                })

            # String columns
            elif pd.api.types.is_string_dtype(df[col]) or pd.api.types.is_object_dtype(df[col]):
                non_null = df[col].dropna()
                if len(non_null) > 0:
                    col_profile.update({
                        'avg_length': round(non_null.astype(str).str.len().mean(), 1),
                        'max_length': int(non_null.astype(str).str.len().max()),
                        'top_values': non_null.value_counts().head(5).to_dict()
                    })

            profile['columns'][col] = col_profile

        # Data quality score
        profile['quality_score'] = DataProfiler._calculate_quality_score(df)

        return profile

    @staticmethod
    def _calculate_quality_score(df: pd.DataFrame) -> Dict[str, float]:
        """Calculate data quality dimensions score"""
        total_cells = len(df) * len(df.columns)
        null_cells = df.isnull().sum().sum()

        completeness = ((total_cells - null_cells) / total_cells) * 100

        return {
            'completeness': round(completeness, 2),
            'overall': round(completeness, 2)  # Simplified - could add more dimensions
        }

class ComparativeAnalyzer:
    """Compare and score multiple options"""

    @staticmethod
    def weighted_scoring(
        options: Dict[str, Dict[str, float]],
        weights: Dict[str, float]
    ) -> Dict[str, Dict[str, float]]:
        """Perform weighted scoring analysis

        Args:
            options: Dictionary of options with their scores by criteria
                    Format: {'Option A': {'cost': 8, 'time': 6, ...}, ...}
            weights: Dictionary of weights by criteria (must sum to 1.0)
                    Format: {'cost': 0.4, 'time': 0.3, ...}

        Returns:
            Dictionary with weighted scores and rankings
        """
        # Validate weights sum to 1.0
        if abs(sum(weights.values()) - 1.0) > 0.01:
            raise ValueError(f"Weights must sum to 1.0, got {sum(weights.values())}")

        results = {}
        for option_name, scores in options.items():
            weighted_score = sum(scores[criterion] * weights[criterion]
                               for criterion in weights.keys())
            results[option_name] = {
                'weighted_score': round(weighted_score, 2),
                'detail': scores
            }

        # Add rankings
        sorted_options = sorted(results.items(), key=lambda x: x[1]['weighted_score'], reverse=True)
        for rank, (option_name, _) in enumerate(sorted_options, 1):
            results[option_name]['rank'] = rank

        return results

def financial_command(args):
    """Handle financial analysis command"""
    analyzer = FinancialAnalyzer()

    print("\n" + "="*70)
    print("FINANCIAL ANALYSIS REPORT")
    print("="*70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    # Basic calculations
    initial_investment = args.investment
    annual_benefit = args.annual_benefit
    annual_cost = args.annual_cost if args.annual_cost else 0
    annual_net_benefit = annual_benefit - annual_cost
    years = args.years
    discount_rate = args.discount_rate / 100

    # Cash flows
    cash_flows = [-initial_investment] + [annual_net_benefit] * years

    # Calculate metrics
    total_benefit = annual_net_benefit * years
    total_cost = initial_investment + (annual_cost * years)
    roi = analyzer.calculate_roi(annual_benefit * years, total_cost)
    payback = analyzer.calculate_payback_period(initial_investment, annual_net_benefit)
    npv = analyzer.calculate_npv(cash_flows, discount_rate)
    irr = analyzer.calculate_irr(cash_flows)

    print(f"Investment Parameters:")
    print(f"  Initial Investment: ¥{initial_investment:,.0f}")
    print(f"  Annual Benefit:     ¥{annual_benefit:,.0f}")
    print(f"  Annual Cost:        ¥{annual_cost:,.0f}")
    print(f"  Net Annual Benefit: ¥{annual_net_benefit:,.0f}")
    print(f"  Time Horizon:       {years} years")
    print(f"  Discount Rate:      {discount_rate*100:.1f}%")
    print()

    print("Financial Metrics:")
    print(f"  ROI:                {roi:.1f}%")
    print(f"  NPV:                ¥{npv:,.0f}")
    print(f"  IRR:                {irr:.1f}%")
    print(f"  Payback Period:     {payback:.2f} years")
    print()

    # Interpretation
    print("Interpretation:")
    if npv > 0:
        print("  ✓ NPV is positive - Project adds value")
    else:
        print("  ✗ NPV is negative - Project destroys value")

    if roi > 15:
        print(f"  ✓ ROI ({roi:.1f}%) exceeds typical hurdle rate (15%)")
    else:
        print(f"  ⚠ ROI ({roi:.1f}%) below typical hurdle rate (15%)")

    if payback < 3:
        print(f"  ✓ Payback period ({payback:.2f} years) is acceptable (<3 years)")
    else:
        print(f"  ⚠ Payback period ({payback:.2f} years) is long (>3 years)")
    print()

    # Sensitivity analysis
    if args.sensitivity:
        print("Sensitivity Analysis:")
        print("-" * 70)
        scenarios = analyzer.sensitivity_analysis(initial_investment, annual_net_benefit, years, discount_rate)

        for scenario_name, metrics in scenarios.items():
            print(f"\n{scenario_name.capitalize()} Case:")
            print(f"  NPV:            ¥{metrics['npv']:,.0f}")
            print(f"  ROI:            {metrics['roi']:.1f}%")
            print(f"  Payback:        {metrics['payback']:.2f} years")

    print("\n" + "="*70)

def profile_command(args):
    """Handle data profiling command"""
    try:
        df = pd.read_csv(args.file)
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    profiler = DataProfiler()
    profile = profiler.profile_dataset(df)

    print("\n" + "="*70)
    print("DATA PROFILE REPORT")
    print("="*70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    print("Dataset Overview:")
    print(f"  Total Rows:    {profile['overview']['total_rows']:,}")
    print(f"  Total Columns: {profile['overview']['total_columns']}")
    print(f"  Memory Usage:  {profile['overview']['memory_usage_mb']:.2f} MB")
    print()

    print(f"Data Quality Score:")
    print(f"  Completeness:  {profile['quality_score']['completeness']:.1f}%")
    print(f"  Overall Score: {profile['quality_score']['overall']:.1f}%")
    print()

    print("Column Profiles:")
    print("-" * 70)
    for col_name, col_info in profile['columns'].items():
        print(f"\n{col_name}:")
        print(f"  Type:         {col_info['data_type']}")
        print(f"  Null Count:   {col_info['null_count']} ({col_info['null_pct']}%)")
        print(f"  Unique Count: {col_info['unique_count']} ({col_info['unique_pct']}%)")

        if 'mean' in col_info:
            print(f"  Min:          {col_info['min']}")
            print(f"  Max:          {col_info['max']}")
            print(f"  Mean:         {col_info['mean']:.2f}")
            print(f"  Median:       {col_info['median']}")

        if 'top_values' in col_info:
            print(f"  Top Values:   {list(col_info['top_values'].items())[:3]}")

    print("\n" + "="*70)

    # Save detailed report if requested
    if args.output:
        with open(args.output, 'w') as f:
            json.dump(profile, f, indent=2)
        print(f"\nDetailed profile saved to: {args.output}")

def compare_command(args):
    """Handle options comparison command"""
    try:
        with open(args.file, 'r') as f:
            data = json.load(f)
    except Exception as e:
        print(f"Error loading file: {e}")
        return

    options = data.get('options', {})
    weights = data.get('weights', {})

    analyzer = ComparativeAnalyzer()
    results = analyzer.weighted_scoring(options, weights)

    print("\n" + "="*70)
    print("OPTIONS COMPARISON ANALYSIS")
    print("="*70)
    print(f"Date: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
    print()

    print("Criteria Weights:")
    for criterion, weight in weights.items():
        print(f"  {criterion}: {weight*100:.0f}%")
    print()

    print("Results (Ranked):")
    print("-" * 70)
    sorted_results = sorted(results.items(), key=lambda x: x[1]['rank'])

    for option_name, result in sorted_results:
        print(f"\nRank #{result['rank']}: {option_name}")
        print(f"  Weighted Score: {result['weighted_score']:.2f}")
        print(f"  Detail Scores:")
        for criterion, score in result['detail'].items():
            print(f"    {criterion}: {score}")

    print("\n" + "="*70)

    # Recommendation
    winner = sorted_results[0]
    print(f"\nRecommendation: {winner[0]}")
    print(f"  (Highest weighted score: {winner[1]['weighted_score']:.2f})")
    print()

def main():
    parser = argparse.ArgumentParser(
        description='Business Analysis Toolkit',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    subparsers = parser.add_subparsers(dest='command', help='Analysis command')

    # Financial analysis command
    financial_parser = subparsers.add_parser('financial', help='Financial analysis (ROI, NPV, etc.)')
    financial_parser.add_argument('--investment', type=float, required=True, help='Initial investment amount')
    financial_parser.add_argument('--annual-benefit', type=float, required=True, help='Annual benefit amount')
    financial_parser.add_argument('--annual-cost', type=float, default=0, help='Annual operating cost')
    financial_parser.add_argument('--years', type=int, default=3, help='Number of years to analyze')
    financial_parser.add_argument('--discount-rate', type=float, default=10, help='Discount rate percentage (default: 10)')
    financial_parser.add_argument('--sensitivity', action='store_true', help='Include sensitivity analysis')

    # Data profiling command
    profile_parser = subparsers.add_parser('profile', help='Profile dataset')
    profile_parser.add_argument('file', help='CSV file to profile')
    profile_parser.add_argument('--output', help='Output file for detailed profile (JSON)')

    # Options comparison command
    compare_parser = subparsers.add_parser('compare', help='Compare options using weighted scoring')
    compare_parser.add_argument('file', help='JSON file with options and weights')

    args = parser.parse_args()

    if args.command == 'financial':
        financial_command(args)
    elif args.command == 'profile':
        profile_command(args)
    elif args.command == 'compare':
        compare_command(args)
    else:
        parser.print_help()

if __name__ == '__main__':
    main()
