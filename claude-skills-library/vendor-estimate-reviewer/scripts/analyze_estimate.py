#!/usr/bin/env python3
"""
Vendor Estimate Analysis Script

This script analyzes vendor estimates from Excel, CSV, or PDF files and generates
a comprehensive Markdown review report with findings and recommendations.

Usage:
    python analyze_estimate.py <input_file> [options]

Options:
    --output, -o       Output Markdown file path (default: estimate_review_report.md)
    --vendor           Vendor name
    --project          Project name
    --budget           Client budget (for comparison)
    --template         Report template to use (default, executive, detailed)
    --rates-file       JSON file with market rate benchmarks
    --verbose, -v      Verbose output

Examples:
    python analyze_estimate.py vendor_estimate.xlsx -o review.md --vendor "Acme Corp" --project "CRM System"
    python analyze_estimate.py estimate.csv --budget 500000 --template executive
"""

import argparse
import json
import sys
from datetime import datetime
from pathlib import Path
from typing import Dict, List, Optional, Tuple
import re

# Optional imports with graceful fallback
try:
    import pandas as pd
    HAS_PANDAS = True
except ImportError:
    HAS_PANDAS = False
    print("Warning: pandas not installed. Excel/CSV analysis limited.", file=sys.stderr)

try:
    import openpyxl
    HAS_OPENPYXL = True
except ImportError:
    HAS_OPENPYXL = False

try:
    import PyPDF2
    HAS_PYPDF2 = True
except ImportError:
    HAS_PYPDF2 = False


