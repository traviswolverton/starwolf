from django.db import migrations, models

BORTLE_SEED = [
    # (bortle_class, composite_modifier, naked_eye_modifier, description)
    (1, 1.00, 1.00, "Excellent dark sky — no penalty on either score."),
    (2, 1.00, 1.00, "Truly dark site — no penalty on either score."),
    (3, 0.97, 0.95, "Rural sky — minimal penalty; Milky Way prominent."),
    (4, 0.92, 0.85, "Rural/suburban transition — mild penalty; Milky Way visible."),
    (5, 0.82, 0.65, "Suburban sky — moderate penalty; Milky Way faint or gone."),
    (6, 0.68, 0.40, "Bright suburban — heavy naked-eye penalty; scopes still viable for showpieces."),
    (7, 0.48, 0.20, "Suburban/urban — severe penalty; DSO contrast collapsing."),
    (8, 0.28, 0.08, "City sky — near-zero for naked eye; planets/moon/doubles only."),
    (9, 0.12, 0.03, "Inner city — extreme penalty; only bright planets and Moon viable."),
]


def seed_bortle_modifiers(apps, schema_editor):
    BortleModifier = apps.get_model("accounts", "BortleModifier")
    for bortle, comp, ne, desc in BORTLE_SEED:
        BortleModifier.objects.get_or_create(
            bortle_class=bortle,
            defaults={"composite_modifier": comp, "naked_eye_modifier": ne, "description": desc},
        )


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0011_add_sky_object_details"),
    ]

    operations = [
        migrations.CreateModel(
            name="BortleModifier",
            fields=[
                ("id", models.BigAutoField(auto_created=True, primary_key=True, serialize=False)),
                ("bortle_class", models.IntegerField(unique=True)),
                ("composite_modifier", models.FloatField(help_text="Multiplier applied to the composite (telescope) score (0–1).")),
                ("naked_eye_modifier", models.FloatField(help_text="Multiplier applied to the naked-eye score (0–1).")),
                ("description", models.TextField(blank=True)),
            ],
            options={"db_table": "bortle_modifiers", "ordering": ["bortle_class"]},
        ),
        migrations.RunPython(seed_bortle_modifiers, migrations.RunPython.noop),
    ]
