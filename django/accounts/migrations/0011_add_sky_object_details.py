from django.db import migrations, models
import django.db.models.deletion


class Migration(migrations.Migration):

    dependencies = [
        ("accounts", "0010_scoring_weights"),
    ]

    operations = [
        migrations.CreateModel(
            name="SkyObjectDetail",
            fields=[
                ("sky_object", models.OneToOneField(on_delete=django.db.models.deletion.CASCADE, primary_key=True, related_name="detail", serialize=False, to="accounts.skyobject")),
                ("wikipedia_url", models.TextField(blank=True, null=True)),
                ("wikipedia_summary", models.TextField(blank=True, null=True)),
                ("image_url", models.TextField(blank=True, null=True)),
                ("image_credit", models.TextField(blank=True, null=True)),
                ("constellation", models.CharField(blank=True, max_length=50)),
                ("distance_ly", models.FloatField(blank=True, null=True)),
                ("angular_size_arcmin", models.FloatField(blank=True, null=True)),
                ("discovery_year", models.IntegerField(blank=True, null=True)),
                ("discoverer", models.CharField(blank=True, max_length=100)),
                ("enriched_at", models.DateTimeField(blank=True, null=True)),
            ],
            options={"db_table": "sky_object_details"},
        ),
    ]