class EstimateAnalyzer:
    """Analyzes vendor estimates and generates review reports."""

    def __init__(self, verbose: bool = False):
        self.verbose = verbose
        self.findings = []
        self.warnings = []
        self.risks = []
        self.recommendations = []

        # Default market rate benchmarks (USD/hour)
        self.market_rates = {
            "Software Engineer": {"junior": 60, "mid": 100, "senior": 150, "expert": 220},
            "Project Manager": {"junior": 70, "mid": 110, "senior": 170, "expert": 240},
            "QA Engineer": {"junior": 50, "mid": 80, "senior": 120, "expert": 180},
            "DevOps Engineer": {"junior": 80, "mid": 120, "senior": 180, "expert": 260},
            "UI/UX Designer": {"junior": 60, "mid": 100, "senior": 150, "expert": 220},
            "Business Analyst": {"junior": 60, "mid": 100, "senior": 150, "expert": 210},
            "Architect": {"mid": 140, "senior": 190, "expert": 280},
        }

        # Expected phase distribution
        self.expected_distribution = {
            "Requirements": (0.10, 0.15),
            "Design": (0.15, 0.20),
            "Development": (0.40, 0.50),
            "Testing": (0.15, 0.25),
            "Deployment": (0.05, 0.10),
        }

    def log(self, message: str):
        """Print verbose log message."""
        if self.verbose:
            print(f"[INFO] {message}")

    def load_rates_from_file(self, rates_file: Path):
        """Load market rate benchmarks from JSON file."""
        try:
            with open(rates_file, 'r') as f:
                self.market_rates = json.load(f)
            self.log(f"Loaded market rates from {rates_file}")
        except Exception as e:
            print(f"Warning: Could not load rates file: {e}", file=sys.stderr)

    def parse_estimate_file(self, file_path: Path) -> Dict:
        """Parse estimate file and extract structured data."""
        suffix = file_path.suffix.lower()

        if suffix in ['.xlsx', '.xls'] and HAS_PANDAS:
            return self._parse_excel(file_path)
        elif suffix == '.csv' and HAS_PANDAS:
            return self._parse_csv(file_path)
        elif suffix == '.pdf' and HAS_PYPDF2:
            return self._parse_pdf(file_path)
        else:
            raise ValueError(f"Unsupported file format: {suffix}")

    def _parse_excel(self, file_path: Path) -> Dict:
        """Parse Excel file."""
        self.log(f"Parsing Excel file: {file_path}")

        # Try to read all sheets
        excel_file = pd.ExcelFile(file_path)
        data = {}

        for sheet_name in excel_file.sheet_names:
            df = pd.read_excel(file_path, sheet_name=sheet_name)
            data[sheet_name] = df

        # Try to identify the main estimate sheet
        estimate_data = self._extract_estimate_data(data)

        return estimate_data

    def _parse_csv(self, file_path: Path) -> Dict:
        """Parse CSV file."""
        self.log(f"Parsing CSV file: {file_path}")

        df = pd.read_csv(file_path)
        data = {"main": df}

        estimate_data = self._extract_estimate_data(data)

        return estimate_data

    def _parse_pdf(self, file_path: Path) -> Dict:
        """Parse PDF file (basic text extraction)."""
        self.log(f"Parsing PDF file: {file_path}")

        with open(file_path, 'rb') as f:
            reader = PyPDF2.PdfReader(f)
            text = ""
            for page in reader.pages:
                text += page.extract_text()

        # Basic extraction (this is simplified - production would need more sophisticated parsing)
        estimate_data = {
            "raw_text": text,
            "items": [],
            "total_cost": self._extract_total_from_text(text),
        }

        return estimate_data

    def _extract_estimate_data(self, data: Dict) -> Dict:
        """Extract structured estimate data from parsed file."""
        estimate_data = {
            "items": [],
            "phases": {},
            "resources": [],
            "total_hours": 0,
            "total_cost": 0,
        }

        # Look for estimate sheet (heuristic: most data, contains numeric columns)
        main_df = None
        for sheet_name, df in data.items():
            if df is not None and len(df) > 0:
                main_df = df
                break

        if main_df is None:
            return estimate_data

        # Try to identify columns
        col_mapping = self._identify_columns(main_df)

        # Extract items
        for idx, row in main_df.iterrows():
            try:
                item = {
                    "description": row.get(col_mapping.get("description", ""), ""),
                    "hours": float(row.get(col_mapping.get("hours", 0), 0)),
                    "rate": float(row.get(col_mapping.get("rate", 0), 0)),
                    "cost": float(row.get(col_mapping.get("cost", 0), 0)),
                    "phase": row.get(col_mapping.get("phase", ""), ""),
                    "role": row.get(col_mapping.get("role", ""), ""),
                }

                if item["hours"] > 0 or item["cost"] > 0:
                    estimate_data["items"].append(item)
                    estimate_data["total_hours"] += item["hours"]
                    estimate_data["total_cost"] += item["cost"]

                    # Aggregate by phase
                    phase = item["phase"] or "Other"
                    if phase not in estimate_data["phases"]:
                        estimate_data["phases"][phase] = {"hours": 0, "cost": 0}
                    estimate_data["phases"][phase]["hours"] += item["hours"]
                    estimate_data["phases"][phase]["cost"] += item["cost"]
            except (ValueError, TypeError, KeyError):
                continue

        return estimate_data

    def _identify_columns(self, df: pd.DataFrame) -> Dict:
        """Identify column names using heuristics."""
        col_mapping = {}

        columns_lower = {col: col.lower() for col in df.columns}

        # Description
        for col, col_lower in columns_lower.items():
            if any(keyword in col_lower for keyword in ["description", "task", "activity", "item", "deliverable"]):
                col_mapping["description"] = col
                break

        # Hours
        for col, col_lower in columns_lower.items():
            if any(keyword in col_lower for keyword in ["hours", "effort", "time", "duration"]):
                col_mapping["hours"] = col
                break

        # Rate
        for col, col_lower in columns_lower.items():
            if any(keyword in col_lower for keyword in ["rate", "price", "hourly"]):
                col_mapping["rate"] = col
                break

        # Cost
        for col, col_lower in columns_lower.items():
            if any(keyword in col_lower for keyword in ["cost", "amount", "total", "price"]) and col not in [col_mapping.get("rate")]:
                col_mapping["cost"] = col
                break

        # Phase
        for col, col_lower in columns_lower.items():
            if any(keyword in col_lower for keyword in ["phase", "stage", "milestone", "module"]):
                col_mapping["phase"] = col
                break

        # Role
        for col, col_lower in columns_lower.items():
            if any(keyword in col_lower for keyword in ["role", "resource", "position", "title"]):
                col_mapping["role"] = col
                break

        return col_mapping

    def _extract_total_from_text(self, text: str) -> float:
        """Extract total cost from text using patterns."""
        # Look for patterns like "Total: $500,000" or "Grand Total: 500000"
        patterns = [
            r"(?:total|grand total|sum)[\s:$]*([0-9,]+(?:\.[0-9]{2})?)",
            r"\$([0-9,]+(?:\.[0-9]{2})?)"
        ]

        for pattern in patterns:
            matches = re.findall(pattern, text, re.IGNORECASE)
            if matches:
                try:
                    # Take the largest number found
                    amounts = [float(m.replace(',', '')) for m in matches]
                    return max(amounts)
                except ValueError:
                    continue

        return 0

    def analyze_estimate(self, estimate_data: Dict, budget: Optional[float] = None) -> Dict:
        """Perform comprehensive analysis of the estimate."""
        self.log("Analyzing estimate...")

        analysis = {
            "summary": {},
            "phase_analysis": {},
            "rate_analysis": {},
            "risk_assessment": {},
            "recommendations": [],
        }

        # Summary metrics
        analysis["summary"] = {
            "total_hours": estimate_data["total_hours"],
            "total_cost": estimate_data["total_cost"],
            "item_count": len(estimate_data["items"]),
            "phase_count": len(estimate_data["phases"]),
            "budget": budget,
            "budget_variance": ((estimate_data["total_cost"] - budget) / budget * 100) if budget else None,
        }

        # Phase distribution analysis
        if estimate_data["total_hours"] > 0:
            for phase, data in estimate_data["phases"].items():
                percentage = data["hours"] / estimate_data["total_hours"]

                phase_analysis = {
                    "hours": data["hours"],
                    "cost": data["cost"],
                    "percentage": percentage * 100,
                    "status": "unknown"
                }

                # Check against expected distribution
                for expected_phase, (min_pct, max_pct) in self.expected_distribution.items():
                    if expected_phase.lower() in phase.lower():
                        if percentage < min_pct:
                            phase_analysis["status"] = "low"
                            self.warnings.append(f"{phase} phase is {percentage*100:.1f}% (expected {min_pct*100}-{max_pct*100}%) - may be underestimated")
                        elif percentage > max_pct:
                            phase_analysis["status"] = "high"
                            self.warnings.append(f"{phase} phase is {percentage*100:.1f}% (expected {min_pct*100}-{max_pct*100}%) - may be overestimated")
                        else:
                            phase_analysis["status"] = "normal"
                        break

                analysis["phase_analysis"][phase] = phase_analysis

        # Check for missing phases
        expected_phases_lower = {p.lower() for p in self.expected_distribution.keys()}
        found_phases_lower = {p.lower() for p in estimate_data["phases"].keys()}
        missing_phases = expected_phases_lower - found_phases_lower

        if missing_phases:
            self.warnings.append(f"Missing phases: {', '.join(missing_phases)}")

        # Cost analysis
        if budget and estimate_data["total_cost"] > 0:
            variance = analysis["summary"]["budget_variance"]
            if variance > 10:
                self.warnings.append(f"Estimate exceeds budget by {variance:.1f}%")
            elif variance < -20:
                self.warnings.append(f"Estimate is {abs(variance):.1f}% below budget - may be too optimistic")

        # Risk assessment
        analysis["risk_assessment"] = self._assess_risks(estimate_data, analysis)

        # Generate recommendations
        analysis["recommendations"] = self._generate_recommendations(estimate_data, analysis)

        return analysis

    def _assess_risks(self, estimate_data: Dict, analysis: Dict) -> Dict:
        """Assess risks in the estimate."""
        risks = {
            "high": [],
            "medium": [],
            "low": [],
        }

        # Check for very low testing effort
        testing_pct = 0
        for phase, data in analysis["phase_analysis"].items():
            if "test" in phase.lower():
                testing_pct += data["percentage"]

        if testing_pct < 15:
            risks["high"].append({
                "category": "Quality Assurance",
                "risk": "Insufficient testing effort",
                "detail": f"Testing is {testing_pct:.1f}% of total effort (recommended: 15-25%)",
                "impact": "High defect rates, production issues",
                "mitigation": "Increase testing allocation to 20% minimum"
            })

        # Check for missing contingency
        if "contingency" not in str(estimate_data).lower() and "buffer" not in str(estimate_data).lower():
            risks["medium"].append({
                "category": "Risk Management",
                "risk": "No contingency buffer identified",
                "detail": "No explicit contingency or buffer in estimate",
                "impact": "Cost overruns on unexpected issues",
                "mitigation": "Add 15-20% contingency reserve"
            })

        # Check for round numbers (suggests rough estimation)
        round_number_count = sum(1 for item in estimate_data["items"]
                                 if item["hours"] > 0 and item["hours"] % 10 == 0)
        if len(estimate_data["items"]) > 0:
            round_number_pct = round_number_count / len(estimate_data["items"])
            if round_number_pct > 0.7:
                risks["medium"].append({
                    "category": "Estimation Quality",
                    "risk": "High proportion of round numbers",
                    "detail": f"{round_number_pct*100:.0f}% of items are round numbers (10, 20, 50, 100, etc.)",
                    "impact": "Estimates may be rough/unrefined",
                    "mitigation": "Request detailed task breakdown"
                })

        # Check for very large items (poor granularity)
        large_items = [item for item in estimate_data["items"] if item["hours"] > 200]
        if large_items:
            risks["medium"].append({
                "category": "Estimation Granularity",
                "risk": "Large task items detected",
                "detail": f"{len(large_items)} items exceed 200 hours",
                "impact": "Difficult to track progress, hidden complexity",
                "mitigation": "Break down large items into smaller tasks (< 80 hours each)"
            })

        return risks

    def _generate_recommendations(self, estimate_data: Dict, analysis: Dict) -> List[str]:
        """Generate actionable recommendations."""
        recommendations = []

        # Budget recommendations
        if analysis["summary"].get("budget_variance"):
            variance = analysis["summary"]["budget_variance"]
            if variance > 10:
                recommendations.append("**Budget**: Negotiate scope reduction or phased delivery to meet budget constraints")
            elif variance < -20:
                recommendations.append("**Budget**: Validate with vendor - unusually low estimate may indicate missing scope")

        # Phase recommendations
        for warning in self.warnings:
            if "phase" in warning.lower():
                recommendations.append(f"**Scope**: {warning}")

        # Quality recommendations
        recommendations.append("**Quality**: Verify testing approach includes unit, integration, system, and UAT levels")
        recommendations.append("**Risk Management**: Request risk register with mitigation strategies")

        # Resource recommendations
        recommendations.append("**Resources**: Request team composition details (senior/mid/junior ratio)")
        recommendations.append("**Resources**: Ensure key resources have >= 80% allocation")

        # Contract recommendations
        recommendations.append("**Contract**: Define clear acceptance criteria for each milestone")
        recommendations.append("**Contract**: Include 10-15% payment holdback until warranty period ends")

        # Process recommendations
        recommendations.append("**Process**: Request weekly status reports and bi-weekly demos")
        recommendations.append("**Process**: Define change request process with impact assessment")

        return recommendations

    def generate_markdown_report(
        self,
        estimate_data: Dict,
        analysis: Dict,
        output_file: Path,
        vendor: str = "Unknown Vendor",
        project: str = "Unknown Project",
        template: str = "default"
    ):
        """Generate comprehensive Markdown review report."""
        self.log(f"Generating report: {output_file}")

        report_lines = []

        # Header
        report_lines.append(f"# Vendor Estimate Review Report")
        report_lines.append(f"")
        report_lines.append(f"**Project**: {project}")
        report_lines.append(f"**Vendor**: {vendor}")
        report_lines.append(f"**Review Date**: {datetime.now().strftime('%Y-%m-%d')}")
        report_lines.append(f"**Reviewer**: Generated by Estimate Analyzer")
        report_lines.append(f"")
        report_lines.append(f"---")
        report_lines.append(f"")

        # Executive Summary
        report_lines.append(f"## Executive Summary")
        report_lines.append(f"")

        summary = analysis["summary"]
        report_lines.append(f"| Metric | Value |")
        report_lines.append(f"|--------|-------|")
        report_lines.append(f"| **Total Estimated Cost** | ${summary['total_cost']:,.2f} |")
        report_lines.append(f"| **Total Estimated Hours** | {summary['total_hours']:,.0f} hours |")
        report_lines.append(f"| **Average Rate** | ${summary['total_cost']/summary['total_hours'] if summary['total_hours'] > 0 else 0:.2f}/hour |")
        if summary.get("budget"):
            report_lines.append(f"| **Client Budget** | ${summary['budget']:,.2f} |")
            report_lines.append(f"| **Budget Variance** | {summary['budget_variance']:+.1f}% |")
        report_lines.append(f"| **Line Items** | {summary['item_count']} |")
        report_lines.append(f"| **Project Phases** | {summary['phase_count']} |")
        report_lines.append(f"")

        # Overall Assessment
        report_lines.append(f"### Overall Assessment")
        report_lines.append(f"")

        risk_count = sum(len(risks) for risks in analysis["risk_assessment"].values())
        if risk_count == 0:
            report_lines.append(f"✅ **LOW RISK** - Estimate appears reasonable with no major concerns identified.")
        elif risk_count <= 3:
            report_lines.append(f"⚠️ **MEDIUM RISK** - {risk_count} concerns identified that should be addressed.")
        else:
            report_lines.append(f"🚨 **HIGH RISK** - {risk_count} significant concerns require clarification and revision.")
        report_lines.append(f"")

        # Phase Distribution Analysis
        if analysis["phase_analysis"]:
            report_lines.append(f"## Phase Distribution Analysis")
            report_lines.append(f"")
            report_lines.append(f"| Phase | Hours | Cost | % of Total | Status |")
            report_lines.append(f"| ----- | ----- | ---- | ---------- | ------ |")

            for phase, data in sorted(analysis["phase_analysis"].items(), key=lambda x: x[1]["hours"], reverse=True):
                status_icon = {
                    "normal": "✅",
                    "low": "⚠️",
                    "high": "⚠️",
                    "unknown": "ℹ️"
                }.get(data["status"], "")

                report_lines.append(
                    f"| {phase} | {data['hours']:,.0f} | ${data['cost']:,.2f} | "
                    f"{data['percentage']:.1f}% | {status_icon} {data['status'].title()} |"
                )
            report_lines.append(f"")
            report_lines.append(f"**Expected Phase Distribution** (Industry Standards):")
            report_lines.append(f"")
            for phase, (min_pct, max_pct) in self.expected_distribution.items():
                report_lines.append(f"- {phase}: {min_pct*100:.0f}-{max_pct*100:.0f}%")
            report_lines.append(f"")

        # Warnings and Concerns
        if self.warnings:
            report_lines.append(f"## ⚠️ Warnings and Concerns")
            report_lines.append(f"")
            for i, warning in enumerate(self.warnings, 1):
                report_lines.append(f"{i}. {warning}")
            report_lines.append(f"")

        # Risk Assessment
        report_lines.append(f"## Risk Assessment")
        report_lines.append(f"")

        for risk_level in ["high", "medium", "low"]:
            risks = analysis["risk_assessment"].get(risk_level, [])
            if risks:
                icon = {"high": "🚨", "medium": "⚠️", "low": "ℹ️"}[risk_level]
                report_lines.append(f"### {icon} {risk_level.title()} Risk Items")
                report_lines.append(f"")

                for risk in risks:
                    report_lines.append(f"**{risk['category']}: {risk['risk']}**")
                    report_lines.append(f"")
                    report_lines.append(f"- **Detail**: {risk['detail']}")
                    report_lines.append(f"- **Impact**: {risk['impact']}")
                    report_lines.append(f"- **Mitigation**: {risk['mitigation']}")
                    report_lines.append(f"")

        if not any(analysis["risk_assessment"].values()):
            report_lines.append(f"✅ No significant risks identified in initial analysis.")
            report_lines.append(f"")

        # Recommendations
        report_lines.append(f"## Recommendations")
        report_lines.append(f"")

        for i, recommendation in enumerate(analysis["recommendations"], 1):
            report_lines.append(f"{i}. {recommendation}")
        report_lines.append(f"")

        # Detailed Line Items (if not too many)
        if template == "detailed" and len(estimate_data["items"]) <= 50:
            report_lines.append(f"## Detailed Line Items")
            report_lines.append(f"")
            report_lines.append(f"| Description | Hours | Rate | Cost | Phase |")
            report_lines.append(f"|-------------|-------|------|------|-------|")

            for item in estimate_data["items"]:
                report_lines.append(
                    f"| {item['description'][:50]} | {item['hours']:.1f} | "
                    f"${item['rate']:.2f} | ${item['cost']:,.2f} | {item['phase']} |"
                )
            report_lines.append(f"")

        # Next Steps
        report_lines.append(f"## Next Steps")
        report_lines.append(f"")
        report_lines.append(f"1. **Review with Vendor**: Discuss identified concerns and request clarifications")
        report_lines.append(f"2. **Request Revisions**: Ask vendor to address high-risk items and warnings")
        report_lines.append(f"3. **Validate Assumptions**: Confirm all assumptions documented in estimate")
        report_lines.append(f"4. **Negotiate Terms**: Focus on payment milestones, warranties, and change process")
        report_lines.append(f"5. **Final Decision**: Make go/no-go decision based on revised estimate")
        report_lines.append(f"")

        # Footer
        report_lines.append(f"---")
        report_lines.append(f"")
        report_lines.append(f"*This report was generated automatically by the Vendor Estimate Analyzer.*")
        report_lines.append(f"*For comprehensive review, also consult the Review Checklist, Cost Estimation Standards, and Risk Factors references.*")

        # Write to file
        with open(output_file, 'w', encoding='utf-8') as f:
            f.write('\n'.join(report_lines))

        print(f"✅ Review report generated: {output_file}")


