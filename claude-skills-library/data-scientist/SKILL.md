---
name: data-scientist
description: Comprehensive data science workflow skill for analyzing tabular and time series data. Use when conducting exploratory data analysis, building predictive models, performing feature engineering, or generating data-driven insights. Supports end-to-end analysis from data understanding through model deployment, following industry best practices for regression, classification, time series forecasting, and statistical analysis.
---

# Data Scientist

## Overview

Transform raw data into actionable insights using professional data science methodologies. This skill provides comprehensive guidance, automated tools, and best practices for conducting thorough data analysis, building predictive models, and communicating results effectively.

**Core Capabilities:**
- Exploratory Data Analysis (EDA) with automated insights
- Feature engineering and selection strategies
- Model selection and comparison across multiple algorithms
- Time series analysis and forecasting
- Professional visualization and reporting
- Statistical rigor and best practices

## When to Use This Skill

Invoke this skill when working on tasks that involve:

- **Data Analysis:** Understanding patterns, distributions, and relationships in data
- **Predictive Modeling:** Building classification or regression models
- **Time Series:** Analyzing temporal data, forecasting future values
- **Feature Engineering:** Creating and selecting optimal features
- **Model Evaluation:** Comparing algorithms and interpreting results
- **Data Visualization:** Creating professional charts and dashboards
- **Reporting:** Generating comprehensive analysis reports

**Typical User Requests:**
- "Analyze this sales data and find key drivers"
- "Build a model to predict customer churn"
- "Forecast next quarter's revenue based on historical data"
- "Compare different machine learning models for this classification problem"
- "Help me understand what features are most important"
- "Create visualizations to present these findings"

## Analysis Workflow

Follow this systematic approach for comprehensive data science projects:

```
1. Problem Definition
   ↓
2. Data Understanding (EDA)
   ↓
3. Data Preparation & Feature Engineering
   ↓
4. Model Selection & Training
   ↓
5. Model Evaluation & Interpretation
   ↓
6. Insights & Recommendations
   ↓
7. Communication & Deployment
```

### Step 1: Problem Definition and Scoping

**Objective:** Clearly define the business problem and translate it into a data science problem.

**Key Actions:**
1. Understand the business context and objectives
2. Define success criteria and KPIs
3. Identify problem type (classification, regression, time series, clustering)
4. Determine constraints (time, resources, interpretability requirements)

**Questions to Ask:**
- What business decision will this analysis inform?
- What are the success criteria?
- What are the constraints (data, time, computational)?
- Is interpretability important?

**Reference:** See `references/analysis_methodology.md` → "Phase 1: Problem Definition" for detailed guidance.

### Step 2: Data Understanding and Exploration

**Objective:** Gain deep understanding of data characteristics, quality, and patterns.

**Automated EDA:**

Use the `auto_eda.py` script for comprehensive automated analysis:

```bash
python scripts/auto_eda.py data.csv --target target_column --output eda_results/
```

**This generates:**
- Data quality assessment (missing values, duplicates, types)
- Univariate analysis (distributions, outliers)
- Bivariate analysis (correlations, relationships)
- Comprehensive visualizations
- Detailed text report

**Manual Analysis:**

For deeper exploration, read `references/analysis_methodology.md` → "Phase 2: Data Understanding" which covers:
- Missing value patterns and mechanisms
- Outlier detection and treatment
- Distribution analysis
- Correlation and relationship exploration
- Data profiling techniques

**Visualization:**

Use templates from `assets/visualization_template.py`:
- Distribution plots (histograms, box plots, violin plots)
- Correlation heatmaps
- Scatter plots with regression lines
- Pair plots for multivariate analysis

**Key Outputs:**
- Understanding of data quality issues
- Identification of patterns and relationships
- Hypotheses about important features
- Data preparation requirements

### Step 3: Data Preparation and Feature Engineering

**Objective:** Transform raw data into analysis-ready features that capture relevant patterns.

**Feature Engineering Strategies:**

Consult `references/feature_engineering.md` for comprehensive guidance on:

1. **Mathematical Transformations**
   - Log, square root, Box-Cox for skewed distributions
   - Polynomial features for non-linear relationships
   - Scaling and normalization

2. **Encoding Categorical Variables**
   - One-hot encoding for nominal categories
   - Label/ordinal encoding for ordered categories
   - Target encoding for high cardinality
   - Frequency encoding

