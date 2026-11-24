"""
Tests for Phase 1 ML Database Foundation, Models, and Constraints.
Verifies MLDatasetSnapshot, MLFeatureDefinition, MLMonitoringEvent, MLPredictionArchive,
model lifecycle states, conditional unique constraints, and prediction idempotency.
"""
from datetime import date, timedelta
from decimal import Decimal

import pytest
from django.db import IntegrityError, transaction
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.ml_engine.models import (
    MLDatasetSnapshot,
    MLFeatureDefinition,
    MLInferenceState,
    MLModelRecord,
    MLModelState,
    MLMonitoringEvent,
    MLPrediction,
    MLPredictionArchive,
    MLPredictionLabel,
)


@pytest.fixture
def test_listing(db):
    exchange, _ = Exchange.objects.get_or_create(code="NSE", defaults={"name": "NSE"})
    instrument, _ = Instrument.objects.get_or_create(
        isin="INE002A01018",
        defaults={
            "legal_name": "Reliance Industries Limited",
            "display_name": "Reliance Industries",
            "sector": "Energy",
        },
    )
    listing, _ = ExchangeListing.objects.get_or_create(
        exchange=exchange,
        symbol="RELIANCE",
        defaults={"instrument": instrument, "trading_symbol": "RELIANCE-EQ"},
    )
    return listing


@pytest.fixture
def test_dataset_snapshot(db):
    return MLDatasetSnapshot.objects.create(
        name="NIFTY 250 5-Year EOD Snapshot",
        version="snapshot-v1.0-20261124",
        start_date=date(2021, 1, 1),
        end_date=date(2026, 11, 20),
        universe_hash="e3b0c44298fc1c149afbf4c8996fb92427ae41e4649b934ca495991b7852b855",
        content_hash="cf83e1357eefb8bdf1542850d66d8007d620e4050b5715dc83f4a921d36ce9ce",
        universe_size=250,
        total_samples=300000,
        feature_count=14,
        corporate_action_version="corp-v1.0",
        feature_schema_version="feat-v1.0",
    )


@pytest.mark.django_db
class TestMLDatasetSnapshot:
    def test_create_and_str(self, test_dataset_snapshot):
        assert "snapshot-v1.0-20261124" in str(test_dataset_snapshot)
        assert test_dataset_snapshot.universe_size == 250
        assert test_dataset_snapshot.quality_status == "VALIDATED"

    def test_version_uniqueness(self, test_dataset_snapshot):
        with pytest.raises(IntegrityError):
            MLDatasetSnapshot.objects.create(
                name="Duplicate Snapshot",
                version="snapshot-v1.0-20261124",
                start_date=date(2022, 1, 1),
                end_date=date(2026, 11, 20),
                universe_hash="abc",
            )


@pytest.mark.django_db
class TestMLFeatureDefinition:
    def test_create_feature_definition(self):
        feat = MLFeatureDefinition.objects.create(
            name="rsi_14",
            category="MOMENTUM",
            lookback_periods=14,
            calculation_version="feat-v1.0",
            formula_description="Wilder smoothed 14-period Relative Strength Index",
        )
        assert str(feat) == "rsi_14 (MOMENTUM, 14p)"
        assert feat.is_active is True

    def test_name_uniqueness(self):
        MLFeatureDefinition.objects.create(name="sma_50", category="TREND")
        with pytest.raises(IntegrityError):
            MLFeatureDefinition.objects.create(name="sma_50", category="TREND")


