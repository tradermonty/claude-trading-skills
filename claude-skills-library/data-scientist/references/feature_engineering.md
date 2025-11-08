# Feature Engineering Guide

## Overview

Feature engineering is the process of creating new features or transforming existing ones to improve model performance. This is often the most impactful step in the data science workflow.

## Feature Engineering Principles

### The Feature Engineering Mindset

1. **Domain Knowledge First:** Best features come from understanding the business context
2. **Iterative Process:** Create features, test, analyze, refine
3. **Start Simple:** Begin with obvious transformations, then get creative
4. **Monitor Impact:** Track feature importance and contribution
5. **Balance Complexity:** More features ≠ better model (curse of dimensionality)

## Feature Creation Techniques

### 1. Mathematical Transformations

**Purpose:** Improve linearity, normality, or reduce skewness

**Common Transformations:**

```python
# Log transformation (for right-skewed data)
df['log_value'] = np.log1p(df['value'])  # log(1+x) to handle zeros

# Square root (moderate skewness)
df['sqrt_value'] = np.sqrt(df['value'])

# Box-Cox transformation (automatic optimization)
from scipy.stats import boxcox
df['boxcox_value'], lambda_param = boxcox(df['value'])

# Yeo-Johnson (handles negative values)
from sklearn.preprocessing import PowerTransformer
pt = PowerTransformer(method='yeo-johnson')
df['yeojohnson_value'] = pt.fit_transform(df[['value']])

# Reciprocal transformation
df['reciprocal_value'] = 1 / (df['value'] + 1)  # +1 to avoid division by zero

# Polynomial features
df['value_squared'] = df['value'] ** 2
df['value_cubed'] = df['value'] ** 3
```

**When to Use:**
- Right-skewed distributions → log, sqrt
- Left-skewed distributions → square, exponential
- U-shaped relationships → polynomial
- Heteroscedasticity in residuals → various transformations

### 2. Scaling and Normalization

**Purpose:** Bring features to comparable scales

**Techniques:**

```python
from sklearn.preprocessing import StandardScaler, MinMaxScaler, RobustScaler

# Standardization (mean=0, std=1) - sensitive to outliers
scaler = StandardScaler()
df['standardized'] = scaler.fit_transform(df[['value']])

# Min-Max Scaling (range [0,1]) - preserves shape, sensitive to outliers
scaler = MinMaxScaler()
df['normalized'] = scaler.fit_transform(df[['value']])

# Robust Scaling (uses median and IQR) - resistant to outliers
scaler = RobustScaler()
df['robust_scaled'] = scaler.fit_transform(df[['value']])

# Max Abs Scaling (preserves sparsity)
from sklearn.preprocessing import MaxAbsScaler
scaler = MaxAbsScaler()
df['maxabs_scaled'] = scaler.fit_transform(df[['value']])
```

**When to Use:**
- Neural networks, SVM, KNN → Standardization or Min-Max
- Outliers present → Robust Scaling
- Sparse data → Max Abs Scaling
- Tree-based models → Usually not needed

### 3. Binning and Discretization

**Purpose:** Convert continuous variables to categorical, capture non-linear relationships

```python
# Equal-width binning
df['age_bin'] = pd.cut(df['age'], bins=5, labels=['Very Young', 'Young', 'Middle', 'Senior', 'Elderly'])

# Equal-frequency binning (quantiles)
df['income_quartile'] = pd.qcut(df['income'], q=4, labels=['Q1', 'Q2', 'Q3', 'Q4'])

# Custom bins based on domain knowledge
age_bins = [0, 18, 30, 45, 60, 100]
age_labels = ['Minor', 'Young Adult', 'Adult', 'Middle Age', 'Senior']
df['age_category'] = pd.cut(df['age'], bins=age_bins, labels=age_labels)

# Automated binning with optimal splits
from sklearn.tree import DecisionTreeClassifier
dt = DecisionTreeClassifier(max_leaf_nodes=5)
dt.fit(df[['value']], df['target'])
df['value_bin'] = dt.predict(df[['value']])
```

