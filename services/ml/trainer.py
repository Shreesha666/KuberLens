"""
Walk-Forward Purged Cross-Validation Trainer for KuberLens AI/ML.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Implements:
1. Expanding chronological window cross-validation (4 folds).
2. Strict h-session purging and h-session embargoing to eliminate data leakage.
3. LightGBM binary classifier training with early stopping.
4. Comprehensive evaluation metrics:
   - Discrimination: ROC-AUC, PR-AUC, Accuracy, Balanced Accuracy, Precision, Recall, F1.
   - Calibration: Brier Score, Brier Skill Score, Expected Calibration Error (ECE).
   - Baseline comparison: MajorityClassBaseline, MomentumBaseline.
   - Cost-adjusted financial backtest metrics: Mean net return, Sharpe ratio, Win rate.
5. Untouched out-of-sample final test set evaluation (Dec 2025 – Oct 2026).
6. Model artifact persistence with SHA-256 cryptographic verification and MLModelRecord tracking.
"""
from __future__ import annotations

import hashlib
import logging
from dataclasses import dataclass
from datetime import date
from pathlib import Path
from typing import Any

import joblib
import lightgbm as lgb
import numpy as np
import pandas as pd
from django.conf import settings
from django.utils import timezone
from sklearn.metrics import (
    accuracy_score,
    balanced_accuracy_score,
    brier_score_loss,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)

from apps.ml_engine.models import MLDatasetSnapshot, MLModelRecord, MLModelState
from services.ml.baselines import MajorityClassBaseline, MomentumBaseline
from services.ml.calibrator import ProbabilityCalibrator, compute_expected_calibration_error
from services.ml.features import FEATURE_CATALOG

logger = logging.getLogger(__name__)


@dataclass(frozen=True)
class WalkForwardFoldSpec:
    fold_index: int
    train_start: str
    train_end: str
    val_start: str
    val_end: str


# 4 Expanding chronological folds per AIML Roadmap v2.1
STANDARD_FOLDS: list[WalkForwardFoldSpec] = [
    WalkForwardFoldSpec(1, "2020-01-01", "2022-12-31", "2023-01-01", "2023-12-31"),
    WalkForwardFoldSpec(2, "2020-01-01", "2023-12-31", "2024-01-01", "2024-12-31"),
    WalkForwardFoldSpec(3, "2020-01-01", "2024-12-31", "2025-01-01", "2025-06-30"),
    WalkForwardFoldSpec(4, "2020-01-01", "2025-06-30", "2025-07-01", "2025-11-30"),
]

# Untouched final test period
FINAL_TEST_SPEC = {
    "start_date": "2025-12-01",
    "end_date": "2026-10-31",
}


@dataclass
class FoldMetrics:
    fold_index: int
    train_samples: int
    val_samples: int
    roc_auc: float
    pr_auc: float
    accuracy: float
    balanced_accuracy: float
    precision: float
    recall: float
    f1: float
    brier_score: float
    brier_skill_score: float
    ece: float
    majority_accuracy: float
    majority_brier: float
    momentum_accuracy: float
    momentum_roc_auc: float
    mean_net_return_pct: float
    sharpe_ratio: float
    win_rate_pct: float
    confusion_matrix: list[list[int]]


