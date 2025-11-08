#!/usr/bin/env python3
"""
Project Health Check Script

Analyzes project metrics and generates health assessment based on PMBOK principles.
Provides insights on schedule, cost, quality, risks, and overall project health.

Usage:
    python project_health_check.py <metrics_file> [--output OUTPUT_DIR]

Example:
    python project_health_check.py project_metrics.json --output health_report/
"""

import argparse
import json
import sys
from pathlib import Path
from datetime import datetime

class ProjectHealthChecker:
    """Analyze project health based on key metrics"""

    def __init__(self, metrics_file, output_dir='health_report'):
        """
        Initialize Project Health Checker

        Args:
            metrics_file: Path to JSON file with project metrics
            output_dir: Directory to save output reports
        """
        self.metrics_file = metrics_file
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load metrics
        with open(metrics_file, 'r') as f:
            self.metrics = json.load(f)

        self.health_score = 0
        self.issues = []
        self.warnings = []
        self.recommendations = []

    def analyze_schedule_performance(self):
        """Analyze schedule health using EVM metrics"""
        print("\n" + "="*80)
        print("SCHEDULE PERFORMANCE ANALYSIS")
        print("="*80)

        schedule = self.metrics.get('schedule', {})

        # Calculate SPI
        pv = schedule.get('planned_value', 0)
        ev = schedule.get('earned_value', 0)

        if pv > 0:
            spi = ev / pv
            sv = ev - pv

            print(f"\nSchedule Performance Index (SPI): {spi:.2f}")
            print(f"Schedule Variance (SV): ¥{sv:,.0f}")

            if spi >= 1.0:
                print("  ✓ Status: ON SCHEDULE or AHEAD")
                self.health_score += 20
            elif spi >= 0.9:
                print("  ⚠ Status: SLIGHTLY BEHIND SCHEDULE")
                self.health_score += 15
                self.warnings.append(f"Schedule slightly behind (SPI: {spi:.2f})")
                self.recommendations.append("Monitor critical path activities closely")
            else:
                print("  ✗ Status: SIGNIFICANTLY BEHIND SCHEDULE")
                self.health_score += 5
                self.issues.append(f"Schedule significantly behind (SPI: {spi:.2f})")
                self.recommendations.append("URGENT: Review and update schedule, consider fast-tracking or crashing")

        # Milestone adherence
        milestones = schedule.get('milestones', [])
        if milestones:
            completed = sum(1 for m in milestones if m.get('status') == 'completed')
            total = len(milestones)
            completion_rate = (completed / total) * 100 if total > 0 else 0

            print(f"\nMilestone Completion: {completed}/{total} ({completion_rate:.1f}%)")

            # Check for delayed milestones
            delayed = [m for m in milestones if m.get('status') == 'delayed']
            if delayed:
                print(f"  ⚠ Delayed Milestones: {len(delayed)}")
                for m in delayed:
                    self.warnings.append(f"Milestone delayed: {m.get('name')}")

        return spi if pv > 0 else 1.0

    def analyze_cost_performance(self):
        """Analyze cost health using EVM metrics"""
        print("\n" + "="*80)
        print("COST PERFORMANCE ANALYSIS")
        print("="*80)

        cost = self.metrics.get('cost', {})

        # Calculate CPI
        ev = cost.get('earned_value', 0)
        ac = cost.get('actual_cost', 0)

        if ac > 0:
            cpi = ev / ac
            cv = ev - ac

            print(f"\nCost Performance Index (CPI): {cpi:.2f}")
            print(f"Cost Variance (CV): ¥{cv:,.0f}")

            if cpi >= 1.0:
                print("  ✓ Status: ON BUDGET or UNDER BUDGET")
                self.health_score += 20
            elif cpi >= 0.9:
                print("  ⚠ Status: SLIGHTLY OVER BUDGET")
                self.health_score += 15
                self.warnings.append(f"Cost slightly over budget (CPI: {cpi:.2f})")
                self.recommendations.append("Review cost variances and identify savings")
            else:
                print("  ✗ Status: SIGNIFICANTLY OVER BUDGET")
                self.health_score += 5
                self.issues.append(f"Cost significantly over budget (CPI: {cpi:.2f})")
                self.recommendations.append("URGENT: Review project budget, consider scope reduction or additional funding")

            # Forecast EAC
            bac = cost.get('budget_at_completion', 0)
            if bac > 0 and cpi > 0:
                eac = bac / cpi
                vac = bac - eac
                print(f"\nForecast at Completion (EAC): ¥{eac:,.0f}")
                print(f"Variance at Completion (VAC): ¥{vac:,.0f}")

                if vac < 0:
                    print(f"  ⚠ Projected overrun: ¥{abs(vac):,.0f}")

        return cpi if ac > 0 else 1.0

    def analyze_quality(self):
        """Analyze quality metrics"""
        print("\n" + "="*80)
        print("QUALITY ANALYSIS")
        print("="*80)

        quality = self.metrics.get('quality', {})

        # Defect analysis
        defects = quality.get('defects', {})
        critical = defects.get('critical', 0)
        high = defects.get('high', 0)
        medium = defects.get('medium', 0)
        low = defects.get('low', 0)

        total_defects = critical + high + medium + low

        print(f"\nDefect Summary:")
        print(f"  Critical: {critical}")
        print(f"  High: {high}")
        print(f"  Medium: {medium}")
        print(f"  Low: {low}")
        print(f"  Total: {total_defects}")

        if critical > 0:
            print(f"  ✗ CRITICAL: {critical} critical defects must be resolved")
            self.issues.append(f"{critical} critical defects open")
            self.recommendations.append("URGENT: Resolve all critical defects before proceeding")
            self.health_score += 5
        elif high > 5:
            print(f"  ⚠ Warning: {high} high-severity defects")
            self.warnings.append(f"{high} high-severity defects")
            self.recommendations.append("Prioritize resolution of high-severity defects")
            self.health_score += 10
        else:
            print("  ✓ No critical defects")
            self.health_score += 15

        # Test coverage
        test_coverage = quality.get('test_coverage', 0)
        print(f"\nTest Coverage: {test_coverage}%")

        if test_coverage >= 80:
            print("  ✓ Adequate test coverage")
            self.health_score += 5
        elif test_coverage >= 60:
            print("  ⚠ Test coverage below target")
            self.warnings.append(f"Test coverage at {test_coverage}% (target: 80%)")
            self.recommendations.append("Increase test coverage, especially for critical paths")
            self.health_score += 3
        else:
            print("  ✗ Insufficient test coverage")
            self.issues.append(f"Test coverage only {test_coverage}%")
            self.recommendations.append("URGENT: Significantly increase test coverage before release")
            self.health_score += 1

    def analyze_risks(self):
        """Analyze risk profile"""
        print("\n" + "="*80)
        print("RISK ANALYSIS")
        print("="*80)

        risks = self.metrics.get('risks', {})

        critical = risks.get('critical', 0)
        high = risks.get('high', 0)
        medium = risks.get('medium', 0)
        low = risks.get('low', 0)

        total_risks = critical + high + medium + low

        print(f"\nRisk Summary:")
        print(f"  Critical: {critical}")
        print(f"  High: {high}")
        print(f"  Medium: {medium}")
        print(f"  Low: {low}")
        print(f"  Total: {total_risks}")

        if critical > 0:
            print(f"  ✗ CRITICAL: {critical} critical risks require immediate attention")
            self.issues.append(f"{critical} critical risks")
            self.recommendations.append("URGENT: Escalate critical risks to sponsor, implement mitigation immediately")
            self.health_score += 5
        elif high > 5:
            print(f"  ⚠ Warning: {high} high-priority risks")
            self.warnings.append(f"{high} high-priority risks")
            self.recommendations.append("Active mitigation required for high-priority risks")
            self.health_score += 10
        elif total_risks > 0:
            print("  ✓ Risks under control")
            self.health_score += 15
        else:
            print("  ⚠ No risks identified (may indicate inadequate risk management)")
            self.warnings.append("No risks in register - review risk identification process")
            self.health_score += 10

        # Risk mitigation effectiveness
        mitigation_rate = risks.get('mitigation_effectiveness', 0)
        if mitigation_rate > 0:
            print(f"\nRisk Mitigation Effectiveness: {mitigation_rate}%")
            if mitigation_rate < 70:
                self.warnings.append(f"Risk mitigation effectiveness low ({mitigation_rate}%)")
                self.recommendations.append("Review and strengthen risk response plans")

    def analyze_stakeholder_satisfaction(self):
        """Analyze stakeholder engagement and satisfaction"""
        print("\n" + "="*80)
        print("STAKEHOLDER SATISFACTION ANALYSIS")
        print("="*80)

        stakeholders = self.metrics.get('stakeholders', {})

        satisfaction = stakeholders.get('satisfaction_score', 0)
        print(f"\nStakeholder Satisfaction Score: {satisfaction}/10")

        if satisfaction >= 8.0:
            print("  ✓ High stakeholder satisfaction")
            self.health_score += 10
        elif satisfaction >= 6.0:
            print("  ⚠ Moderate stakeholder satisfaction")
            self.warnings.append(f"Stakeholder satisfaction at {satisfaction}/10")
            self.recommendations.append("Increase stakeholder engagement and communication")
            self.health_score += 5
        else:
            print("  ✗ Low stakeholder satisfaction")
            self.issues.append(f"Low stakeholder satisfaction ({satisfaction}/10)")
            self.recommendations.append("URGENT: Address stakeholder concerns, increase transparency")
            self.health_score += 2

        # Engagement levels
        engagement = stakeholders.get('engagement', {})
        resistant = engagement.get('resistant', 0)
        if resistant > 0:
            print(f"  ⚠ {resistant} resistant stakeholders")
            self.warnings.append(f"{resistant} resistant stakeholders")
            self.recommendations.append("Develop targeted engagement strategies for resistant stakeholders")

    def analyze_team_health(self):
        """Analyze team morale and productivity"""
        print("\n" + "="*80)
        print("TEAM HEALTH ANALYSIS")
        print("="*80)

        team = self.metrics.get('team', {})

        morale = team.get('morale_score', 0)
        print(f"\nTeam Morale Score: {morale}/10")

        if morale >= 7.5:
            print("  ✓ High team morale")
            self.health_score += 10
        elif morale >= 5.0:
            print("  ⚠ Moderate team morale")
            self.warnings.append(f"Team morale at {morale}/10")
            self.recommendations.append("Address team concerns, recognize achievements")
            self.health_score += 5
        else:
            print("  ✗ Low team morale")
            self.issues.append(f"Low team morale ({morale}/10)")
            self.recommendations.append("URGENT: Conduct team retrospective, address burnout concerns")
            self.health_score += 2

        # Velocity (for Agile projects)
        velocity = team.get('velocity', {})
        current = velocity.get('current', 0)
        target = velocity.get('target', 0)

        if current > 0 and target > 0:
            velocity_pct = (current / target) * 100
            print(f"\nTeam Velocity: {current} (target: {target}, {velocity_pct:.1f}%)")

            if velocity_pct >= 90:
                print("  ✓ Team velocity on target")
            else:
                print(f"  ⚠ Team velocity below target ({velocity_pct:.1f}%)")
                self.warnings.append(f"Team velocity at {velocity_pct:.1f}% of target")

    def calculate_overall_health(self):
        """Calculate overall project health score"""
        print("\n" + "="*80)
        print("OVERALL PROJECT HEALTH")
        print("="*80)

        # Normalize score to 100
        max_score = 100
        normalized_score = min(self.health_score, max_score)

        print(f"\nOverall Health Score: {normalized_score}/100")

        if normalized_score >= 80:
            status = "🟢 HEALTHY"
            status_desc = "Project is on track with minor issues"
        elif normalized_score >= 60:
            status = "🟡 AT RISK"
            status_desc = "Project has some concerns requiring attention"
        else:
            status = "🔴 CRITICAL"
            status_desc = "Project requires immediate intervention"

        print(f"Status: {status}")
        print(f"Assessment: {status_desc}")

        return normalized_score, status

    def generate_report(self):
        """Generate comprehensive health report"""
        print("\n" + "="*80)
        print("PROJECT HEALTH CHECK REPORT")
        print(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}")
        print("="*80)

        # Run all analyses
        spi = self.analyze_schedule_performance()
        cpi = self.analyze_cost_performance()
        self.analyze_quality()
        self.analyze_risks()
        self.analyze_stakeholder_satisfaction()
        self.analyze_team_health()

        # Calculate overall health
        score, status = self.calculate_overall_health()

        # Summary
        print("\n" + "="*80)
        print("SUMMARY")
        print("="*80)

        print(f"\n📊 Key Metrics:")
        print(f"  Schedule Performance Index: {spi:.2f}")
        print(f"  Cost Performance Index: {cpi:.2f}")
        print(f"  Overall Health Score: {score}/100")

        if self.issues:
            print(f"\n❌ Critical Issues ({len(self.issues)}):")
            for i, issue in enumerate(self.issues, 1):
                print(f"  {i}. {issue}")

        if self.warnings:
            print(f"\n⚠️  Warnings ({len(self.warnings)}):")
            for i, warning in enumerate(self.warnings, 1):
                print(f"  {i}. {warning}")

        if self.recommendations:
            print(f"\n💡 Recommendations ({len(self.recommendations)}):")
            for i, rec in enumerate(self.recommendations, 1):
                print(f"  {i}. {rec}")

        # Save report
        report_file = self.output_dir / 'health_report.txt'
        self._save_report(report_file, score, status, spi, cpi)

        print(f"\n{'='*80}")
        print(f"Report saved to: {report_file}")
        print(f"{'='*80}\n")

    def _save_report(self, file_path, score, status, spi, cpi):
        """Save report to file"""
        with open(file_path, 'w') as f:
            f.write("PROJECT HEALTH CHECK REPORT\n")
            f.write("="*80 + "\n")
            f.write(f"Generated: {datetime.now().strftime('%Y-%m-%d %H:%M:%S')}\n")
            f.write(f"Project: {self.metrics.get('project_name', 'Unknown')}\n")
            f.write("="*80 + "\n\n")

            f.write("EXECUTIVE SUMMARY\n")
            f.write("-"*80 + "\n")
            f.write(f"Overall Status: {status}\n")
            f.write(f"Health Score: {score}/100\n")
            f.write(f"Schedule Performance Index: {spi:.2f}\n")
            f.write(f"Cost Performance Index: {cpi:.2f}\n\n")

            if self.issues:
                f.write(f"CRITICAL ISSUES ({len(self.issues)})\n")
                f.write("-"*80 + "\n")
                for i, issue in enumerate(self.issues, 1):
                    f.write(f"{i}. {issue}\n")
                f.write("\n")

            if self.warnings:
                f.write(f"WARNINGS ({len(self.warnings)})\n")
                f.write("-"*80 + "\n")
                for i, warning in enumerate(self.warnings, 1):
                    f.write(f"{i}. {warning}\n")
                f.write("\n")

            if self.recommendations:
                f.write(f"RECOMMENDATIONS ({len(self.recommendations)})\n")
                f.write("-"*80 + "\n")
                for i, rec in enumerate(self.recommendations, 1):
                    f.write(f"{i}. {rec}\n")


