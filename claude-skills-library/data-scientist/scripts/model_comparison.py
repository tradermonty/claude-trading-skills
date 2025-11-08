#!/usr/bin/env python3
"""
Model Comparison Script

Compares multiple machine learning models on a given dataset:
- Trains multiple models with default and tuned parameters
- Evaluates using appropriate metrics
- Generates comparison visualizations
- Provides recommendations based on results

Usage:
    python model_comparison.py <data_file> <target_col> [--problem-type TYPE] [--output OUTPUT_DIR]

Example:
    python model_comparison.py data.csv price --problem-type regression
    python model_comparison.py data.csv churn --problem-type classification --output results/
"""

import argparse
import os
import sys
import warnings
from pathlib import Path
from time import time
warnings.filterwarnings('ignore')

import pandas as pd
import numpy as np
import matplotlib.pyplot as plt
import seaborn as sns

from sklearn.model_selection import train_test_split, cross_val_score, GridSearchCV
from sklearn.preprocessing import StandardScaler, LabelEncoder
from sklearn.impute import SimpleImputer
from sklearn.metrics import (
    mean_squared_error, mean_absolute_error, r2_score,
    accuracy_score, precision_score, recall_score, f1_score,
    roc_auc_score, confusion_matrix, classification_report
)

# Regression models
from sklearn.linear_model import LinearRegression, Ridge, Lasso, ElasticNet
from sklearn.tree import DecisionTreeRegressor
from sklearn.ensemble import RandomForestRegressor, GradientBoostingRegressor
from sklearn.svm import SVR
from sklearn.neighbors import KNeighborsRegressor

# Classification models
from sklearn.linear_model import LogisticRegression
from sklearn.tree import DecisionTreeClassifier
from sklearn.ensemble import RandomForestClassifier, GradientBoostingClassifier
from sklearn.svm import SVC
from sklearn.neighbors import KNeighborsClassifier
from sklearn.naive_bayes import GaussianNB

# Set style
sns.set_style('whitegrid')
sns.set_context('notebook', font_scale=1.1)


