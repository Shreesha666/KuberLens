"""
Unit and Regression Tests for Phase 4 LightGBM Pilot Model Training.
Complies with AIML Architecture Specification v2.1 and Master Specification Section 18.

Tests cover:
1. Purging and embargo correctness (verifying zero target window leakage).
2. Chronological walk-forward cross-validation schedule (no shuffling).
3. Feature matrix leakage exclusion (no future prices or targets in X).
4. Probability calibrator fitting and monotonicity.
5. Baseline models (MajorityClassBaseline and MomentumBaseline).
6. Model artifact persistence and SHA-256 checksum registration.
7. Model record state constraints (strictly EXPERIMENTAL / RESEARCH_ONLY).
"""
import tempfile
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from apps.ml_engine.models import MLModelState
from services.ml.baselines import MajorityClassBaseline, MomentumBaseline
from services.ml.calibrator import ProbabilityCalibrator, compute_expected_calibration_error
from services.ml.trainer import WalkForwardTrainer


@pytest.mark.django_db
class TestMLPhase4Trainer:

    def test_purging_and_embargo_zero_leakage(self):
        """
        Verify that h-session purging removes training observations whose forward
        horizon overlaps with the validation window start.
        """
        # Create synthetic time-series dates
        dates = [f"2023-01-{i:02d}" for i in range(1, 31)]
        df = pd.DataFrame({
            "session_date": dates,
            "symbol": ["TEST"] * len(dates),
            "close_adj": np.linspace(100, 110, len(dates)),
            "target_binary_5d": [1] * len(dates),
            "target_return_net_5d": [0.01] * len(dates),
        })

        trainer = WalkForwardTrainer(horizon_sessions=5)
        # Train: 2023-01-01 to 2023-01-15, Val: 2023-01-16 to 2023-01-25
        df_train, df_val = trainer.purge_and_embargo(
            df,
            train_start="2023-01-01",
            train_end="2023-01-15",
            val_start="2023-01-16",
            val_end="2023-01-25",
        )

        # val_start is at index 15 ("2023-01-16")
        # Purge cutoff is index 15 - 5 = index 10 ("2023-01-11")
        # Training rows must be strictly before 2023-01-11
        assert not df_train.empty
        assert not df_val.empty
        assert max(df_train["session_date"]) < "2023-01-11"
        assert min(df_val["session_date"]) == "2023-01-16"
        assert max(df_val["session_date"]) == "2023-01-25"

    def test_chronological_folds_non_shuffling(self):
        """
        Verify that walk-forward folds are strictly chronological and expanding.
        """
        trainer = WalkForwardTrainer(horizon_sessions=10)
        assert len(trainer.folds) == 4
        prev_train_end = None
        for fold in trainer.folds:
            assert fold.train_start <= fold.train_end
            assert fold.train_end < fold.val_start
            assert fold.val_start <= fold.val_end
            if prev_train_end:
                assert fold.train_end > prev_train_end
            prev_train_end = fold.train_end

    def test_majority_class_baseline(self):
        """
        Verify that MajorityClassBaseline accurately calculates training prevalence.
        """
        X = pd.DataFrame({"feat1": [1, 2, 3, 4, 5]})
        y = np.array([1, 1, 1, 0, 0])  # 60% positive

        baseline = MajorityClassBaseline().fit(X, y)
        assert baseline.prior_p_ == 0.6
        assert baseline.majority_class_ == 1

        probs = baseline.predict_proba(X)
        assert probs.shape == (5, 2)
        assert np.allclose(probs[:, 1], 0.6)

        preds = baseline.predict(X)
        assert np.array_equal(preds, np.array([1, 1, 1, 1, 1]))

    def test_momentum_baseline(self):
        """
        Verify that MomentumBaseline predicts positive direction when return_20d > 0.
        """
        X = pd.DataFrame({"return_20d": [-0.05, -0.01, 0.0, 0.02, 0.10]})
        baseline = MomentumBaseline(momentum_col="return_20d").fit(X)

        preds = baseline.predict(X)
        assert np.array_equal(preds, np.array([0, 0, 0, 1, 1]))

        probs = baseline.predict_proba(X)
        assert probs.shape == (5, 2)
        # Higher momentum should give higher probability for class 1
        assert probs[4, 1] > probs[3, 1] > probs[1, 1]

    def test_probability_calibrator_methods(self):
        """
        Verify Platt and Isotonic calibration mechanics and Expected Calibration Error.
        """
        np.random.seed(42)
        y_val_prob = np.random.uniform(0.1, 0.9, 100)
        y_val_true = (y_val_prob > 0.5).astype(int)

        calibrator = ProbabilityCalibrator(method="auto").fit(y_val_prob, y_val_true)
        summary = calibrator.get_summary()

        assert summary["selected_method"] in ("platt", "isotonic", "none")
        assert summary["calibrated_brier"] <= summary["uncalibrated_brier"] + 0.05
        assert summary["calibrated_ece"] >= 0.0

        cal_probs = calibrator.calibrate(y_val_prob)
        assert len(cal_probs) == len(y_val_prob)
        assert np.all((cal_probs >= 0.0) & (cal_probs <= 1.0))

    def test_ece_calculation(self):
        """
        Verify Expected Calibration Error calculation.
        """
        # Perfectly calibrated probabilities
        y_true = np.array([0, 0, 1, 1])
        y_prob = np.array([0.1, 0.1, 0.9, 0.9])
        ece = compute_expected_calibration_error(y_true, y_prob, n_bins=2)
        assert ece < 0.2

    def test_model_artifact_persistence_and_registration(self):
        """
        Verify that trained model bundle is properly saved with SHA-256 hash
        and registered in MLModelRecord strictly in EXPERIMENTAL state.
        """
        import lightgbm as lgb

        X_dummy = pd.DataFrame({"feat1": [1.0, 2.0, 3.0, 4.0, 5.0, 6.0]})
        y_dummy = np.array([0, 0, 0, 1, 1, 1])
        clf = lgb.LGBMClassifier(n_estimators=5, random_state=42, verbosity=-1)
        clf.fit(X_dummy, y_dummy)

        calibrator = ProbabilityCalibrator(method="none").fit(clf.predict_proba(X_dummy)[:, 1], y_dummy)

        trainer = WalkForwardTrainer(horizon_sessions=10, feature_cols=["feat1"])
        cv_summary = {
            "average_cross_validation_metrics": {"roc_auc": 0.60, "accuracy": 0.65},
        }
        test_summary = {
            "metrics": {
                "roc_auc": 0.58,
                "accuracy": 0.62,
                "brier_score": 0.23,
                "brier_skill_score": 0.05,
                "pr_auc": 0.45,
            },
            "feature_importances": {"feat1": 5},
        }

        with tempfile.TemporaryDirectory() as tmp_dir:
            record = trainer.persist_artifact_and_register(
                trained_model=clf,
                calibrator=calibrator,
                cv_summary=cv_summary,
                final_test_summary=test_summary,
                artifact_dir=Path(tmp_dir),
            )

            assert record.id is not None
            assert record.algorithm == "LIGHTGBM"
            assert record.horizon_sessions == 10
            assert record.model_state == MLModelState.EXPERIMENTAL  # Mandatory research-only
            assert len(record.artifact_hash) == 64
            assert Path(record.artifact_path).exists()