def main():
    parser = argparse.ArgumentParser(
        description='Project Health Check Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Example metrics file format (JSON):
{
  "project_name": "My Project",
  "schedule": {
    "planned_value": 10000000,
    "earned_value": 9500000,
    "milestones": [
      {"name": "Design Complete", "status": "completed"},
      {"name": "Development Complete", "status": "delayed"}
    ]
  },
  "cost": {
    "earned_value": 9500000,
    "actual_cost": 10500000,
    "budget_at_completion": 20000000
  },
  "quality": {
    "defects": {"critical": 0, "high": 3, "medium": 8, "low": 15},
    "test_coverage": 75
  },
  "risks": {
    "critical": 0,
    "high": 2,
    "medium": 5,
    "low": 10,
    "mitigation_effectiveness": 80
  },
  "stakeholders": {
    "satisfaction_score": 7.5,
    "engagement": {"resistant": 2}
  },
  "team": {
    "morale_score": 7.0,
    "velocity": {"current": 75, "target": 80}
  }
}
        """
    )

    parser.add_argument('metrics_file', help='Path to project metrics JSON file')
    parser.add_argument('--output', '-o', default='health_report',
                       help='Output directory for reports')

    args = parser.parse_args()

    # Validate input file
    if not Path(args.metrics_file).exists():
        print(f"Error: File not found: {args.metrics_file}")
        sys.exit(1)

    # Run health check
    checker = ProjectHealthChecker(args.metrics_file, args.output)
    checker.generate_report()


if __name__ == '__main__':
    main()