class ModelComparison:
    """Compare multiple ML models"""

    def __init__(self, data_path, target_col, problem_type=None, output_dir='model_comparison'):
        """
        Initialize ModelComparison

        Args:
            data_path: Path to data file
            target_col: Name of target column
            problem_type: 'regression' or 'classification' (auto-detected if None)
            output_dir: Directory to save outputs
        """
        self.data_path = data_path
        self.target_col = target_col
        self.output_dir = Path(output_dir)
        self.output_dir.mkdir(parents=True, exist_ok=True)

        # Load data
        self.df = self._load_data()

        # Detect or set problem type
        if problem_type:
            self.problem_type = problem_type.lower()
        else:
            self.problem_type = self._detect_problem_type()

        print(f"\nProblem Type: {self.problem_type.upper()}")

        # Prepare data
        self.X_train, self.X_test, self.y_train, self.y_test = self._prepare_data()

        # Results storage
        self.results = []
        self.trained_models = {}

    def _load_data(self):
        """Load data from file"""
        file_ext = Path(self.data_path).suffix.lower()

        if file_ext == '.csv':
            return pd.read_csv(self.data_path)
        elif file_ext in ['.xlsx', '.xls']:
            return pd.read_excel(self.data_path)
        elif file_ext == '.parquet':
            return pd.read_parquet(self.data_path)
        else:
            raise ValueError(f"Unsupported file format: {file_ext}")

    def _detect_problem_type(self):
        """Auto-detect problem type"""
        target = self.df[self.target_col]

        if pd.api.types.is_numeric_dtype(target):
            n_unique = target.nunique()
            if n_unique > 20:  # Arbitrary threshold
                return 'regression'
            else:
                return 'classification'
        else:
            return 'classification'

    def _prepare_data(self):
        """Prepare data for modeling"""
        print("\nPreparing data...")

        # Separate features and target
        X = self.df.drop(columns=[self.target_col])
        y = self.df[self.target_col]

        # Handle categorical features
        cat_cols = X.select_dtypes(include=['object', 'category']).columns
        if len(cat_cols) > 0:
            print(f"  Encoding {len(cat_cols)} categorical features...")
            for col in cat_cols:
                le = LabelEncoder()
                X[col] = le.fit_transform(X[col].astype(str))

        # Handle missing values
        if X.isnull().any().any():
            print("  Imputing missing values...")
            imputer = SimpleImputer(strategy='median')
            X = pd.DataFrame(imputer.fit_transform(X), columns=X.columns)

        # Encode target if classification
        if self.problem_type == 'classification' and not pd.api.types.is_numeric_dtype(y):
            print("  Encoding target variable...")
            le = LabelEncoder()
            y = le.fit_transform(y)
            self.target_encoder = le
        else:
            self.target_encoder = None

        # Train-test split
        X_train, X_test, y_train, y_test = train_test_split(
            X, y, test_size=0.2, random_state=42, stratify=y if self.problem_type == 'classification' else None
        )

        # Scale features
        print("  Scaling features...")
        scaler = StandardScaler()
        X_train_scaled = scaler.fit_transform(X_train)
        X_test_scaled = scaler.transform(X_test)

        # Convert back to DataFrame
        X_train = pd.DataFrame(X_train_scaled, columns=X.columns)
        X_test = pd.DataFrame(X_test_scaled, columns=X.columns)

        print(f"  Training set: {X_train.shape}")
        print(f"  Test set: {X_test.shape}")

        return X_train, X_test, y_train, y_test

    def _get_models(self):
        """Get models to compare"""
        if self.problem_type == 'regression':
            return {
                'Linear Regression': LinearRegression(),
                'Ridge': Ridge(random_state=42),
                'Lasso': Lasso(random_state=42),
                'ElasticNet': ElasticNet(random_state=42),
                'Decision Tree': DecisionTreeRegressor(random_state=42),
                'Random Forest': RandomForestRegressor(random_state=42, n_jobs=-1),
                'Gradient Boosting': GradientBoostingRegressor(random_state=42),
                'SVR': SVR(),
                'KNN': KNeighborsRegressor()
            }
        else:
            return {
                'Logistic Regression': LogisticRegression(random_state=42, max_iter=1000),
                'Decision Tree': DecisionTreeClassifier(random_state=42),
                'Random Forest': RandomForestClassifier(random_state=42, n_jobs=-1),
                'Gradient Boosting': GradientBoostingClassifier(random_state=42),
                'SVM': SVC(random_state=42, probability=True),
                'KNN': KNeighborsClassifier(),
                'Naive Bayes': GaussianNB()
            }

    def train_models(self, cv=5):
        """Train and evaluate all models"""
        print(f"\nTraining models with {cv}-fold cross-validation...\n")

        models = self._get_models()

        for name, model in models.items():
            print(f"Training {name}...")
            start_time = time()

            # Cross-validation
            if self.problem_type == 'regression':
                cv_scores = cross_val_score(model, self.X_train, self.y_train,
                                           cv=cv, scoring='neg_mean_squared_error', n_jobs=-1)
                cv_rmse = np.sqrt(-cv_scores.mean())
            else:
                cv_scores = cross_val_score(model, self.X_train, self.y_train,
                                           cv=cv, scoring='f1_weighted', n_jobs=-1)
                cv_score = cv_scores.mean()

            # Train on full training set
            model.fit(self.X_train, self.y_train)

            # Predict
            y_pred = model.predict(self.X_test)
            if self.problem_type == 'classification' and hasattr(model, 'predict_proba'):
                y_pred_proba = model.predict_proba(self.X_test)
            else:
                y_pred_proba = None

            # Calculate metrics
            train_time = time() - start_time

            if self.problem_type == 'regression':
                metrics = {
                    'Model': name,
                    'CV_RMSE': cv_rmse,
                    'Test_RMSE': np.sqrt(mean_squared_error(self.y_test, y_pred)),
                    'Test_MAE': mean_absolute_error(self.y_test, y_pred),
                    'Test_R2': r2_score(self.y_test, y_pred),
                    'Train_Time': train_time
                }
                print(f"  CV RMSE: {cv_rmse:.4f} | Test RMSE: {metrics['Test_RMSE']:.4f} | "
                      f"R²: {metrics['Test_R2']:.4f} | Time: {train_time:.2f}s")
            else:
                metrics = {
                    'Model': name,
                    'CV_F1': cv_score,
                    'Test_Accuracy': accuracy_score(self.y_test, y_pred),
                    'Test_Precision': precision_score(self.y_test, y_pred, average='weighted', zero_division=0),
                    'Test_Recall': recall_score(self.y_test, y_pred, average='weighted', zero_division=0),
                    'Test_F1': f1_score(self.y_test, y_pred, average='weighted', zero_division=0),
                    'Train_Time': train_time
                }

                # Add ROC-AUC for binary classification
                if len(np.unique(self.y_train)) == 2 and y_pred_proba is not None:
                    metrics['Test_ROC_AUC'] = roc_auc_score(self.y_test, y_pred_proba[:, 1])
                    print(f"  CV F1: {cv_score:.4f} | Test Acc: {metrics['Test_Accuracy']:.4f} | "
                          f"F1: {metrics['Test_F1']:.4f} | AUC: {metrics['Test_ROC_AUC']:.4f} | "
                          f"Time: {train_time:.2f}s")
                else:
                    print(f"  CV F1: {cv_score:.4f} | Test Acc: {metrics['Test_Accuracy']:.4f} | "
                          f"F1: {metrics['Test_F1']:.4f} | Time: {train_time:.2f}s")

            self.results.append(metrics)
            self.trained_models[name] = (model, y_pred, y_pred_proba)

        print("\nAll models trained!")

    def generate_comparison_report(self):
        """Generate comparison visualizations and report"""
        print("\nGenerating comparison report...")

        results_df = pd.DataFrame(self.results)

        if self.problem_type == 'regression':
            # Sort by test RMSE
            results_df = results_df.sort_values('Test_RMSE')

            # Save results table
            results_df.to_csv(self.output_dir / 'model_results.csv', index=False)

            # Visualizations
            fig, axes = plt.subplots(2, 2, figsize=(16, 12))

            # RMSE comparison
            axes[0, 0].barh(results_df['Model'], results_df['Test_RMSE'])
            axes[0, 0].set_xlabel('Test RMSE (Lower is Better)')
            axes[0, 0].set_title('Model Comparison - RMSE')
            axes[0, 0].invert_yaxis()

            # R² comparison
            axes[0, 1].barh(results_df['Model'], results_df['Test_R2'],
                          color=['green' if x > 0 else 'red' for x in results_df['Test_R2']])
            axes[0, 1].set_xlabel('Test R² (Higher is Better)')
            axes[0, 1].set_title('Model Comparison - R²')
            axes[0, 1].invert_yaxis()
            axes[0, 1].axvline(x=0, color='black', linestyle='--', linewidth=1)

            # MAE comparison
            axes[1, 0].barh(results_df['Model'], results_df['Test_MAE'])
            axes[1, 0].set_xlabel('Test MAE (Lower is Better)')
            axes[1, 0].set_title('Model Comparison - MAE')
            axes[1, 0].invert_yaxis()

            # Training time comparison
            axes[1, 1].barh(results_df['Model'], results_df['Train_Time'])
            axes[1, 1].set_xlabel('Training Time (seconds)')
            axes[1, 1].set_title('Model Training Time')
            axes[1, 1].invert_yaxis()

            plt.tight_layout()
            plt.savefig(self.output_dir / 'model_comparison.png', dpi=300, bbox_inches='tight')
            plt.close()

            # Best model summary
            best_model_name = results_df.iloc[0]['Model']
            print(f"\n{'='*80}")
            print(f"BEST MODEL (by Test RMSE): {best_model_name}")
            print(f"{'='*80}")
            print(results_df.iloc[0].to_string())

        else:
            # Sort by test F1
            results_df = results_df.sort_values('Test_F1', ascending=False)

            # Save results table
            results_df.to_csv(self.output_dir / 'model_results.csv', index=False)

            # Visualizations
            n_plots = 4 if 'Test_ROC_AUC' in results_df.columns else 3
            fig, axes = plt.subplots(2, 2, figsize=(16, 12))
            axes = axes.flatten()

            # F1 comparison
            axes[0].barh(results_df['Model'], results_df['Test_F1'])
            axes[0].set_xlabel('Test F1 Score (Higher is Better)')
            axes[0].set_title('Model Comparison - F1 Score')
            axes[0].invert_yaxis()

            # Accuracy comparison
            axes[1].barh(results_df['Model'], results_df['Test_Accuracy'])
            axes[1].set_xlabel('Test Accuracy (Higher is Better)')
            axes[1].set_title('Model Comparison - Accuracy')
            axes[1].invert_yaxis()

            # Precision vs Recall
            axes[2].scatter(results_df['Test_Recall'], results_df['Test_Precision'], s=100)
            for idx, row in results_df.iterrows():
                axes[2].annotate(row['Model'], (row['Test_Recall'], row['Test_Precision']),
                               fontsize=8, alpha=0.7)
            axes[2].set_xlabel('Recall')
            axes[2].set_ylabel('Precision')
            axes[2].set_title('Precision vs Recall Trade-off')
            axes[2].grid(alpha=0.3)

            # ROC-AUC or Training time
            if 'Test_ROC_AUC' in results_df.columns:
                axes[3].barh(results_df['Model'], results_df['Test_ROC_AUC'])
                axes[3].set_xlabel('Test ROC-AUC (Higher is Better)')
                axes[3].set_title('Model Comparison - ROC-AUC')
                axes[3].invert_yaxis()
            else:
                axes[3].barh(results_df['Model'], results_df['Train_Time'])
                axes[3].set_xlabel('Training Time (seconds)')
                axes[3].set_title('Model Training Time')
                axes[3].invert_yaxis()

            plt.tight_layout()
            plt.savefig(self.output_dir / 'model_comparison.png', dpi=300, bbox_inches='tight')
            plt.close()

            # Confusion matrix for best model
            best_model_name = results_df.iloc[0]['Model']
            _, y_pred, _ = self.trained_models[best_model_name]

            cm = confusion_matrix(self.y_test, y_pred)
            plt.figure(figsize=(8, 6))
            sns.heatmap(cm, annot=True, fmt='d', cmap='Blues')
            plt.xlabel('Predicted')
            plt.ylabel('Actual')
            plt.title(f'Confusion Matrix - {best_model_name}')
            plt.tight_layout()
            plt.savefig(self.output_dir / f'confusion_matrix_{best_model_name.replace(" ", "_")}.png',
                       dpi=300, bbox_inches='tight')
            plt.close()

            # Classification report
            report = classification_report(self.y_test, y_pred)
            with open(self.output_dir / f'classification_report_{best_model_name.replace(" ", "_")}.txt', 'w') as f:
                f.write(f"Classification Report - {best_model_name}\n")
                f.write("="*80 + "\n\n")
                f.write(report)

            # Best model summary
            print(f"\n{'='*80}")
            print(f"BEST MODEL (by Test F1): {best_model_name}")
            print(f"{'='*80}")
            print(results_df.iloc[0].to_string())
            print(f"\nClassification Report:")
            print(report)

        # Save detailed results
        with open(self.output_dir / 'model_comparison_summary.txt', 'w') as f:
            f.write(f"Model Comparison Report\n")
            f.write(f"{'='*80}\n\n")
            f.write(f"Problem Type: {self.problem_type.upper()}\n")
            f.write(f"Target Variable: {self.target_col}\n")
            f.write(f"Training Samples: {len(self.y_train)}\n")
            f.write(f"Test Samples: {len(self.y_test)}\n\n")
            f.write(f"{'='*80}\n\n")
            f.write(results_df.to_string(index=False))

        print(f"\nResults saved to: {self.output_dir}")


