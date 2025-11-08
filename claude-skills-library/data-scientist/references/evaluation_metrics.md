# Model Evaluation Metrics Guide

## Overview

Choosing the right evaluation metrics is critical for assessing model performance and aligning with business objectives. This guide provides comprehensive coverage of metrics for different problem types.

## Metric Selection Framework

### Key Principles

1. **Align with Business Goals:** Metric should reflect what matters to stakeholders
2. **Use Multiple Metrics:** Single metric rarely tells the complete story
3. **Consider Context:** Same problem may need different metrics in different contexts
4. **Understand Trade-offs:** Be aware of what each metric optimizes for

## Classification Metrics

### Binary Classification

#### Confusion Matrix Components

```
                    Predicted
                Positive    Negative
Actual Positive    TP          FN
       Negative    FP          TN

TP: True Positives  - Correctly predicted positive
FN: False Negatives - Missed positive cases (Type II error)
FP: False Positives - Incorrectly predicted positive (Type I error)
TN: True Negatives  - Correctly predicted negative
```

#### Core Metrics

**Accuracy**
```python
accuracy = (TP + TN) / (TP + TN + FP + FN)
```
- **Use when:** Balanced classes, all errors equally costly
- **Don't use when:** Imbalanced data (misleading)
- **Example:** 95% accuracy meaningless if 95% of data is one class