def main():
    parser = argparse.ArgumentParser(
        description="Analyze vendor estimates and generate review reports",
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog=__doc__
    )

    parser.add_argument("input_file", type=Path, help="Input estimate file (Excel, CSV, or PDF)")
    parser.add_argument("-o", "--output", type=Path, default=Path("estimate_review_report.md"),
                       help="Output Markdown file (default: estimate_review_report.md)")
    parser.add_argument("--vendor", default="Unknown Vendor", help="Vendor name")
    parser.add_argument("--project", default="Unknown Project", help="Project name")
    parser.add_argument("--budget", type=float, help="Client budget for comparison")
    parser.add_argument("--template", choices=["default", "executive", "detailed"],
                       default="default", help="Report template")
    parser.add_argument("--rates-file", type=Path, help="JSON file with market rate benchmarks")
    parser.add_argument("-v", "--verbose", action="store_true", help="Verbose output")

    args = parser.parse_args()

    # Check input file exists
    if not args.input_file.exists():
        print(f"Error: Input file not found: {args.input_file}", file=sys.stderr)
        return 1

    # Check dependencies
    if not HAS_PANDAS and args.input_file.suffix.lower() in ['.xlsx', '.xls', '.csv']:
        print("Error: pandas is required for Excel/CSV analysis. Install with: pip install pandas openpyxl",
              file=sys.stderr)
        return 1

    if not HAS_PYPDF2 and args.input_file.suffix.lower() == '.pdf':
        print("Error: PyPDF2 is required for PDF analysis. Install with: pip install PyPDF2",
              file=sys.stderr)
        return 1

    # Create analyzer
    analyzer = EstimateAnalyzer(verbose=args.verbose)

    # Load custom rates if provided
    if args.rates_file:
        analyzer.load_rates_from_file(args.rates_file)

    try:
        # Parse estimate file
        print(f"📄 Parsing estimate file: {args.input_file}")
        estimate_data = analyzer.parse_estimate_file(args.input_file)

        # Analyze estimate
        print(f"🔍 Analyzing estimate...")
        analysis = analyzer.analyze_estimate(estimate_data, budget=args.budget)

        # Generate report
        print(f"📝 Generating review report...")
        analyzer.generate_markdown_report(
            estimate_data=estimate_data,
            analysis=analysis,
            output_file=args.output,
            vendor=args.vendor,
            project=args.project,
            template=args.template
        )

        print(f"\n✅ Analysis complete!")
        print(f"📊 Total Cost: ${estimate_data['total_cost']:,.2f}")
        print(f"⏱️  Total Hours: {estimate_data['total_hours']:,.0f}")
        print(f"⚠️  Warnings: {len(analyzer.warnings)}")

        return 0

    except Exception as e:
        print(f"Error during analysis: {e}", file=sys.stderr)
        if args.verbose:
            import traceback
            traceback.print_exc()
        return 1


if __name__ == "__main__":
    sys.exit(main())