**When to Use:**
- Capture non-linear relationships in linear models
- Reduce impact of outliers
- Create interpretable categories
- Handle missing values as a separate category

### 4. Encoding Categorical Variables

**Techniques:**

```python
# One-Hot Encoding (for nominal categories with low cardinality)
df_encoded = pd.get_dummies(df, columns=['category'], prefix='cat')

# Label Encoding (for ordinal categories or tree-based models)
from sklearn.preprocessing import LabelEncoder
le = LabelEncoder()
df['category_encoded'] = le.fit_transform(df['category'])

# Ordinal Encoding (when order matters)
from sklearn.preprocessing import OrdinalEncoder
ordinal_map = {'Low': 1, 'Medium': 2, 'High': 3}
df['priority_encoded'] = df['priority'].map(ordinal_map)

# Target Encoding (mean encoding)
# Replace category with mean of target variable
target_mean = df.groupby('category')['target'].mean()
df['category_target_encoded'] = df['category'].map(target_mean)

# Frequency Encoding
freq = df['category'].value_counts(normalize=True)
df['category_freq'] = df['category'].map(freq)

# Binary Encoding (for high cardinality)
import category_encoders as ce
encoder = ce.BinaryEncoder(cols=['category'])
df_encoded = encoder.fit_transform(df)

# Hashing (for very high cardinality)
from sklearn.feature_extraction import FeatureHasher
hasher = FeatureHasher(n_features=10, input_type='string')
hashed = hasher.transform(df['category'])
```

**When to Use:**
- One-Hot: Low cardinality (<10-15 categories), nominal
- Label: Ordinal data, tree-based models
- Target: High cardinality, risk of overfitting (use with care)
- Frequency: When frequency contains information
- Binary/Hashing: Very high cardinality (>100 categories)

### 5. Interaction Features

**Purpose:** Capture relationships between features

```python
# Multiplicative interactions
df['price_per_sqft'] = df['price'] / df['sqft']
df['speed'] = df['distance'] / df['time']

# Additive interactions
df['total_score'] = df['math_score'] + df['reading_score'] + df['writing_score']

# Ratio features
df['debt_to_income'] = df['debt'] / (df['income'] + 1)
df['conversion_rate'] = df['conversions'] / (df['visits'] + 1)

# Boolean combinations
df['premium_young'] = (df['is_premium'] == 1) & (df['age'] < 30)
df['high_risk'] = (df['credit_score'] < 600) | (df['income'] < 30000)

# Polynomial features (automated interaction creation)
from sklearn.preprocessing import PolynomialFeatures
poly = PolynomialFeatures(degree=2, interaction_only=True, include_bias=False)
interactions = poly.fit_transform(df[['feature1', 'feature2', 'feature3']])
```

**When to Use:**
- Domain knowledge suggests relationships
- Linear models need to capture non-linear patterns
- After analyzing feature importance and correlations

### 6. Aggregation Features

**Purpose:** Create summary statistics from grouped data

```python
# Basic aggregations
customer_stats = df.groupby('customer_id').agg({
    'purchase_amount': ['sum', 'mean', 'std', 'min', 'max', 'count'],
    'days_since_purchase': ['min', 'mean'],
    'product_category': 'nunique'
})

# Flatten multi-index columns
customer_stats.columns = ['_'.join(col).strip() for col in customer_stats.columns.values]

# Time-based aggregations
df['total_last_30days'] = df.groupby('customer_id')['amount'].transform(
    lambda x: x.rolling(window=30, min_periods=1).sum()
)

# Cumulative features
df['cumulative_spend'] = df.groupby('customer_id')['amount'].cumsum()
df['purchase_number'] = df.groupby('customer_id').cumcount() + 1

# Rank features
df['amount_rank'] = df.groupby('customer_id')['amount'].rank(method='dense')

# Deviation from group statistics
df['amount_vs_customer_avg'] = df['amount'] - df.groupby('customer_id')['amount'].transform('mean')
df['price_vs_category_median'] = df['price'] / df.groupby('category')['price'].transform('median')
```