**Precision (Positive Predictive Value)**
```python
precision = TP / (TP + FP)
```
- **Meaning:** Of all predicted positives, how many were actually positive?
- **Use when:** False positives are costly
- **Examples:**
  - Spam detection (don't want to mark legitimate emails as spam)
  - Medical treatment recommendations (don't want unnecessary treatments)
  - Fraud detection alerts (too many false alarms reduce trust)

**Recall (Sensitivity, True Positive Rate)**
```python
recall = TP / (TP + FN)
```
- **Meaning:** Of all actual positives, how many did we catch?
- **Use when:** False negatives are costly
- **Examples:**
  - Disease screening (don't want to miss sick patients)
  - Fraud detection (must catch fraudulent transactions)
  - Safety-critical systems (can't miss dangerous situations)

**Specificity (True Negative Rate)**
```python
specificity = TN / (TN + FP)
```
- **Meaning:** Of all actual negatives, how many did we correctly identify?
- **Use when:** True negative rate matters (medical tests, security)

**F1 Score**
```python
f1 = 2 * (precision * recall) / (precision + recall)
```
- **Meaning:** Harmonic mean of precision and recall
- **Use when:** Need balance between precision and recall
- **Note:** Weighs precision and recall equally

**F-Beta Score**
```python
f_beta = (1 + beta²) * (precision * recall) / (beta² * precision + recall)
```
- **Beta > 1:** Emphasizes recall (beta=2 common)
- **Beta < 1:** Emphasizes precision (beta=0.5 common)
- **Use when:** Want to weight precision vs recall differently

#### Threshold-Dependent Metrics

**ROC-AUC (Receiver Operating Characteristic - Area Under Curve)**
```python
from sklearn.metrics import roc_auc_score, roc_curve
auc = roc_auc_score(y_true, y_pred_proba)
fpr, tpr, thresholds = roc_curve(y_true, y_pred_proba)
```
- **Range:** 0.5 (random) to 1.0 (perfect)
- **Meaning:** Probability model ranks random positive higher than random negative
- **Use when:**
  - Want threshold-independent metric
  - Classes somewhat balanced
  - Care about ranking quality
- **Don't use when:** Severe class imbalance (use PR-AUC instead)

**PR-AUC (Precision-Recall Area Under Curve)**
```python
from sklearn.metrics import average_precision_score, precision_recall_curve
pr_auc = average_precision_score(y_true, y_pred_proba)
precision, recall, thresholds = precision_recall_curve(y_true, y_pred_proba)
```
- **Use when:**
  - Severe class imbalance
  - Positive class is rare and important
  - More informative than ROC-AUC for imbalanced data

**Matthews Correlation Coefficient (MCC)**
```python
from sklearn.metrics import matthews_corrcoef
mcc = matthews_corrcoef(y_true, y_pred)
```
- **Range:** -1 (total disagreement) to +1 (perfect prediction)
- **Use when:** Imbalanced classes, single balanced metric needed
- **Advantage:** Accounts for all confusion matrix elements

#### Calibration Metrics

**Brier Score**
```python
from sklearn.metrics import brier_score_loss
brier = brier_score_loss(y_true, y_pred_proba)
```
- **Range:** 0 (perfect) to 1 (worst)
- **Meaning:** Mean squared difference between predicted probabilities and actual outcomes
- **Use when:** Probability calibration matters

**Log Loss (Cross-Entropy Loss)**
```python
from sklearn.metrics import log_loss
logloss = log_loss(y_true, y_pred_proba)
```
- **Range:** 0 (perfect) to ∞
- **Use when:** Penalizing confident wrong predictions is important
- **Note:** Heavily penalizes confident misclassifications

### Multi-Class Classification

**Macro-Averaged Metrics**
```python
from sklearn.metrics import precision_score, recall_score, f1_score
precision_macro = precision_score(y_true, y_pred, average='macro')
recall_macro = recall_score(y_true, y_pred, average='macro')
f1_macro = f1_score(y_true, y_pred, average='macro')
```
- **Meaning:** Average metric across classes (equal weight per class)
- **Use when:** All classes equally important regardless of size

**Weighted-Averaged Metrics**
```python
precision_weighted = precision_score(y_true, y_pred, average='weighted')
f1_weighted = f1_score(y_true, y_pred, average='weighted')
```
- **Meaning:** Average metric weighted by class support
- **Use when:** Want to account for class imbalance

**Micro-Averaged Metrics**
```python
precision_micro = precision_score(y_true, y_pred, average='micro')
f1_micro = f1_score(y_true, y_pred, average='micro')
```
- **Meaning:** Calculate metrics globally by counting total TP, FP, FN
- **Use when:** Want to weight by instance, not class

**Cohen's Kappa**
```python
from sklearn.metrics import cohen_kappa_score
kappa = cohen_kappa_score(y_true, y_pred)
```
- **Range:** -1 to 1 (0 = random agreement)
- **Use when:** Want to account for chance agreement

## Regression Metrics

### Error-Based Metrics

**Mean Absolute Error (MAE)**
```python
from sklearn.metrics import mean_absolute_error
mae = mean_absolute_error(y_true, y_pred)
```
- **Meaning:** Average absolute difference between predictions and actual
- **Units:** Same as target variable
- **Advantages:** Easy to interpret, robust to outliers
- **Use when:** Outliers shouldn't dominate, want intuitive metric

**Mean Squared Error (MSE)**
```python
from sklearn.metrics import mean_squared_error
mse = mean_squared_error(y_true, y_pred)
```
- **Meaning:** Average squared difference
- **Units:** Squared units of target
- **Advantages:** Penalizes large errors more
- **Use when:** Large errors are particularly bad

**Root Mean Squared Error (RMSE)**
```python
rmse = np.sqrt(mean_squared_error(y_true, y_pred))
```
- **Meaning:** Square root of MSE
- **Units:** Same as target variable
- **Use when:** Want MSE properties but in original units

**Mean Absolute Percentage Error (MAPE)**
```python
mape = np.mean(np.abs((y_true - y_pred) / y_true)) * 100
```
- **Meaning:** Average absolute percentage error
- **Units:** Percentage
- **Advantages:** Scale-independent, easy to communicate
- **Disadvantages:** Undefined when y_true = 0, asymmetric
- **Use when:** Need percentage-based metric, no zero values

**Symmetric MAPE (sMAPE)**
```python
smape = np.mean(2 * np.abs(y_pred - y_true) / (np.abs(y_true) + np.abs(y_pred))) * 100
```
- **Meaning:** Symmetric version of MAPE
- **Range:** 0% to 200%
- **Use when:** Want symmetry in error measurement

### Variance-Based Metrics

**R² Score (Coefficient of Determination)**
```python
from sklearn.metrics import r2_score
r2 = r2_score(y_true, y_pred)
```
- **Range:** -∞ to 1 (1 = perfect, 0 = baseline mean prediction)
- **Meaning:** Proportion of variance explained by model
- **Use when:** Want to know how much variance is explained
- **Note:** Can be negative if model worse than mean baseline

**Adjusted R²**
```python
n = len(y_true)
p = X.shape[1]  # number of predictors
adj_r2 = 1 - (1 - r2) * (n - 1) / (n - p - 1)
```
- **Use when:** Comparing models with different numbers of features
- **Advantage:** Penalizes adding uninformative features

**Explained Variance Score**
```python
from sklearn.metrics import explained_variance_score
ev = explained_variance_score(y_true, y_pred)
```
- **Range:** -∞ to 1
- **Use when:** Variance explanation more important than bias

### Business-Oriented Metrics

**Mean Percentage Error (MPE)**
```python
mpe = np.mean((y_true - y_pred) / y_true) * 100
```
- **Meaning:** Indicates bias (over/under prediction)
- **Use when:** Direction of error matters

**Weighted Metrics**
```python
# Weight errors by importance
weights = compute_sample_weights(y_true)  # custom function
weighted_mae = np.average(np.abs(y_true - y_pred), weights=weights)
```
- **Use when:** Some predictions more important than others

## Ranking Metrics

**Mean Average Precision @ K (MAP@K)**
```python
def average_precision_at_k(y_true, y_pred, k):
    if len(y_pred) > k:
        y_pred = y_pred[:k]

    score = 0.0
    num_hits = 0.0

    for i, p in enumerate(y_pred):
        if p in y_true and p not in y_pred[:i]:
            num_hits += 1.0
            score += num_hits / (i + 1.0)

    return score / min(len(y_true), k)
```
- **Use when:** Ranking quality matters (recommendations, search)

**Normalized Discounted Cumulative Gain (NDCG)**
```python
from sklearn.metrics import ndcg_score
ndcg = ndcg_score(y_true, y_pred, k=10)
```
- **Range:** 0 to 1
- **Use when:** Position and relevance both matter

## Time Series Metrics

**Mean Absolute Scaled Error (MASE)**
```python
def mase(y_true, y_pred, y_train):
    mae = np.mean(np.abs(y_true - y_pred))
    mae_naive = np.mean(np.abs(np.diff(y_train)))
    return mae / mae_naive
```
- **Meaning:** MAE relative to naive forecast
- **Use when:** Comparing across different time series
- **Advantage:** Scale-independent

**Forecast Bias**
```python
bias = np.mean(y_pred - y_true)
```
- **Meaning:** Systematic over/under prediction
- **Use when:** Direction of error is important

## Clustering Metrics

### Internal Validation (No Ground Truth Needed)

**Silhouette Score**
```python
from sklearn.metrics import silhouette_score
silhouette = silhouette_score(X, cluster_labels)
```
- **Range:** -1 to 1 (higher better)
- **Meaning:** How similar points are to their cluster vs other clusters

**Calinski-Harabasz Index**
```python
from sklearn.metrics import calinski_harabasz_score
ch_score = calinski_harabasz_score(X, cluster_labels)
```
- **Higher is better**
- **Meaning:** Ratio of between-cluster to within-cluster dispersion

**Davies-Bouldin Index**
```python
from sklearn.metrics import davies_bouldin_score
db_score = davies_bouldin_score(X, cluster_labels)
```
- **Lower is better**
- **Meaning:** Average similarity between each cluster and most similar one

### External Validation (Ground Truth Available)

**Adjusted Rand Index (ARI)**
```python
from sklearn.metrics import adjusted_rand_score
ari = adjusted_rand_score(true_labels, predicted_labels)
```
- **Range:** -1 to 1 (1 = perfect, 0 = random)
- **Advantage:** Adjusted for chance

**Normalized Mutual Information (NMI)**
```python
from sklearn.metrics import normalized_mutual_info_score
nmi = normalized_mutual_info_score(true_labels, predicted_labels)
```
- **Range:** 0 to 1
- **Meaning:** Information shared between clusterings

## Custom Business Metrics

### Financial Metrics

**Profit/Loss Based on Predictions**
```python
def profit_metric(y_true, y_pred, cost_fp, cost_fn, reward_tp):
    TP = np.sum((y_true == 1) & (y_pred == 1))
    FP = np.sum((y_true == 0) & (y_pred == 1))
    FN = np.sum((y_true == 1) & (y_pred == 0))

    profit = (TP * reward_tp) - (FP * cost_fp) - (FN * cost_fn)
    return profit
```

**Expected Value Framework**
```python
def expected_value(y_true, y_pred_proba, value_matrix):
    """
    value_matrix: 2x2 matrix of values for [TN, FP, FN, TP]
    """
    expected_val = np.sum([
        (1 - y_true[i]) * (1 - y_pred_proba[i]) * value_matrix[0, 0] +  # TN
        (1 - y_true[i]) * y_pred_proba[i] * value_matrix[0, 1] +         # FP
        y_true[i] * (1 - y_pred_proba[i]) * value_matrix[1, 0] +         # FN
        y_true[i] * y_pred_proba[i] * value_matrix[1, 1]                 # TP
        for i in range(len(y_true))
    ])
    return expected_val
```

## Metric Selection Decision Tree

```
Problem Type?
├─ Classification
│  ├─ Binary
│  │  ├─ Balanced classes?
│  │  │  ├─ Yes → Accuracy, F1, ROC-AUC
│  │  │  └─ No → Precision-Recall AUC, F1, MCC
│  │  ├─ Cost of errors?
│  │  │  ├─ FP costly → Precision, Specificity
│  │  │  └─ FN costly → Recall, Sensitivity
│  │  └─ Probabilities needed?
│  │     └─ Yes → Log Loss, Brier Score, ROC-AUC
│  │
│  └─ Multi-class
│     ├─ All classes equally important? → Macro F1
│     ├─ Weight by class size? → Weighted F1
│     └─ Overall performance? → Accuracy, Micro F1
│
├─ Regression
│  ├─ Outliers present?
│  │  ├─ Yes → MAE, Huber Loss
│  │  └─ No → RMSE, MSE
│  ├─ Percentage errors matter?
│  │  └─ Yes → MAPE, sMAPE
│  └─ Variance explanation?
│     └─ Yes → R², Adjusted R²
│
├─ Ranking
│  └─ → MAP@K, NDCG
│
├─ Clustering
│  ├─ Ground truth available?
│  │  ├─ Yes → ARI, NMI
│  │  └─ No → Silhouette, CH Index
│  │
└─ Time Series
   └─ → MASE, RMSE, MAE, Forecast Bias
```

## Best Practices

### 1. Use Multiple Metrics

Always evaluate with multiple complementary metrics:
- **Classification:** Accuracy + F1 + ROC-AUC + Confusion Matrix
- **Regression:** RMSE + MAE + R² + Residual Plots
- **Imbalanced:** Precision + Recall + F1 + PR-AUC

### 2. Consider Business Context

Translate technical metrics to business impact:
```python
# Example: Customer churn
# Instead of just "95% accuracy"
print(f"We will retain {TP} out of {TP + FN} at-risk customers")
print(f"We will contact {FP} customers unnecessarily")
print(f"Expected revenue saved: ${TP * avg_customer_value}")
print(f"Cost of intervention: ${(TP + FP) * contact_cost}")
```

### 3. Stratified Analysis

Evaluate metrics across different segments:
```python
# Performance by segment
for segment in df['customer_segment'].unique():
    segment_mask = df['customer_segment'] == segment
    segment_f1 = f1_score(y_true[segment_mask], y_pred[segment_mask])
    print(f"{segment}: F1 = {segment_f1:.3f}")
```

### 4. Threshold Optimization

For classification, optimize threshold based on business metric:
```python
from sklearn.metrics import precision_recall_curve

precision, recall, thresholds = precision_recall_curve(y_true, y_pred_proba)

# Custom objective (e.g., maximize profit)
profits = []
for threshold in thresholds:
    y_pred_thresh = (y_pred_proba >= threshold).astype(int)
    profit = profit_metric(y_true, y_pred_thresh, cost_fp=10, cost_fn=50, reward_tp=100)
    profits.append(profit)

optimal_threshold = thresholds[np.argmax(profits)]
```

### 5. Cross-Validation Metrics

Report metrics with confidence intervals:
```python
from sklearn.model_selection import cross_val_score

scores = cross_val_score(model, X, y, cv=5, scoring='f1')
print(f"F1: {scores.mean():.3f} (+/- {scores.std() * 2:.3f})")
```

### 6. Metric Consistency

Ensure metrics align across:
- Training objective
- Validation evaluation
- Test evaluation
- Production monitoring

## Common Pitfalls

1. **Using accuracy on imbalanced data**
   - Solution: Use F1, PR-AUC, or MCC instead

2. **Optimizing for single metric**
   - Solution: Consider multiple metrics and trade-offs

3. **Not considering business costs**
   - Solution: Create custom metrics aligned with business value

4. **Ignoring metric variance**
   - Solution: Use cross-validation and report confidence intervals

5. **Wrong metric for problem type**
   - Solution: Follow decision tree and understand metric properties

6. **Not analyzing errors by segment**
   - Solution: Stratified evaluation and error analysis

7. **Comparing metrics across different scales**
   - Solution: Use appropriate normalization or relative metrics