@pytest.mark.django_db
class TestMLModelRecordLifecycleAndConstraints:
    def test_at_most_one_approved_model_per_horizon_constraint(self, test_dataset_snapshot):
        today = timezone.now().date()
        # 1. First approved model for 10-day horizon
        m1 = MLModelRecord.objects.create(
            model_name="lgbm_horizon_10d",
            version="v1.0",
            target_variable="positive_forward_return_10d",
            training_start_date=today - timedelta(days=730),
            training_end_date=today - timedelta(days=30),
            horizon_sessions=10,
            model_state=MLModelState.APPROVED,
            algorithm="LIGHTGBM",
            dataset_snapshot=test_dataset_snapshot,
        )
        assert m1.model_state == MLModelState.APPROVED

        # 2. Approved model for 5-day horizon is allowed (different horizon)
        m2 = MLModelRecord.objects.create(
            model_name="lgbm_horizon_5d",
            version="v1.0",
            target_variable="positive_forward_return_5d",
            training_start_date=today - timedelta(days=730),
            training_end_date=today - timedelta(days=30),
            horizon_sessions=5,
            model_state=MLModelState.APPROVED,
            algorithm="LIGHTGBM",
        )
        assert m2.model_state == MLModelState.APPROVED

        # 3. Multiple experimental or retired models for horizon 10 are allowed
        m3_exp = MLModelRecord.objects.create(
            model_name="lgbm_horizon_10d_exp",
            version="v1.1-exp",
            target_variable="positive_forward_return_10d",
            training_start_date=today - timedelta(days=730),
            training_end_date=today - timedelta(days=30),
            horizon_sessions=10,
            model_state=MLModelState.EXPERIMENTAL,
        )
        m4_ret = MLModelRecord.objects.create(
            model_name="lgbm_horizon_10d_ret",
            version="v0.9-ret",
            target_variable="positive_forward_return_10d",
            training_start_date=today - timedelta(days=730),
            training_end_date=today - timedelta(days=30),
            horizon_sessions=10,
            model_state=MLModelState.RETIRED,
        )
        assert m3_exp.id is not None
        assert m4_ret.id is not None

        # 4. Attempting to create a SECOND approved model for horizon 10 MUST fail database constraint
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MLModelRecord.objects.create(
                    model_name="lgbm_horizon_10d_second_approved",
                    version="v1.2",
                    target_variable="positive_forward_return_10d",
                    training_start_date=today - timedelta(days=730),
                    training_end_date=today - timedelta(days=30),
                    horizon_sessions=10,
                    model_state=MLModelState.APPROVED,
                )

    def test_atomic_promotion_and_rollback(self):
        today = timezone.now().date()
        m1 = MLModelRecord.objects.create(
            model_name="lgbm_horizon_20d",
            version="v1.0",
            target_variable="positive_forward_return_20d",
            training_start_date=today - timedelta(days=365),
            training_end_date=today,
            horizon_sessions=20,
            model_state=MLModelState.APPROVED,
        )

        candidate = MLModelRecord.objects.create(
            model_name="lgbm_horizon_20d",
            version="v2.0",
            target_variable="positive_forward_return_20d",
            training_start_date=today - timedelta(days=365),
            training_end_date=today,
            horizon_sessions=20,
            model_state=MLModelState.EXPERIMENTAL,
        )

        # Atomic promotion: retire old, promote new
        with transaction.atomic():
            m1.model_state = MLModelState.RETIRED
            m1.save(update_fields=["model_state"])

            candidate.model_state = MLModelState.APPROVED
            candidate.previous_approved_version = m1
            candidate.save(update_fields=["model_state", "previous_approved_version"])

        m1.refresh_from_db()
        candidate.refresh_from_db()
        assert m1.model_state == MLModelState.RETIRED
        assert candidate.model_state == MLModelState.APPROVED
        assert candidate.previous_approved_version == m1

        # Atomic rollback
        with transaction.atomic():
            candidate.model_state = MLModelState.RETIRED
            candidate.save(update_fields=["model_state"])

            m1.model_state = MLModelState.APPROVED
            m1.save(update_fields=["model_state"])

        m1.refresh_from_db()
        candidate.refresh_from_db()
        assert m1.model_state == MLModelState.APPROVED
        assert candidate.model_state == MLModelState.RETIRED


