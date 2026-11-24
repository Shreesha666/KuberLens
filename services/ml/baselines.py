"""
Baseline Classification Models for KuberLens AI/ML.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Implements benchmark baselines against which LightGBM models are evaluated:
1. MajorityClassBaseline:
   Always predicts the training fold majority class prior (prevalence probability).
2. MomentumBaseline:
   Predicts positive forward direction if historical 20-session return (return_20d) > 0.
"""
from __future__ import annotations

import numpy as np
import pandas as pd


class MajorityClassBaseline:
    """
    Majority class baseline model.
    Learns training label prevalence prior P(y=1) and predicts constant probability.
    """

    def __init__(self) -> None:
        self.prior_p_: float = 0.5
        self.majority_class_: int = 0

    def fit(self, X: pd.DataFrame | np.ndarray, y: pd.Series | np.ndarray) -> MajorityClassBaseline:
        y_arr = np.asarray(y)
        if len(y_arr) == 0:
            self.prior_p_ = 0.5
            self.majority_class_ = 0
            return self
        self.prior_p_ = float(np.mean(y_arr))
        self.majority_class_ = int(self.prior_p_ >= 0.5)
        return self

    def predict_proba(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        n = len(X)
        p1 = np.full(n, self.prior_p_)
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])

    def predict(self, X: pd.DataFrame | np.ndarray) -> np.ndarray:
        n = len(X)
        return np.full(n, self.majority_class_, dtype=int)


class MomentumBaseline:
    """
    Rule-based technical momentum baseline.
    Predicts positive forward direction if historical 20-session return > 0.
    Outputs heuristic probability based on standardized return magnitude.
    """

    def __init__(self, momentum_col: str = "return_20d") -> None:
        self.momentum_col = momentum_col
        self.mean_mom_: float = 0.0
        self.std_mom_: float = 1.0

    def fit(self, X: pd.DataFrame, y: pd.Series | np.ndarray | None = None) -> MomentumBaseline:
        if isinstance(X, pd.DataFrame) and self.momentum_col in X.columns:
            mom = X[self.momentum_col].dropna()
            if len(mom) > 0:
                self.mean_mom_ = float(mom.mean())
                self.std_mom_ = float(mom.std()) if mom.std() > 0 else 1.0
        return self

    def predict_proba(self, X: pd.DataFrame) -> np.ndarray:
        if isinstance(X, pd.DataFrame) and self.momentum_col in X.columns:
            mom = X[self.momentum_col].fillna(0.0).values
        elif isinstance(X, np.ndarray):
            # Assume first column or zero if passed as array
            mom = X[:, 0] if X.ndim > 1 and X.shape[1] > 0 else np.zeros(len(X))
        else:
            mom = np.zeros(len(X))

        # Sigmoid transform around zero momentum
        z = (mom - self.mean_mom_) / (self.std_mom_ if self.std_mom_ > 0 else 1.0)
        p1 = 1.0 / (1.0 + np.exp(-z))
        p0 = 1.0 - p1
        return np.column_stack([p0, p1])

    def predict(self, X: pd.DataFrame) -> np.ndarray:
        if isinstance(X, pd.DataFrame) and self.momentum_col in X.columns:
            mom = X[self.momentum_col].fillna(0.0).values
        elif isinstance(X, np.ndarray):
            mom = X[:, 0] if X.ndim > 1 and X.shape[1] > 0 else np.zeros(len(X))
        else:
            mom = np.zeros(len(X))
        return (mom > 0).astype(int)