**When to Use:**
- Customer behavior analysis
- Product performance metrics
- Comparing individual to group behavior
- Time-based patterns

### 7. Time-Based Features

**Purpose:** Extract temporal patterns and relationships

```python
# Basic datetime components
df['year'] = df['date'].dt.year
df['month'] = df['date'].dt.month
df['day'] = df['date'].dt.day
df['day_of_week'] = df['date'].dt.dayofweek
df['day_of_year'] = df['date'].dt.dayofyear
df['week_of_year'] = df['date'].dt.isocalendar().week
df['quarter'] = df['date'].dt.quarter
df['hour'] = df['date'].dt.hour

# Cyclical encoding (preserves circular nature)
df['month_sin'] = np.sin(2 * np.pi * df['month'] / 12)
df['month_cos'] = np.cos(2 * np.pi * df['month'] / 12)
df['hour_sin'] = np.sin(2 * np.pi * df['hour'] / 24)
df['hour_cos'] = np.cos(2 * np.pi * df['hour'] / 24)

# Boolean time features
df['is_weekend'] = df['day_of_week'].isin([5, 6]).astype(int)
df['is_month_end'] = df['date'].dt.is_month_end.astype(int)
df['is_month_start'] = df['date'].dt.is_month_start.astype(int)
df['is_quarter_end'] = df['date'].dt.is_quarter_end.astype(int)

# Business day features
from pandas.tseries.holiday import USFederalHolidayCalendar
cal = USFederalHolidayCalendar()
holidays = cal.holidays(start=df['date'].min(), end=df['date'].max())
df['is_holiday'] = df['date'].isin(holidays).astype(int)

# Time since/until events
df['days_since_launch'] = (df['date'] - pd.to_datetime('2020-01-01')).dt.days
df['days_until_year_end'] = (df['date'].dt.year.astype(str) + '-12-31' - df['date']).dt.days

# Lag features (for time series)
df['sales_lag_1'] = df.groupby('store_id')['sales'].shift(1)
df['sales_lag_7'] = df.groupby('store_id')['sales'].shift(7)
df['sales_lag_30'] = df.groupby('store_id')['sales'].shift(30)

# Rolling statistics
df['sales_rolling_mean_7'] = df.groupby('store_id')['sales'].transform(
    lambda x: x.rolling(window=7, min_periods=1).mean()
)
df['sales_rolling_std_7'] = df.groupby('store_id')['sales'].transform(
    lambda x: x.rolling(window=7, min_periods=1).std()
)

# Expanding statistics (cumulative)
df['sales_expanding_mean'] = df.groupby('store_id')['sales'].transform(
    lambda x: x.expanding(min_periods=1).mean()
)

# Time differences
df['days_since_last_purchase'] = df.groupby('customer_id')['date'].diff().dt.days
df['time_between_events'] = df.groupby('user_id')['timestamp'].diff().dt.total_seconds()
```

**When to Use:**
- Time series forecasting
- Seasonality detection
- Event-based analysis
- Customer behavior over time

### 8. Text Feature Engineering

**Purpose:** Extract information from text data

