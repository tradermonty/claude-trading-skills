# Resource Index

Bundled resources, moved verbatim from `SKILL.md`.

This skill includes the following bundled resources:

### references/breadth_chart_methodology.md

Comprehensive methodology covering:
- **Chart 1 (200MA Breadth)**: Components, interpretation, market regimes, backtested strategy, analysis checklist
- **Chart 2 (Uptrend Ratio)**: Components, interpretation, market conditions, swing trading strategy, analysis checklist
- **Combined Analysis**: Alignment scenarios, integrated decision-making
- **Common Pitfalls**: Mistakes to avoid for each chart type

**Usage**: Read this file before conducting any breadth chart analysis to ensure systematic, accurate interpretation.

### assets/breadth_analysis_template.md

Structured template for breadth analysis reports in English.

**Usage**: Use this template structure for every analysis report.

### assets/SP500_Breadth_Index_200MA_8MA.jpeg

Sample Chart 1 image for format reference.

### assets/US_Stock_Market_Uptrend_Ratio.jpeg

Sample Chart 2 image for format reference.

### scripts/fetch_breadth_csv.py

**PRIMARY data source**. Fetches market breadth, uptrend ratio, and sector summary data from public CSV sources. Uses only stdlib (urllib + csv) -- no external dependencies.

```bash
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py        # Human-readable
python3 skills/breadth-chart-analyst/scripts/fetch_breadth_csv.py --json  # JSON output
```

### scripts/extract_chart_right_edge.py

Extracts the rightmost portion of chart images to help focus on latest data points. Requires PIL/Pillow.

```bash
python3 skills/breadth-chart-analyst/scripts/extract_chart_right_edge.py <image_path> --percent 25
```

### scripts/detect_uptrend_ratio.py (DEPRECATED)

OpenCV-based uptrend ratio detection. Superseded by CSV fetch. Requires opencv-python + numpy.

### scripts/detect_breadth_values.py (DEPRECATED)

OpenCV-based breadth value detection. Superseded by CSV fetch. Requires opencv-python + numpy.
