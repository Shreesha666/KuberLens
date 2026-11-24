# Generated manually to enforce safe transitional schema extensions
from decimal import Decimal
import uuid
import django.db.models.deletion
from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("instruments", "0001_initial"),
        ("ml_engine", "0001_initial"),
    ]

    operations = [
        migrations.CreateModel(
            name="MLDatasetSnapshot",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(max_length=150)),
                ("version", models.CharField(db_index=True, max_length=50, unique=True)),
                ("start_date", models.DateField()),
                ("end_date", models.DateField()),
                ("universe_hash", models.CharField(help_text="SHA-256 hash of eligible universe ISINs", max_length=64)),
                ("content_hash", models.CharField(blank=True, help_text="SHA-256 hash of canonical extracted dataset", max_length=64)),
                ("universe_size", models.PositiveIntegerField(default=0)),
                ("total_samples", models.PositiveIntegerField(default=0)),
                ("feature_count", models.PositiveIntegerField(default=0)),
                ("corporate_action_version", models.CharField(default="corp-v1.0", max_length=50)),
                ("feature_schema_version", models.CharField(default="feat-v1.0", max_length=50)),
                ("quality_status", models.CharField(default="VALIDATED", max_length=30)),
                ("storage_path", models.CharField(blank=True, max_length=255)),
                ("metadata", models.JSONField(blank=True, default=dict)),
            ],
            options={
                "verbose_name": "ML Dataset Snapshot",
                "verbose_name_plural": "ML Dataset Snapshots",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MLFeatureDefinition",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("name", models.CharField(db_index=True, max_length=100, unique=True)),
                ("category", models.CharField(db_index=True, max_length=50)),
                ("lookback_periods", models.PositiveIntegerField(default=14)),
                ("calculation_version", models.CharField(default="feat-v1.0", max_length=50)),
                ("formula_description", models.TextField(blank=True)),
                ("is_active", models.BooleanField(db_index=True, default=True)),
            ],
            options={
                "verbose_name": "ML Feature Definition",
                "verbose_name_plural": "ML Feature Definitions",
                "ordering": ["category", "name"],
            },
        ),
        migrations.CreateModel(
            name="MLMonitoringEvent",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("event_type", models.CharField(db_index=True, max_length=50)),
                ("severity", models.CharField(db_index=True, default="MEDIUM", max_length=20)),
                ("details", models.JSONField(blank=True, default=dict)),
                (
                    "model_record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="monitoring_events",
                        to="ml_engine.mlmodelrecord",
                    ),
                ),
            ],
            options={
                "verbose_name": "ML Monitoring Event",
                "verbose_name_plural": "ML Monitoring Events",
                "ordering": ["-created_at"],
            },
        ),
        migrations.CreateModel(
            name="MLPredictionArchive",
            fields=[
                ("id", models.UUIDField(default=uuid.uuid4, editable=False, primary_key=True, serialize=False)),
                ("created_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("updated_at", models.DateTimeField(auto_now=True)),
                ("original_prediction_id", models.UUIDField(db_index=True)),
                ("prediction_timestamp", models.DateTimeField(db_index=True)),
                ("prediction_label", models.CharField(max_length=50)),
                ("confidence_score", models.DecimalField(decimal_places=4, default=Decimal("0.5000"), max_digits=5)),
                ("regime_classification", models.CharField(default="RANGE_BOUND", max_length=50)),
                ("feature_contributions", models.JSONField(blank=True, default=dict)),
                ("disclaimer", models.CharField(blank=True, max_length=250)),
                ("horizon_sessions", models.PositiveSmallIntegerField(default=10)),
                ("as_of_session", models.DateField(blank=True, null=True)),
                ("archived_at", models.DateTimeField(auto_now_add=True, db_index=True)),
                ("archive_reason", models.CharField(default="MIGRATION_DUPLICATE_KEY_RESOLUTION", max_length=100)),
                (
                    "listing",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="archived_ml_predictions",
                        to="instruments.exchangelisting",
                    ),
                ),
                (
                    "model_record",
                    models.ForeignKey(
                        on_delete=django.db.models.deletion.CASCADE,
                        related_name="archived_predictions",
                        to="ml_engine.mlmodelrecord",
                    ),
                ),
            ],
            options={
                "verbose_name": "ML Prediction Archive",
                "verbose_name_plural": "ML Prediction Archives",
                "ordering": ["-archived_at"],
            },
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="dataset_snapshot",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="trained_models",
                to="ml_engine.mldatasetsnapshot",
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="previous_approved_version",
            field=models.ForeignKey(
                blank=True,
                null=True,
                on_delete=django.db.models.deletion.SET_NULL,
                related_name="superseded_by",
                to="ml_engine.mlmodelrecord",
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="artifact_path",
            field=models.CharField(
                blank=True,
                default="",
                help_text="Filesystem path to joblib serialized bundle under models/lightgbm/.",
                max_length=255,
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="artifact_hash",
            field=models.CharField(
                blank=True,
                default="",
                help_text="SHA-256 checksum of the serialized joblib artifact.",
                max_length=64,
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="algorithm",
            field=models.CharField(
                db_index=True,
                default="HEURISTIC_RULE_BASED",
                help_text="e.g. LIGHTGBM, HEURISTIC_RULE_BASED",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="horizon_sessions",
            field=models.PositiveSmallIntegerField(
                db_index=True,
                default=10,
                help_text="Prediction horizon in trading sessions (5, 10, or 20).",
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="calibration_method",
            field=models.CharField(
                blank=True,
                default="NONE",
                help_text="ISOTONIC, SIGMOID, or NONE.",
                max_length=50,
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="brier_score",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Out-of-sample Brier score.",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="brier_skill_score",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Brier Skill Score relative to training prevalence prior.",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="pr_auc",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Precision-Recall Area Under Curve.",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mlmodelrecord",
            name="model_state",
            field=models.CharField(
                choices=[
                    ("EXPERIMENTAL", "Experimental"),
                    ("VALIDATED", "Validated"),
                    ("APPROVED", "Approved"),
                    ("RETIRED", "Retired"),
                    ("FAILED", "Failed"),
                    ("LEGACY_HEURISTIC", "Legacy Heuristic"),
                ],
                db_index=True,
                default="EXPERIMENTAL",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="mlprediction",
            name="horizon_sessions",
            field=models.PositiveSmallIntegerField(
                db_index=True,
                default=10,
                help_text="Prediction horizon in trading sessions (5, 10, or 20).",
            ),
        ),
        migrations.AddField(
            model_name="mlprediction",
            name="as_of_session",
            field=models.DateField(
                blank=True,
                db_index=True,
                help_text="Market trading session date (point-in-time close date).",
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mlprediction",
            name="target_definition",
            field=models.CharField(
                default="forward_10d_directional_probability",
                max_length=100,
            ),
        ),
        migrations.AddField(
            model_name="mlprediction",
            name="raw_probability",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Uncalibrated model probability score.",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mlprediction",
            name="calibrated_probability",
            field=models.DecimalField(
                blank=True,
                decimal_places=4,
                help_text="Calibrated probability score.",
                max_digits=6,
                null=True,
            ),
        ),
        migrations.AddField(
            model_name="mlprediction",
            name="calibration_status",
            field=models.CharField(
                db_index=True,
                default="UNCALIBRATED",
                help_text="CALIBRATED, RAW, UNCALIBRATED, or FALLBACK.",
                max_length=30,
            ),
        ),
        migrations.AddField(
            model_name="mlprediction",
            name="is_heuristic",
            field=models.BooleanField(
                db_index=True,
                default=True,
                help_text="True if generated by rule fallback, False if trained statistical model.",
            ),
        ),
        migrations.AddField(
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
                max_length=30,
            ),
        ),
    ]