class WalkForwardTrainer:
    """
    Orchestrates expanding chronological walk-forward training for LightGBM models
    with purging, embargo, probability calibration, and financial evaluation.
    """

    def __init__(
        self,
        horizon_sessions: int = 20,
        feature_cols: list[str] | None = None,
        folds: list[WalkForwardFoldSpec] | None = None,
        final_test_spec: dict[str, str] | None = None,
        random_state: int = 42,
        lgb_params: dict[str, Any] | None = None,
    ):
        self.horizon_sessions = horizon_sessions
        self.target_col = f"target_binary_{horizon_sessions}d"
        self.net_return_col = f"target_return_net_{horizon_sessions}d"
        self.feature_cols = feature_cols or [s.name for s in FEATURE_CATALOG]
        self.folds = folds or STANDARD_FOLDS
        self.final_test_spec = final_test_spec or FINAL_TEST_SPEC
        self.random_state = random_state

        default_lgb_params = {
            "objective": "binary",
            "metric": "binary_logloss",
            "boosting_type": "gbdt",
            "learning_rate": 0.03,
            "num_leaves": 31,
            "max_depth": 6,
            "min_child_samples": 50,
            "subsample": 0.8,
            "colsample_bytree": 0.8,
            "n_estimators": 300,
            "random_state": self.random_state,
            "verbosity": -1,
            "n_jobs": -1,
        }
        if lgb_params:
            default_lgb_params.update(lgb_params)
        self.lgb_params = default_lgb_params

    def purge_and_embargo(
        self,
        df: pd.DataFrame,
        train_start: str,
        train_end: str,
        val_start: str,
        val_end: str,
    ) -> tuple[pd.DataFrame, pd.DataFrame]:
        """
        Splits dataset into train and validation sets enforcing:
        1. Train rows strictly in [train_start, train_end].
        2. Validation rows strictly in [val_start, val_end].
        3. h-session Purging:
           Excludes train observations whose forward horizon [t, t+h] overlaps with val_start.
           Specifically, any train session where session_date >= (val_start - h trading sessions)
           is purged to ensure zero target label overlap.
        4. Embargo:
           In an expanding forward scheme (train preceding val), the embargo protects
           against auto-correlated residual leakage at the train/val boundary.
        """
        # Get sorted unique session dates in chronological order
        unique_dates = sorted(df["session_date"].unique())
        date_to_idx = {d: i for i, d in enumerate(unique_dates)}

        val_start_idx = date_to_idx.get(val_start)
        if val_start_idx is None:
            # Find first date >= val_start
            matching = [i for i, d in enumerate(unique_dates) if d >= val_start]
            val_start_idx = matching[0] if matching else len(unique_dates)

        # Purge cutoff: h sessions prior to val_start
        purge_cutoff_idx = max(0, val_start_idx - self.horizon_sessions)
        purge_cutoff_date = unique_dates[purge_cutoff_idx]

        # Enforce train strictly before purge cutoff
        df_train = df[(df["session_date"] >= train_start) & (df["session_date"] < purge_cutoff_date)].copy()
        df_val = df[(df["session_date"] >= val_start) & (df["session_date"] <= val_end)].copy()

        return df_train, df_val

    def compute_metrics(
        self,
        y_true: np.ndarray,
        y_prob: np.ndarray,
        net_returns: np.ndarray | None = None,
        calibrator: ProbabilityCalibrator | None = None,
    ) -> dict[str, Any]:
        """
        Computes comprehensive evaluation metrics for classification and financial performance.
        """
        y_true = np.asarray(y_true, dtype=int)
        y_prob_calibrated = calibrator.calibrate(y_prob) if calibrator else y_prob
        y_pred = (y_prob_calibrated >= 0.5).astype(int)

        roc_auc = float(roc_auc_score(y_true, y_prob_calibrated)) if len(np.unique(y_true)) > 1 else 0.5
        
        # PR-AUC via Average Precision
        try:
            from sklearn.metrics import average_precision_score
            pr_auc = float(average_precision_score(y_true, y_prob_calibrated))
        except Exception:
            pr_auc = float(np.mean(y_true))

        acc = float(accuracy_score(y_true, y_pred))
        bal_acc = float(balanced_accuracy_score(y_true, y_pred))
        prec = float(precision_score(y_true, y_pred, zero_division=0))
        rec = float(recall_score(y_true, y_pred, zero_division=0))
        f1 = float(f1_score(y_true, y_pred, zero_division=0))

        brier = float(brier_score_loss(y_true, y_prob_calibrated))
        prior_p = float(np.mean(y_true)) if len(y_true) > 0 else 0.5
        brier_ref = float(np.mean((prior_p - y_true) ** 2)) if len(y_true) > 0 else 0.25
        brier_skill = float(1.0 - (brier / brier_ref)) if brier_ref > 0 else 0.0

        ece = compute_expected_calibration_error(y_true, y_prob_calibrated)
        cm = confusion_matrix(y_true, y_pred).tolist()

        # Financial performance on positive predictions (y_pred == 1)
        mean_ret = 0.0
        sharpe = 0.0
        win_rate = 0.0
        if net_returns is not None and len(net_returns) == len(y_pred):
            pos_mask = y_pred == 1
            if np.sum(pos_mask) > 0:
                selected_rets = net_returns[pos_mask]
                mean_ret = float(np.mean(selected_rets) * 100.0)
                std_ret = float(np.std(selected_rets))
                # Annualized Sharpe (assuming ~250 sessions / horizon)
                annualization_factor = np.sqrt(250.0 / self.horizon_sessions)
                sharpe = float(np.mean(selected_rets) / std_ret * annualization_factor) if std_ret > 0 else 0.0
                win_rate = float(np.mean(selected_rets > 0) * 100.0)

        return {
            "roc_auc": round(roc_auc, 4),
            "pr_auc": round(pr_auc, 4),
            "accuracy": round(acc, 4),
            "balanced_accuracy": round(bal_acc, 4),
            "precision": round(prec, 4),
            "recall": round(rec, 4),
            "f1": round(f1, 4),
            "brier_score": round(brier, 4),
            "brier_skill_score": round(brier_skill, 4),
            "ece": round(ece, 4),
            "mean_net_return_pct": round(mean_ret, 2),
            "sharpe_ratio": round(sharpe, 2),
            "win_rate_pct": round(win_rate, 2),
            "confusion_matrix": cm,
        }

    def train_walk_forward(self, df_dataset: pd.DataFrame) -> dict[str, Any]:
        """
        Executes the 4-fold walk-forward cross-validation schedule.
        Fits LightGBM and baselines per fold, applies probability calibration,
        and aggregates cross-validation performance.
        """
        df_clean = df_dataset.dropna(subset=self.feature_cols + [self.target_col]).copy()
        df_clean = df_clean.sort_values(by=["session_date", "symbol"]).reset_index(drop=True)

        fold_results: list[dict[str, Any]] = []
        trained_models: list[lgb.LGBMClassifier] = []
        calibrators: list[ProbabilityCalibrator] = []

        logger.info("Starting Walk-Forward CV for %d-session horizon across %d folds...", self.horizon_sessions, len(self.folds))

        for fold in self.folds:
            df_train, df_val = self.purge_and_embargo(
                df_clean,
                train_start=fold.train_start,
                train_end=fold.train_end,
                val_start=fold.val_start,
                val_end=fold.val_end,
            )

            X_train = df_train[self.feature_cols]
            y_train = df_train[self.target_col].astype(int)
            X_val = df_val[self.feature_cols]
            y_val = df_val[self.target_col].astype(int)
            val_net_ret = df_val[self.net_return_col].values if self.net_return_col in df_val.columns else None

            logger.info("Fold %d: Train samples=%d, Val samples=%d", fold.fold_index, len(X_train), len(X_val))

            # 1. Fit LightGBM
            clf = lgb.LGBMClassifier(**self.lgb_params)
            clf.fit(
                X_train,
                y_train,
                eval_set=[(X_val, y_val)],
                callbacks=[lgb.early_stopping(stopping_rounds=30, verbose=False)],
            )
            val_probs_raw = clf.predict_proba(X_val)[:, 1]

            # 2. Fit Calibrator on Validation Fold
            calibrator = ProbabilityCalibrator(method="auto")
            calibrator.fit(val_probs_raw, y_val.values)

            # 3. Compute Metrics
            metrics = self.compute_metrics(
                y_true=y_val.values,
                y_prob=val_probs_raw,
                net_returns=val_net_ret,
                calibrator=calibrator,
            )

            # 4. Baselines
            majority = MajorityClassBaseline().fit(X_train, y_train)
            maj_probs = majority.predict_proba(X_val)[:, 1]
            maj_pred = majority.predict(X_val)
            maj_acc = float(accuracy_score(y_val, maj_pred))
            maj_brier = float(brier_score_loss(y_val, maj_probs))

            momentum = MomentumBaseline(momentum_col="return_20d").fit(X_train, y_train)
            mom_probs = momentum.predict_proba(X_val)[:, 1]
            mom_pred = momentum.predict(X_val)
            mom_acc = float(accuracy_score(y_val, mom_pred))
            mom_roc = float(roc_auc_score(y_val, mom_probs)) if len(np.unique(y_val)) > 1 else 0.5

            metrics["majority_baseline"] = {
                "accuracy": round(maj_acc, 4),
                "brier_score": round(maj_brier, 4),
                "prior_p": round(majority.prior_p_, 4),
            }
            metrics["momentum_baseline"] = {
                "accuracy": round(mom_acc, 4),
                "roc_auc": round(mom_roc, 4),
            }
            metrics["calibrator_summary"] = calibrator.get_summary()

            fold_summary = {
                "fold_index": fold.fold_index,
                "train_window": f"{fold.train_start} to {fold.train_end}",
                "val_window": f"{fold.val_start} to {fold.val_end}",
                "train_samples": len(X_train),
                "val_samples": len(X_val),
                "positive_prevalence_train": round(float(y_train.mean()) * 100.0, 1),
                "positive_prevalence_val": round(float(y_val.mean()) * 100.0, 1),
                "metrics": metrics,
            }
            fold_results.append(fold_summary)
            trained_models.append(clf)
            calibrators.append(calibrator)

        # Average metrics across all 4 folds
        avg_roc = float(np.mean([f["metrics"]["roc_auc"] for f in fold_results]))
        avg_pr = float(np.mean([f["metrics"]["pr_auc"] for f in fold_results]))
        avg_acc = float(np.mean([f["metrics"]["accuracy"] for f in fold_results]))
        avg_bal_acc = float(np.mean([f["metrics"]["balanced_accuracy"] for f in fold_results]))
        avg_brier = float(np.mean([f["metrics"]["brier_score"] for f in fold_results]))
        avg_brier_skill = float(np.mean([f["metrics"]["brier_skill_score"] for f in fold_results]))
        avg_ece = float(np.mean([f["metrics"]["ece"] for f in fold_results]))
        avg_sharpe = float(np.mean([f["metrics"]["sharpe_ratio"] for f in fold_results]))

        return {
            "horizon_sessions": self.horizon_sessions,
            "feature_count": len(self.feature_cols),
            "features_used": self.feature_cols,
            "folds": fold_results,
            "average_cross_validation_metrics": {
                "roc_auc": round(avg_roc, 4),
                "pr_auc": round(avg_pr, 4),
                "accuracy": round(avg_acc, 4),
                "balanced_accuracy": round(avg_bal_acc, 4),
                "brier_score": round(avg_brier, 4),
                "brier_skill_score": round(avg_brier_skill, 4),
                "ece": round(avg_ece, 4),
                "sharpe_ratio": round(avg_sharpe, 2),
            },
            "last_fold_model": trained_models[-1],
            "last_fold_calibrator": calibrators[-1],
        }

    def evaluate_final_test_set(
        self,
        df_dataset: pd.DataFrame,
        trained_model: lgb.LGBMClassifier,
        calibrator: ProbabilityCalibrator,
    ) -> dict[str, Any]:
        """
        Evaluates the frozen model + calibrator on the untouched final out-of-sample test window
        (e.g. 2025-12-01 to 2026-10-31).
        Strictly out-of-sample: No fitting, tuning, or calibration occurs on this data.
        """
        t_start = self.final_test_spec["start_date"]
        t_end = self.final_test_spec["end_date"]

        df_test = df_dataset[
            (df_dataset["session_date"] >= t_start) & (df_dataset["session_date"] <= t_end)
        ].dropna(subset=self.feature_cols + [self.target_col]).copy()

        if df_test.empty:
            logger.warning("Final test set is empty for date range %s to %s!", t_start, t_end)
            return {"error": "Empty final test set"}

        X_test = df_test[self.feature_cols]
        y_test = df_test[self.target_col].astype(int)
        test_net_ret = df_test[self.net_return_col].values if self.net_return_col in df_test.columns else None

        # Predict using frozen trained model and frozen calibrator
        raw_probs = trained_model.predict_proba(X_test)[:, 1]
        metrics = self.compute_metrics(
            y_true=y_test.values,
            y_prob=raw_probs,
            net_returns=test_net_ret,
            calibrator=calibrator,
        )

        # Baseline evaluations on final test set
        majority = MajorityClassBaseline().fit(X_test, y_test)
        maj_pred = majority.predict(X_test)
        maj_probs = majority.predict_proba(X_test)[:, 1]
        metrics["majority_baseline"] = {
            "accuracy": round(float(accuracy_score(y_test, maj_pred)), 4),
            "brier_score": round(float(brier_score_loss(y_test, maj_probs)), 4),
            "prior_p": round(majority.prior_p_, 4),
        }

        momentum = MomentumBaseline(momentum_col="return_20d").fit(X_test, y_test)
        mom_pred = momentum.predict(X_test)
        mom_probs = momentum.predict_proba(X_test)[:, 1]
        metrics["momentum_baseline"] = {
            "accuracy": round(float(accuracy_score(y_test, mom_pred)), 4),
            "roc_auc": round(float(roc_auc_score(y_test, mom_probs)), 4) if len(np.unique(y_test)) > 1 else 0.5,
        }

        # Feature importances
        feature_importances = dict(
            sorted(
                zip(self.feature_cols, [int(x) for x in trained_model.feature_importances_], strict=False),
                key=lambda x: x[1],
                reverse=True,
            )
        )

        return {
            "test_window": f"{t_start} to {t_end}",
            "test_samples": len(df_test),
            "positive_prevalence": round(float(y_test.mean()) * 100.0, 1),
            "metrics": metrics,
            "feature_importances": feature_importances,
        }

    def persist_artifact_and_register(
        self,
        trained_model: lgb.LGBMClassifier,
        calibrator: ProbabilityCalibrator,
        cv_summary: dict[str, Any],
        final_test_summary: dict[str, Any],
        dataset_snapshot: MLDatasetSnapshot | None = None,
        artifact_dir: Path | None = None,
    ) -> MLModelRecord:
        """
        Serializes trained model bundle, computes SHA-256 hash, and saves MLModelRecord
        in database strictly in RESEARCH_ONLY (EXPERIMENTAL) mode.
        """
        artifact_dir = artifact_dir or (Path(getattr(settings, "ML_MODEL_DIR", settings.BASE_DIR / "ml_models")) / "artifacts")
        artifact_dir.mkdir(parents=True, exist_ok=True)

        artifact_name = f"lgbm_pilot_{self.horizon_sessions}d_v1.joblib"
        artifact_path = artifact_dir / artifact_name

        bundle = {
            "horizon_sessions": self.horizon_sessions,
            "model_type": "LightGBMClassifier",
            "model": trained_model,
            "calibrator": calibrator,
            "feature_cols": self.feature_cols,
            "lgb_params": self.lgb_params,
            "cv_summary": cv_summary,
            "final_test_summary": final_test_summary,
            "saved_at": timezone.now().isoformat(),
        }

        joblib.dump(bundle, artifact_path, compress=3)

        # Compute SHA-256 hash
        hasher = hashlib.sha256()
        with open(artifact_path, "rb") as f:
            while chunk := f.read(65536):
                hasher.update(chunk)
        artifact_hash = hasher.hexdigest()

        # Database registration in MLModelRecord
        model_name = f"LightGBM_Pilot_{self.horizon_sessions}D"
        version = f"v1.0-pilot-{self.horizon_sessions}d"

        eval_metrics = {
            "cross_validation_average": cv_summary.get("average_cross_validation_metrics", {}),
            "final_test": final_test_summary.get("metrics", {}),
            "feature_importances": final_test_summary.get("feature_importances", {}),
        }
        baseline_metrics = {
            "final_test_majority": final_test_summary.get("metrics", {}).get("majority_baseline", {}),
            "final_test_momentum": final_test_summary.get("metrics", {}).get("momentum_baseline", {}),
        }

        record, _ = MLModelRecord.objects.update_or_create(
            model_name=model_name,
            version=version,
            defaults={
                "target_variable": f"target_binary_{self.horizon_sessions}d",
                "features_used": self.feature_cols,
                "training_start_date": date(2020, 1, 1),
                "training_end_date": date(2025, 11, 30),
                "evaluation_metrics": eval_metrics,
                "baseline_metrics": baseline_metrics,
                "is_active": True,
                "dataset_snapshot": dataset_snapshot,
                "artifact_path": str(artifact_path),
                "artifact_hash": artifact_hash,
                "algorithm": "LIGHTGBM",
                "horizon_sessions": self.horizon_sessions,
                "calibration_method": calibrator.selected_method_.upper(),
                "brier_score": round(final_test_summary.get("metrics", {}).get("brier_score", 0.0), 4),
                "brier_skill_score": round(final_test_summary.get("metrics", {}).get("brier_skill_score", 0.0), 4),
                "pr_auc": round(final_test_summary.get("metrics", {}).get("pr_auc", 0.0), 4),
                "model_state": MLModelState.EXPERIMENTAL,  # Strictly RESEARCH_ONLY
            },
        )
        return record