3. **Creating Interaction Features**
   - Multiplicative interactions (ratios, products)
   - Domain-specific combinations
   - Polynomial feature generation

4. **Time-Based Features** (for temporal data)
   - Date components (year, month, day, hour)
   - Cyclical encoding (sin/cos for circular features)
   - Lag features and rolling statistics
   - Time since/until events

5. **Aggregation Features**
   - Group-by statistics (mean, sum, count, std)
   - Ranking and percentile features
   - Deviation from group statistics

6. **Domain-Specific Features**
   - Financial ratios (profit margin, ROI, debt-to-equity)
   - E-commerce metrics (RFM, CLV, conversion rates)
   - Technical indicators (for financial data)

**Feature Selection:**

Apply feature selection to reduce dimensionality:
- Variance threshold (remove low-variance features)
- Correlation-based filtering
- Feature importance from tree models
- Recursive feature elimination (RFE)
- L1 regularization (Lasso)

**Best Practices:**
- Create features using only training data (avoid data leakage)
- Document all transformations for reproducibility
- Start simple, add complexity incrementally
- Validate feature impact on model performance

### Step 4: Model Selection and Training

**Objective:** Select and train appropriate models based on problem characteristics.

**Automated Model Comparison:**

Use `model_comparison.py` to train and compare multiple models:

```bash
# Regression
python scripts/model_comparison.py data.csv price --problem-type regression --output model_results/

# Classification
python scripts/model_comparison.py data.csv churn --problem-type classification --output model_results/
```

**This evaluates:**
- Linear/Logistic Regression
- Decision Trees
- Random Forest
- Gradient Boosting
- SVM
- KNN
- Additional algorithms

**Outputs:**
- Performance comparison across all models
- Training times
- Visualizations (RMSE/F1 comparison, confusion matrices)
- Best model recommendation

**Manual Model Selection:**

Consult `references/analysis_methodology.md` → "Phase 4: Model Selection" for guidance on:

1. **Problem-Based Selection**
   - Regression: Linear models, tree ensembles, SVR
   - Classification: Logistic regression, tree ensembles, SVM
   - Time series: ARIMA, exponential smoothing, Prophet
   - Imbalanced data: Adjusting class weights, SMOTE, ensemble methods

2. **Data-Based Selection**
   - Small datasets (<10k): Simple models, cross-validation
   - Large datasets (>1M): Gradient boosting, deep learning
   - High dimensionality: Regularization, dimensionality reduction
   - Non-linear relationships: Tree models, polynomial features, neural networks

3. **Requirements-Based Selection**
   - Interpretability needed: Linear models, decision trees, SHAP
   - Real-time prediction: Lightweight models
   - High accuracy: Ensemble methods, gradient boosting

**Training Best Practices:**
- Proper train/validation/test split (typically 60/20/20)
- Cross-validation for robust evaluation
- Hyperparameter tuning (grid search, random search)
- Set random seeds for reproducibility
- Monitor training metrics

### Step 5: Model Evaluation and Interpretation

**Objective:** Rigorously assess model performance and understand predictions.

**Evaluation Metrics:**

Consult `references/evaluation_metrics.md` for comprehensive metric selection:

**Regression:**
- RMSE/MAE: Prediction error in original units
- R²: Proportion of variance explained
- MAPE: Percentage errors (scale-independent)
- Residual analysis: Check assumptions

**Classification:**
- Accuracy: Overall correctness (use only for balanced data)
- Precision/Recall: Trade-off based on cost of errors
- F1 Score: Balanced precision-recall
- ROC-AUC: Threshold-independent performance
- PR-AUC: Better for imbalanced data
- Confusion Matrix: Detailed error breakdown

**Time Series:**
- MASE: Scale-independent forecast error
- Forecast Bias: Systematic over/under prediction
- Coverage: Confidence interval accuracy

**Model Interpretation:**

Use interpretation techniques to understand predictions:

1. **Global Interpretability** (overall model behavior)
   - Feature importance from tree models
   - SHAP summary plots
   - Partial dependence plots

2. **Local Interpretability** (individual predictions)
   - SHAP values for specific instances
   - LIME explanations
   - Counterfactual analysis

3. **Visualization:**