def main():
    parser = argparse.ArgumentParser(
        description='Model Comparison Tool',
        formatter_class=argparse.RawDescriptionHelpFormatter,
        epilog="""
Examples:
  python model_comparison.py data.csv price --problem-type regression
  python model_comparison.py data.csv is_fraud --problem-type classification
  python model_comparison.py sales.xlsx revenue --output my_results/
        """
    )

    parser.add_argument('data_file', help='Path to data file (CSV, Excel, etc.)')
    parser.add_argument('target', help='Target column name')
    parser.add_argument('--problem-type', '-p', choices=['regression', 'classification'],
                       help='Problem type (auto-detected if not specified)')
    parser.add_argument('--output', '-o', default='model_comparison',
                       help='Output directory')
    parser.add_argument('--cv', type=int, default=5,
                       help='Number of cross-validation folds (default: 5)')

    args = parser.parse_args()

    # Validate input file
    if not os.path.exists(args.data_file):
        print(f"Error: File not found: {args.data_file}")
        sys.exit(1)

    # Run comparison
    print(f"\nModel Comparison Tool")
    print(f"{'='*80}")
    print(f"Data: {args.data_file}")
    print(f"Target: {args.target}")
    print(f"Output: {args.output}")

    comparison = ModelComparison(args.data_file, args.target,
                                problem_type=args.problem_type,
                                output_dir=args.output)
    comparison.train_models(cv=args.cv)
    comparison.generate_comparison_report()

    print(f"\n{'='*80}")
    print("Model comparison complete!")
    print(f"{'='*80}\n")


if __name__ == '__main__':
    main()
