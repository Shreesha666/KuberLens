"""
Probability Calibration Engine for KuberLens AI/ML.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Implements Platt Scaling (Sigmoid / Logistic Calibration) and Isotonic Regression.
Calibrators are fitted strictly on separated out-of-fold validation predictions
and evaluated using Brier Score, Expected Calibration Error (ECE), and Log-Loss.
"""
from __future__ import annotations

import logging
from typing import Any

import numpy as np
from sklearn.isotonic import IsotonicRegression
from sklearn.linear_model import LogisticRegression
from sklearn.metrics import brier_score_loss

logger = logging.getLogger(__name__)


def compute_expected_calibration_error(
    y_true: np.ndarray,
    y_prob: np.ndarray,
    n_bins: int = 10,
) -> float:
    """
    Computes Expected Calibration Error (ECE) across uniform confidence bins.
    """
    bins = np.linspace(0.0, 1.0, n_bins + 1)
    bin_indices = np.digitize(y_prob, bins) - 1
    bin_indices = np.clip(bin_indices, 0, n_bins - 1)

    ece = 0.0
    n = len(y_true)
    if n == 0:
        return 0.0

    for b in range(n_bins):
        mask = bin_indices == b
        bin_count = np.sum(mask)
        if bin_count > 0:
            bin_acc = np.mean(y_true[mask])
            bin_conf = np.mean(y_prob[mask])
            ece += (bin_count / n) * abs(bin_acc - bin_conf)

    return float(ece)


class ProbabilityCalibrator:
    """
    Wraps probability calibration methods:
      - 'platt' or 'sigmoid': Logistic regression on raw log-odds/probabilities.
      - 'isotonic': Non-parametric isotonic regression with isotonic monotonicity.
    Selects the optimal calibration method based on minimum validation Brier score.
    """

    def __init__(self, method: str = "auto") -> None:
        """
        method: 'auto', 'platt', 'isotonic', or 'none'.
        'auto' fits both Platt and Isotonic, picking the one with lowest validation Brier score.
        """
        self.method = method.lower()
        self.selected_method_: str = "none"
        self.platt_model_: LogisticRegression | None = None
        self.isotonic_model_: IsotonicRegression | None = None
        self.uncalibrated_brier_: float = 0.0
        self.calibrated_brier_: float = 0.0
        self.brier_skill_score_: float = 0.0
        self.uncalibrated_ece_: float = 0.0
        self.calibrated_ece_: float = 0.0

    def fit(self, y_val_prob: np.ndarray, y_val_true: np.ndarray) -> ProbabilityCalibrator:
        """
        Fits calibration models on out-of-fold validation predicted probabilities (class 1)
        and true binary labels.
        """
        y_prob = np.asarray(y_val_prob, dtype=float).clip(1e-6, 1.0 - 1e-6)
        y_true = np.asarray(y_val_true, dtype=int)

        self.uncalibrated_brier_ = float(brier_score_loss(y_true, y_prob))
        self.uncalibrated_ece_ = compute_expected_calibration_error(y_true, y_prob)

        # Baseline naive prevalence prior Brier score for Brier Skill Score
        prior_p = float(np.mean(y_true)) if len(y_true) > 0 else 0.5
        brier_ref = float(np.mean((prior_p - y_true) ** 2)) if len(y_true) > 0 else 0.25

        # 1. Fit Platt (Logistic)
        logits = np.log(y_prob / (1.0 - y_prob)).reshape(-1, 1)
        platt = LogisticRegression(C=1.0, solver="lbfgs")
        platt.fit(logits, y_true)
        platt_probs = platt.predict_proba(logits)[:, 1]
        platt_brier = float(brier_score_loss(y_true, platt_probs))

        # 2. Fit Isotonic
        iso = IsotonicRegression(out_of_bounds="clip", y_min=0.001, y_max=0.999)
        iso.fit(y_prob, y_true)
        iso_probs = iso.predict(y_prob)
        iso_brier = float(brier_score_loss(y_true, iso_probs))

        # Select method
        if self.method == "platt" or self.method == "sigmoid":
            self.selected_method_ = "platt"
            self.platt_model_ = platt
            self.calibrated_brier_ = platt_brier
            self.calibrated_ece_ = compute_expected_calibration_error(y_true, platt_probs)
        elif self.method == "isotonic":
            self.selected_method_ = "isotonic"
            self.isotonic_model_ = iso
            self.calibrated_brier_ = iso_brier
            self.calibrated_ece_ = compute_expected_calibration_error(y_true, iso_probs)
        elif self.method == "none":
            self.selected_method_ = "none"
            self.calibrated_brier_ = self.uncalibrated_brier_
            self.calibrated_ece_ = self.uncalibrated_ece_
        else:  # 'auto'
            # Pick best between uncalibrated, platt, isotonic
            candidates = [
                ("none", self.uncalibrated_brier_, self.uncalibrated_ece_),
                ("platt", platt_brier, compute_expected_calibration_error(y_true, platt_probs)),
                ("isotonic", iso_brier, compute_expected_calibration_error(y_true, iso_probs)),
            ]
            candidates.sort(key=lambda x: x[1])
            best_method, best_brier, best_ece = candidates[0]
            self.selected_method_ = best_method
            self.platt_model_ = platt
            self.isotonic_model_ = iso
            self.calibrated_brier_ = best_brier
            self.calibrated_ece_ = best_ece

        # Brier Skill Score: 1 - (Brier_model / Brier_ref)
        if brier_ref > 0:
            self.brier_skill_score_ = float(1.0 - (self.calibrated_brier_ / brier_ref))
        else:
            self.brier_skill_score_ = 0.0

        return self

    def calibrate(self, raw_prob_1: np.ndarray) -> np.ndarray:
        """
        Transforms uncalibrated raw probability array for class 1 into calibrated probabilities.
        """
        p = np.asarray(raw_prob_1, dtype=float).clip(1e-6, 1.0 - 1e-6)
        if self.selected_method_ == "platt" and self.platt_model_ is not None:
            logits = np.log(p / (1.0 - p)).reshape(-1, 1)
            return self.platt_model_.predict_proba(logits)[:, 1]
        elif self.selected_method_ == "isotonic" and self.isotonic_model_ is not None:
            return self.isotonic_model_.predict(p)
        return p

    def get_summary(self) -> dict[str, Any]:
        return {
            "selected_method": self.selected_method_,
            "uncalibrated_brier": round(self.uncalibrated_brier_, 4),
            "calibrated_brier": round(self.calibrated_brier_, 4),
            "brier_skill_score": round(self.brier_skill_score_, 4),
            "uncalibrated_ece": round(self.uncalibrated_ece_, 4),
            "calibrated_ece": round(self.calibrated_ece_, 4),
        }