Use `assets/visualization_template.py` for:
- Confusion matrices
- ROC/PR curves
- Residual plots
- Feature importance charts
- Learning curves
- Actual vs predicted plots

**Validation:**
- Cross-validation scores with confidence intervals
- Stratified analysis (performance by segment)
- Error analysis (patterns in misclassifications)
- Business metric assessment (profit, ROI, etc.)

### Step 6: Time Series Analysis

**Objective:** Analyze temporal patterns and forecast future values.

**For Time Series Data:**

Use the specialized `timeseries_analysis.py` script:

```bash
python scripts/timeseries_analysis.py sales.csv revenue --date-col date --forecast-periods 30 --output ts_results/
```

**This provides:**
- Stationarity tests (ADF, KPSS)
- Seasonal decomposition (trend, seasonality, residuals)
- Autocorrelation analysis (ACF, PACF)
- Multiple forecasting models (ARIMA, Exponential Smoothing)
- Forecast with confidence intervals
- Comprehensive visualizations

**Time Series Considerations:**

Consult `references/analysis_methodology.md` for time series-specific guidance:
- Handling seasonality and trends
- Differencing for stationarity
- Feature engineering for time series (lags, rolling stats)
- Train/test splitting for temporal data
- Forecast evaluation metrics

**Visualization:**

Use `assets/visualization_template.py` → time series functions:
- Line plots with moving averages
- Seasonal decomposition plots
- Autocorrelation plots
- Forecast visualizations

### Step 7: Insights and Recommendations

**Objective:** Translate technical findings into actionable business insights.

**Insight Generation:**

1. **Identify Key Patterns**
   - What are the strongest drivers?
   - Which segments behave differently?
   - What unexpected patterns emerged?

2. **Quantify Impact**
   - How much improvement from baseline?
   - What's the expected ROI?
   - What's the confidence level?

3. **Provide Context**
   - How do results compare to industry benchmarks?
   - What are the limitations?
   - What assumptions were made?

4. **Create Recommendations**
   - Specific, actionable steps
   - Prioritized by impact and feasibility
   - Include implementation guidance

**Report Generation:**

Use `assets/analysis_report_template.md` as a starting point:

The template includes:
- Executive summary with key findings
- Business problem and objectives
- Data overview and quality assessment
- EDA findings
- Feature engineering approach
- Model results and comparison
- Business insights and recommendations
- Limitations and next steps
- Technical appendix

**Customize the template** based on:
- Audience (technical vs non-technical)
- Project complexity
- Stakeholder requirements
- Deployment context

## Advanced Topics

### Handling Imbalanced Data

For classification with severe class imbalance:

1. **Resampling Techniques:**
   - SMOTE (Synthetic Minority Over-sampling)
   - Random under-sampling majority class
   - Combination approaches

2. **Algorithm-Level:**
   - Adjust class weights
   - Use algorithms designed for imbalance (e.g., balanced Random Forest)
   - Ensemble methods

3. **Metric Selection:**
   - Don't use accuracy
   - Use Precision-Recall AUC
   - F1 score, Matthews Correlation Coefficient
   - Consider business costs in metric

Reference: `references/evaluation_metrics.md` → Binary Classification section

### Feature Engineering for Domain-Specific Problems

**Financial Data:**
- Price changes and returns
- Technical indicators (SMA, EMA, RSI, MACD)
- Financial ratios
- Volatility measures

**E-commerce:**
- RFM (Recency, Frequency, Monetary) analysis
- Customer lifetime value proxies
- Shopping cart metrics
- Discount utilization rates

**Healthcare:**
- BMI and health risk scores
- Age-adjusted features
- Medication interaction flags

Reference: `references/feature_engineering.md` → "Domain-Specific Features"

### Model Ensemble Techniques

Combine multiple models for better performance:

1. **Voting/Averaging:** Combine predictions from multiple models
2. **Stacking:** Train meta-model on base model predictions
3. **Boosting:** Sequential learning (already built into XGBoost, LightGBM)
4. **Bagging:** Random Forest principle applied to other algorithms

### Deployment Considerations

When preparing models for production:

1. **Model Serialization:**
   ```python
   import joblib
   joblib.dump(model, 'model.pkl')
   joblib.dump(scaler, 'scaler.pkl')
   ```