```python
# Basic text features
df['text_length'] = df['text'].str.len()
df['word_count'] = df['text'].str.split().str.len()
df['char_count'] = df['text'].apply(len)
df['avg_word_length'] = df['char_count'] / (df['word_count'] + 1)

# Specific character counts
df['uppercase_count'] = df['text'].str.count(r'[A-Z]')
df['punctuation_count'] = df['text'].str.count(r'[^\w\s]')
df['digit_count'] = df['text'].str.count(r'\d')
df['special_char_count'] = df['text'].str.count(r'[!@#$%^&*()]')

# Sentiment and subjectivity (requires textblob)
from textblob import TextBlob
df['sentiment'] = df['text'].apply(lambda x: TextBlob(x).sentiment.polarity)
df['subjectivity'] = df['text'].apply(lambda x: TextBlob(x).sentiment.subjectivity)

# TF-IDF features
from sklearn.feature_extraction.text import TfidfVectorizer
tfidf = TfidfVectorizer(max_features=100, stop_words='english')
tfidf_matrix = tfidf.fit_transform(df['text'])

# Count vectorization
from sklearn.feature_extraction.text import CountVectorizer
cv = CountVectorizer(max_features=100, stop_words='english')
count_matrix = cv.fit_transform(df['text'])

# N-grams
ngram_vectorizer = CountVectorizer(ngram_range=(2, 3), max_features=50)
ngram_matrix = ngram_vectorizer.fit_transform(df['text'])
```

**When to Use:**
- Text classification
- Sentiment analysis
- Product reviews, customer feedback
- Document categorization

### 9. Missing Value Features

**Purpose:** Extract information from missingness patterns

```python
# Missing indicator features
df['age_is_missing'] = df['age'].isna().astype(int)
df['income_is_missing'] = df['income'].isna().astype(int)

# Count of missing values per row
df['total_missing'] = df.isnull().sum(axis=1)

# Percentage of missing values per row
df['pct_missing'] = df.isnull().sum(axis=1) / df.shape[1]

# Missing value imputation with indicator
from sklearn.impute import SimpleImputer
imputer = SimpleImputer(strategy='mean', add_indicator=True)
imputed_data = imputer.fit_transform(df[['feature1', 'feature2']])
```

**When to Use:**
- Missingness is informative (MNAR)
- High percentage of missing values
- Missing patterns differ by target

### 10. Domain-Specific Features

**Financial Domain:**
```python
# Financial ratios
df['profit_margin'] = df['profit'] / (df['revenue'] + 1)
df['return_on_assets'] = df['net_income'] / (df['total_assets'] + 1)
df['current_ratio'] = df['current_assets'] / (df['current_liabilities'] + 1)
df['debt_to_equity'] = df['total_debt'] / (df['total_equity'] + 1)

# Price changes and returns
df['price_change'] = df['close_price'] - df['open_price']
df['price_change_pct'] = (df['close_price'] - df['open_price']) / df['open_price']
df['daily_return'] = df['close_price'].pct_change()
df['volatility'] = df['daily_return'].rolling(window=30).std()

# Technical indicators
df['sma_20'] = df['close_price'].rolling(window=20).mean()
df['ema_20'] = df['close_price'].ewm(span=20).mean()
df['price_to_sma_ratio'] = df['close_price'] / df['sma_20']
```

**E-commerce Domain:**
```python
# Customer metrics
df['avg_order_value'] = df['total_spend'] / (df['order_count'] + 1)
df['items_per_order'] = df['total_items'] / (df['order_count'] + 1)
df['discount_usage_rate'] = df['orders_with_discount'] / (df['order_count'] + 1)

# Recency, Frequency, Monetary (RFM)
df['recency'] = (pd.Timestamp.now() - df['last_purchase_date']).dt.days
df['frequency'] = df['purchase_count']
df['monetary'] = df['total_spend']

# Customer lifetime value proxy
df['clv_proxy'] = df['avg_order_value'] * df['purchase_count']
```

**Healthcare Domain:**
```python
# BMI and health metrics
df['bmi'] = df['weight_kg'] / (df['height_m'] ** 2)
df['is_overweight'] = (df['bmi'] >= 25).astype(int)
df['is_obese'] = (df['bmi'] >= 30).astype(int)

# Age-adjusted features
df['age_group'] = pd.cut(df['age'], bins=[0, 18, 40, 65, 100], labels=['Child', 'Adult', 'Middle', 'Senior'])
df['risk_score'] = df['age'] * df['bmi'] / 100
```

