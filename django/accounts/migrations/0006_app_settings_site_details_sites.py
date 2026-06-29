from django.db import migrations, models


class Migration(migrations.Migration):
    """
    Registers pre-existing tables (app_settings, site_details, sites) as
    Django-managed models. Applied with --fake on existing DBs since the
    tables already exist.
    """

    dependencies = [
        ("accounts", "0005_sky_catalog"),
    ]

    operations = [
        migrations.CreateModel(
            name="AppSetting",
            fields=[
                ("key",         models.CharField(max_length=100, primary_key=True, serialize=False)),
                ("value",       models.TextField()),
                ("description", models.TextField(blank=True)),
            ],
            options={"db_table": "app_settings", "ordering": ["key"]},
        ),
    ]
