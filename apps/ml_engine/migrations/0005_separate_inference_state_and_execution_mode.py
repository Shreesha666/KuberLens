# Generated manually for Phase 1.1: Separate inference state from execution mode
from django.db import migrations, models


def forwards_func(apps, schema_editor):
    MLPrediction = apps.get_model("ml_engine", "MLPrediction")
    MLPredictionArchive = apps.get_model("ml_engine", "MLPredictionArchive")

    # 1. Update all existing predictions:
    # Set execution_mode to ONLINE_REALTIME
    # For heuristic predictions: enforce is_heuristic=True, inference_state=HEURISTIC_FALLBACK,
    # calibration_status=UNCALIBRATED, calibrated_probability=None, while preserving confidence_score and timestamps.
    for pred in MLPrediction.objects.all():
        pred.execution_mode = "ONLINE_REALTIME"
        if pred.is_heuristic or (pred.model_record and pred.model_record.model_state == "LEGACY_HEURISTIC"):
            pred.is_heuristic = True
            if pred.inference_state not in ["HEURISTIC_FALLBACK", "INSUFFICIENT_DATA", "STALE_DATA"]:
                pred.inference_state = "HEURISTIC_FALLBACK"
            pred.calibration_status = "UNCALIBRATED"
            pred.calibrated_probability = None
        pred.save(update_fields=[
            "execution_mode",
            "is_heuristic",
            "inference_state",
            "calibration_status",
            "calibrated_probability",
        ])

    # 2. Update archived predictions to default execution_mode
    MLPredictionArchive.objects.filter(execution_mode="").update(execution_mode="ONLINE_REALTIME")


def reverse_func(apps, schema_editor):
    pass


class Migration(migrations.Migration):

    dependencies = [
        ("ml_engine", "0004_enforce_database_constraints"),
    ]

    operations = [
        migrations.AddField(
            model_name="mlprediction",
            name="execution_mode",
            field=models.CharField(
                choices=[
                    ("ONLINE_REALTIME", "Online Real-Time"),
                    ("EOD_BATCH_SCHEDULED", "EOD Batch Scheduled"),
                    ("MANUAL_ADHOC", "Manual Ad-Hoc"),
                    ("BACKTEST_SIMULATED", "Backtest Simulated"),
                ],
                db_index=True,
                default="ONLINE_REALTIME",
                help_text="Execution mode under which inference was triggered.",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="mlpredictionarchive",
            name="execution_mode",
            field=models.CharField(
                blank=True,
                choices=[
                    ("ONLINE_REALTIME", "Online Real-Time"),
                    ("EOD_BATCH_SCHEDULED", "EOD Batch Scheduled"),
                    ("MANUAL_ADHOC", "Manual Ad-Hoc"),
                    ("BACKTEST_SIMULATED", "Backtest Simulated"),
                ],
                default="ONLINE_REALTIME",
                max_length=30,
            ),
        ),
        migrations.AlterField(
            model_name="mlprediction",
            name="inference_state",
            field=models.CharField(
                choices=[
                    ("APPROVED_MODEL", "Approved Model (Calibrated)"),
                    ("EXPERIMENTAL_MODEL", "Experimental Model"),
                    ("HEURISTIC_FALLBACK", "Heuristic Fallback (Rule-Based)"),
                    ("STALE_DATA", "Stale Market Data"),
                    ("INSUFFICIENT_DATA", "Insufficient Data"),
                ],
                db_index=True,
                default="HEURISTIC_FALLBACK",
                help_text="APPROVED_MODEL, EXPERIMENTAL_MODEL, HEURISTIC_FALLBACK, STALE_DATA, or INSUFFICIENT_DATA.",
                max_length=30,
            ),
        ),
        migrations.RunPython(forwards_func, reverse_func),
    ]
