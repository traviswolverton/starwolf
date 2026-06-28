from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0002_userpreferences"),
    ]

    operations = [
        migrations.AddField(
            model_name="userpreferences",
            name="equipment",
            field=models.CharField(
                blank=True,
                choices=[
                    ("naked_eye",   "Naked Eye"),
                    ("binoculars",  "Binoculars (7×50)"),
                    ("small_scope", 'Small Telescope (4–6")'),
                    ("large_scope", 'Large Telescope (10"+)'),
                ],
                max_length=16,
                null=True,
            ),
        ),
    ]
