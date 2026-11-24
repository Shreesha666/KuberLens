from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("ml_engine", "0003_legacy_data_backfill_and_archive"),
    ]

    operations = [
        migrations.AlterField(
            model_name="mlprediction",
            name="as_of_session",
            field=models.DateField(
                db_index=True,
                help_text="Market trading session date (point-in-time close date).",
            ),
        ),
        migrations.AddConstraint(
            model_name="mlmodelrecord",
            constraint=models.UniqueConstraint(
                condition=models.Q(model_state="APPROVED"),
                fields=("horizon_sessions",),
                name="unique_approved_model_per_horizon",
            ),
        ),
        migrations.AddConstraint(
            model_name="mlprediction",
            constraint=models.UniqueConstraint(
                fields=("listing", "model_record", "horizon_sessions", "as_of_session"),
                name="unique_listing_model_horizon_session",
            ),
        ),
    ]