2. **Pipeline Creation:**
   ```python
   from sklearn.pipeline import Pipeline
   pipeline = Pipeline([
       ('scaler', StandardScaler()),
       ('model', RandomForestClassifier())
   ])
   ```

3. **Monitoring Plan:**
   - Track prediction distributions
   - Monitor model performance metrics
   - Detect data drift
   - Set up retraining triggers

Reference: `references/analysis_methodology.md` → "Phase 7: Deployment Considerations"

## Best Practices Summary

### Do's:
✓ Start with problem definition and success criteria
✓ Perform thorough EDA before modeling
✓ Use proper train/test splits to avoid data leakage
✓ Apply cross-validation for robust evaluation
✓ Use multiple metrics to assess performance
✓ Interpret and explain model predictions
✓ Document all steps for reproducibility
✓ Validate assumptions (e.g., residuals for regression)
✓ Consider business context and constraints
✓ Communicate results clearly to stakeholders

### Don'ts:
✗ Skip EDA and jump straight to modeling
✗ Use test data for feature engineering
✗ Rely on single metric (especially accuracy for imbalanced data)
✗ Ignore outliers without investigation
✗ Over-engineer features without validation
✗ Forget to set random seeds
✗ Use correlation to imply causation
✗ Deploy models without monitoring plans
✗ Ignore model limitations
✗ Present results without business context

## Quick Reference: Common Workflows

### Workflow 1: Classification Project

1. Load data → run `auto_eda.py`
2. Review EDA output → identify issues
3. Engineer features based on EDA insights
4. Run `model_comparison.py` for classification
5. Analyze best model → check confusion matrix, feature importance
6. Interpret with SHAP if needed
7. Generate report using template
8. Provide recommendations

### Workflow 2: Regression Project

1. Load data → run `auto_eda.py`
2. Review distributions → check for skewness
3. Transform skewed features (log, Box-Cox)
4. Create interaction/polynomial features if needed
5. Run `model_comparison.py` for regression
6. Analyze residuals → check assumptions
7. Identify important features
8. Generate insights and recommendations

### Workflow 3: Time Series Forecasting

1. Load temporal data → check for gaps
2. Run `timeseries_analysis.py`
3. Review decomposition → understand trend/seasonality
4. Check stationarity tests
5. Create lag features and rolling statistics
6. Compare forecasting models
7. Evaluate forecast accuracy
8. Generate forecast with confidence intervals

### Workflow 4: Exploratory Analysis Only

1. Run `auto_eda.py` for initial understanding
2. Use `visualization_template.py` for custom plots
3. Investigate specific relationships
4. Document findings
5. Generate insights without modeling
6. Recommend next steps or data collection

## Resources

This skill includes three types of bundled resources:

### scripts/

Automated tools for common data science tasks:

- **`auto_eda.py`**: Comprehensive automated exploratory data analysis
  - Generates data quality report
  - Creates distribution visualizations
  - Analyzes correlations and relationships
  - Saves detailed text report and charts

- **`model_comparison.py`**: Train and compare multiple ML models
  - Supports regression and classification
  - Evaluates 7-9 algorithms automatically
  - Generates performance comparison visualizations
  - Identifies best model with detailed metrics

- **`timeseries_analysis.py`**: Specialized time series analysis
  - Stationarity testing
  - Seasonal decomposition
  - Autocorrelation analysis
  - Forecasting with multiple models

**Usage:** Execute these scripts directly from command line or integrate into analysis workflow.

### references/

Comprehensive methodology guides to inform analysis decisions:

- **`analysis_methodology.md`**: Complete data science workflow
  - 7-phase analysis framework
  - Decision trees for method selection
  - Best practices checklist
  - Common pitfalls to avoid

- **`feature_engineering.md`**: Feature creation and selection
  - 10 categories of feature engineering techniques
  - Code examples for each technique
  - Feature selection methods
  - Domain-specific features

- **`evaluation_metrics.md`**: Model evaluation guide
  - Metrics for classification, regression, clustering
  - When to use each metric
  - Metric selection decision tree
  - Custom business metrics

- **`visualization_guide.md`**: Data visualization patterns
  - Chart type selection guide
  - EDA visualizations
  - Model performance visualizations
  - Best practices and styling

**Usage:** Read these references when making methodological decisions or needing detailed guidance on specific techniques.

### assets/

