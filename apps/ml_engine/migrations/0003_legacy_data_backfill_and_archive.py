from django.db import migrations


def forwards_func(apps, schema_editor):
    MLModelRecord = apps.get_model("ml_engine", "MLModelRecord")
    MLPrediction = apps.get_model("ml_engine", "MLPrediction")
    MLPredictionArchive = apps.get_model("ml_engine", "MLPredictionArchive")

    # 1. Update legacy MLModelRecord instances to explicit legacy heuristic state
    MLModelRecord.objects.all().update(
        algorithm="HEURISTIC_RULE_BASED",
        model_state="LEGACY_HEURISTIC",
        calibration_method="NONE",
        horizon_sessions=10,
    )

    # 2. Backfill existing predictions as_of_session and state attributes
    for pred in MLPrediction.objects.all():
        pred.as_of_session = pred.prediction_timestamp.date()
        pred.horizon_sessions = 10
        pred.is_heuristic = True
        pred.inference_state = "HEURISTIC_FALLBACK"
        pred.calibration_status = "UNCALIBRATED"
        pred.save(update_fields=[
            "as_of_session",
            "horizon_sessions",
            "is_heuristic",
            "inference_state",
            "calibration_status",
        ])

    # 3. Deduplicate active predictions by archiving conflicting duplicates
    # We order by descending prediction_timestamp so that the most recent record is kept
    processed_keys = set()
    for pred in MLPrediction.objects.all().order_by("-prediction_timestamp", "-created_at"):
        key = (pred.listing_id, pred.model_record_id, pred.horizon_sessions, pred.as_of_session)
        if key in processed_keys:
            # Conflicting duplicate key detected: archive into MLPredictionArchive preserving full metadata
            MLPredictionArchive.objects.create(
                original_prediction_id=pred.id,
                listing_id=pred.listing_id,
                model_record_id=pred.model_record_id,
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
            pred.delete()
        else:
            processed_keys.add(key)


def reverse_func(apps, schema_editor):
    MLPrediction = apps.get_model("ml_engine", "MLPrediction")
    MLPredictionArchive = apps.get_model("ml_engine", "MLPredictionArchive")

    # Restore archived records back into active table
    for arch in MLPredictionArchive.objects.filter(archive_reason="MIGRATION_DUPLICATE_KEY_RESOLUTION"):
        MLPrediction.objects.create(
            id=arch.original_prediction_id,
            listing_id=arch.listing_id,
            model_record_id=arch.model_record_id,
            prediction_timestamp=arch.prediction_timestamp,
            prediction_label=arch.prediction_label,
            confidence_score=arch.confidence_score,
            regime_classification=arch.regime_classification,
            feature_contributions=arch.feature_contributions,
            disclaimer=arch.disclaimer,
            horizon_sessions=arch.horizon_sessions,
            as_of_session=arch.as_of_session,
            is_heuristic=True,
            inference_state="HEURISTIC_FALLBACK",
            calibration_status="UNCALIBRATED",
        )
        arch.delete()


class Migration(migrations.Migration):

    dependencies = [
        ("ml_engine", "0002_aiml_schema_extensions"),
    ]

    operations = [
        migrations.RunPython(forwards_func, reverse_func),
    ]