@pytest.mark.django_db
class TestMLPredictionIdempotencyAndStates:
    def test_unique_listing_model_horizon_session_constraint(self, test_listing):
        today = timezone.now().date()
        model_rec = MLModelRecord.objects.create(
            model_name="test_model",
            version="v1.0",
            target_variable="forward_10d",
            training_start_date=today - timedelta(days=100),
            training_end_date=today,
            horizon_sessions=10,
        )

        # First prediction for today
        p1 = MLPrediction.objects.create(
            listing=test_listing,
            model_record=model_rec,
            prediction_timestamp=timezone.now(),
            prediction_label=MLPredictionLabel.BULLISH_EXPANSION,
            confidence_score=Decimal("0.7500"),
            horizon_sessions=10,
            as_of_session=today,
            is_heuristic=False,
            inference_state=MLInferenceState.APPROVED_MODEL,
        )
        assert p1.id is not None

        # Duplicate prediction for identical (listing, model_record, horizon, as_of_session) must fail
        with pytest.raises(IntegrityError):
            with transaction.atomic():
                MLPrediction.objects.create(
                    listing=test_listing,
                    model_record=model_rec,
                    prediction_timestamp=timezone.now(),
                    prediction_label=MLPredictionLabel.SIDEWAYS_CONSOLIDATION,
                    confidence_score=Decimal("0.5000"),
                    horizon_sessions=10,
                    as_of_session=today,
                )

        # Different horizon (5d) on same session date is allowed
        p_5d = MLPrediction.objects.create(
            listing=test_listing,
            model_record=model_rec,
            prediction_timestamp=timezone.now(),
            prediction_label=MLPredictionLabel.BULLISH_EXPANSION,
            confidence_score=Decimal("0.6500"),
            horizon_sessions=5,
            as_of_session=today,
        )
        assert p_5d.id is not None

    def test_prediction_archive_preservation(self, test_listing):
        today = timezone.now().date()
        model_rec = MLModelRecord.objects.create(
            model_name="test_model_archive",
            version="v1.0",
            target_variable="forward_10d",
            training_start_date=today - timedelta(days=100),
            training_end_date=today,
            horizon_sessions=10,
        )
        pred = MLPrediction.objects.create(
            listing=test_listing,
            model_record=model_rec,
            prediction_timestamp=timezone.now(),
            prediction_label=MLPredictionLabel.BEARISH_CONTRACTION,
            confidence_score=Decimal("0.3200"),
            horizon_sessions=10,
            as_of_session=today,
        )

        # Archive duplicate
        arch = MLPredictionArchive.objects.create(
            original_prediction_id=pred.id,
            listing=test_listing,
            model_record=model_rec,
            prediction_timestamp=pred.prediction_timestamp,
            prediction_label=pred.prediction_label,
            confidence_score=pred.confidence_score,
            regime_classification=pred.regime_classification,
            feature_contributions=pred.feature_contributions,
            disclaimer=pred.disclaimer,
            horizon_sessions=pred.horizon_sessions,
            as_of_session=pred.as_of_session,
            archive_reason="MIGRATION_DUPLICATE_KEY_RESOLUTION",
        )
        assert arch.original_prediction_id == pred.id
        assert "MIGRATION_DUPLICATE_KEY_RESOLUTION" in arch.archive_reason


@pytest.mark.django_db
class TestMLMonitoringEvents:
    def test_create_monitoring_event(self):
        today = timezone.now().date()
        model_rec = MLModelRecord.objects.create(
            model_name="drift_model",
            version="v1.0",
            target_variable="forward_10d",
            training_start_date=today - timedelta(days=100),
            training_end_date=today,
        )
        event = MLMonitoringEvent.objects.create(
            model_record=model_rec,
            event_type="CALIBRATION_DECAY",
            severity="HIGH",
            details={"brier_score": 0.285, "brier_skill_score": -0.042},
        )
        assert event.severity == "HIGH"
        assert event.details["brier_score"] == 0.285
        assert "CALIBRATION_DECAY" in str(event)
