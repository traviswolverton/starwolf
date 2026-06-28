from django.db import migrations, models


class Migration(migrations.Migration):
    """
    best_metric column was added to the DB directly in a prior session before
    migrations were in place. This migration syncs Django's state without
    issuing an ALTER TABLE (which would fail with "column already exists").
    """

    dependencies = [
        ("accounts", "0003_userpreferences_best_metric_equipment"),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(
            database_operations=[],  # column already exists — don't touch the DB
            state_operations=[
                migrations.AddField(
                    model_name="userpreferences",
                    name="best_metric",
                    field=models.CharField(
                        choices=[
                            ("telescope", "Telescope"),
                            ("naked_eye", "Naked Eye"),
                            ("combined",  "Combined"),
                        ],
                        default="combined",
                        max_length=16,
                    ),
                ),
            ],
        ),
    ]