## Feature Selection Techniques

### Filter Methods (Fast, Independent of Model)

```python
# Variance threshold
from sklearn.feature_selection import VarianceThreshold
selector = VarianceThreshold(threshold=0.1)
X_filtered = selector.fit_transform(X)

# Correlation with target
correlation = df.corr()['target'].abs().sort_values(ascending=False)
top_features = correlation[correlation > 0.3].index.tolist()

# Mutual information
from sklearn.feature_selection import mutual_info_classif, mutual_info_regression
mi_scores = mutual_info_classif(X, y)
mi_scores = pd.Series(mi_scores, index=X.columns).sort_values(ascending=False)

# Chi-square test (for categorical features)
from sklearn.feature_selection import chi2, SelectKBest
selector = SelectKBest(chi2, k=10)
X_selected = selector.fit_transform(X, y)

# ANOVA F-test
from sklearn.feature_selection import f_classif
f_scores, p_values = f_classif(X, y)
```

### Wrapper Methods (Model-Based, More Expensive)

```python
# Recursive Feature Elimination (RFE)
from sklearn.feature_selection import RFE
from sklearn.ensemble import RandomForestClassifier

estimator = RandomForestClassifier()
selector = RFE(estimator, n_features_to_select=10, step=1)
selector.fit(X, y)
selected_features = X.columns[selector.support_]

# Sequential Feature Selection
from sklearn.feature_selection import SequentialFeatureSelector
sfs = SequentialFeatureSelector(estimator, n_features_to_select=10, direction='forward')
sfs.fit(X, y)
```

### Embedded Methods (During Model Training)

```python
# L1 Regularization (Lasso)
from sklearn.linear_model import LassoCV
lasso = LassoCV(cv=5)
lasso.fit(X, y)
important_features = X.columns[lasso.coef_ != 0]

# Tree-based feature importance
from sklearn.ensemble import RandomForestClassifier
rf = RandomForestClassifier()
rf.fit(X, y)
feature_importance = pd.Series(rf.feature_importances_, index=X.columns).sort_values(ascending=False)

# Permutation importance
from sklearn.inspection import permutation_importance
perm_importance = permutation_importance(rf, X, y, n_repeats=10)
```

## Feature Engineering Workflow

1. **Start with EDA:** Understand data distributions and relationships
2. **Create Domain Features:** Apply domain knowledge first
3. **Generate Transformations:** Apply mathematical transformations
4. **Build Interactions:** Create interaction and aggregation features
5. **Engineer Time Features:** Extract temporal patterns
6. **Handle Categories:** Encode categorical variables appropriately
7. **Select Features:** Use feature selection to reduce dimensionality
8. **Validate Impact:** Test feature importance and model performance
9. **Iterate:** Refine based on results

## Best Practices

1. **Avoid Data Leakage:**
   - Create features using only training data
   - Apply same transformations to test data
   - Never use future information

2. **Handle Missing Values:**
   - Impute before creating features when necessary
   - Create missing indicator features
   - Consider domain-specific imputation

3. **Feature Scaling:**
   - Scale after train/test split
   - Use same scaler parameters for test data
   - Choose scaler based on algorithm

4. **Document Everything:**
   - Track feature creation logic
   - Document domain assumptions
   - Version control feature engineering code

5. **Monitor Feature Importance:**
   - Regularly check which features contribute
   - Remove redundant or low-importance features
   - Investigate surprising feature importance

6. **Balance Complexity:**
   - Start simple, add complexity gradually
   - More features aren't always better
   - Consider curse of dimensionality

## Common Mistakes to Avoid

1. Creating features using information from the test set
2. Not handling missing values before feature engineering
3. Creating highly correlated features
4. Ignoring domain knowledge
5. Over-engineering features (too many interactions)
6. Not validating feature impact on model performance
7. Creating features that leak target information
8. Not documenting feature creation process