Templates and boilerplate for creating outputs:

- **`visualization_template.py`**: Professional visualization functions
  - Distribution plots
  - Relationship visualizations
  - Time series charts
  - Model performance plots
  - Fully customizable templates

- **`analysis_report_template.md`**: Comprehensive report structure
  - Executive summary
  - Methodology documentation
  - Results presentation
  - Recommendations format
  - Professional formatting

**Usage:** Copy and customize these templates for creating visualizations and reports tailored to specific projects.

## Troubleshooting Common Issues

**Issue: Model overfitting (high train score, low test score)**
- Solution: Use regularization (Ridge, Lasso, ElasticNet)
- Reduce model complexity
- Collect more training data
- Use cross-validation for tuning
- Reference: `analysis_methodology.md` → "Phase 5: Model Diagnostics"

**Issue: Poor performance on imbalanced data**
- Solution: Don't use accuracy as metric
- Apply SMOTE or class weighting
- Use ensemble methods
- Consider anomaly detection approaches
- Reference: `evaluation_metrics.md` → "Classification Metrics"

**Issue: Time series forecasts are inaccurate**
- Solution: Check for stationarity (use differencing if needed)
- Ensure proper handling of seasonality
- Create more lag features
- Try ensemble of multiple forecast methods
- Reference: Use `timeseries_analysis.py` for diagnostics

**Issue: Features not improving model**
- Solution: Check for data leakage
- Validate features actually add information
- Remove highly correlated features
- Try feature selection methods
- Reference: `feature_engineering.md` → "Feature Selection"

**Issue: Cannot interpret "black box" model**
- Solution: Use SHAP values for interpretation
- Try simpler baseline (linear model, decision tree)
- Create partial dependence plots
- Use LIME for local explanations
- Balance accuracy vs interpretability trade-off

## Examples

### Example 1: Customer Churn Prediction

**User Request:** "Help me build a model to predict which customers will churn next month"

**Workflow:**

1. **Problem Definition:**
   - Classification problem (churn: Yes/No)
   - Success metric: Maximize recall (don't miss churners) while maintaining reasonable precision
   - Timeline: Need predictions monthly

2. **EDA:**
   ```bash
   python scripts/auto_eda.py customer_data.csv --target churned --output churn_eda/
   ```
   - Review output for data quality issues
   - Identify key patterns in churned vs retained customers

3. **Feature Engineering:**
   - Create RFM features (recency, frequency, monetary)
   - Calculate usage metrics (login frequency, feature usage)
   - Create tenure-based features
   - Reference `feature_engineering.md` → "E-commerce Domain"

4. **Model Training:**
   ```bash
   python scripts/model_comparison.py customer_data.csv churned --problem-type classification --output churn_models/
   ```
   - Review F1 scores and ROC-AUC
   - Check confusion matrix of best model

5. **Interpretation:**
   - Analyze feature importance
   - Use SHAP to understand churner characteristics
   - Identify actionable patterns

6. **Recommendations:**
   - Target high-risk customers with retention campaigns
   - Improve features with high churn correlation
   - Set up monthly retraining schedule

### Example 2: Sales Forecasting

**User Request:** "Forecast next quarter's revenue based on 2 years of daily sales data"

**Workflow:**

1. **Time Series Analysis:**
   ```bash
   python scripts/timeseries_analysis.py sales_history.csv revenue --date-col date --forecast-periods 90 --output sales_forecast/
   ```

2. **Review Outputs:**
   - Check decomposition for trend and seasonality
   - Examine stationarity tests
   - Compare ARIMA vs Exponential Smoothing performance

3. **Feature Engineering (if using ML approach):**
   - Create lag features (7-day, 30-day lags)
   - Add rolling statistics (mean, std over windows)
   - Include calendar features (day of week, month, holidays)
   - Reference `feature_engineering.md` → "Time-Based Features"

4. **Model Selection:**
   - Compare statistical methods (ARIMA, Prophet) vs ML methods (XGBoost with time features)
   - Evaluate using MASE and MAE

5. **Deliverables:**
   - 90-day forecast with confidence intervals
   - Identification of key drivers (seasonality, trends, events)
   - Recommendations for inventory and staffing

---

**For additional guidance:** Always start by consulting the relevant sections in the `references/` directory based on your specific analysis phase and problem type.
