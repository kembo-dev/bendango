from django.db import migrations, models


KNOWN_RETAILERS = {
    "drcmart.com": (0.95, "verified"),
    "mobile-rdc.com": (0.92, "verified"),
}


def seed_retailer_trust(apps, schema_editor):
    Retailer = apps.get_model("tracker", "Retailer")
    for retailer in Retailer.objects.all():
        base_url = (retailer.base_url or "").lower()
        matched = next((value for host, value in KNOWN_RETAILERS.items() if host in base_url), None)
        if matched:
            retailer.trust_score, retailer.trust_level = matched
        else:
            retailer.trust_score, retailer.trust_level = 0.60, "standard"
        retailer.save(update_fields=["trust_score", "trust_level"])


class Migration(migrations.Migration):
    dependencies = [("tracker", "0005_pricelisting_extraction_source_match_score")]

    operations = [
        migrations.AddField(
            model_name="retailer",
            name="trust_score",
            field=models.DecimalField(decimal_places=4, default=0.60, max_digits=5),
        ),
        migrations.AddField(
            model_name="retailer",
            name="trust_level",
            field=models.CharField(
                choices=[("verified", "Vérifié"), ("trusted", "Fiable"), ("standard", "Standard"), ("limited", "À confirmer")],
                default="standard",
                max_length=20,
            ),
        ),
        migrations.RunPython(seed_retailer_trust, migrations.RunPython.noop),
        migrations.AlterField(
            model_name="pricelisting",
            name="extraction_source",
            field=models.CharField(
                choices=[("jsonld", "JSON-LD"), ("shopify", "Shopify JSON"), ("meta", "Meta tags"), ("llm", "LLM"), ("html", "HTML fallback"), ("cache", "Cached listing"), ("unknown", "Unknown")],
                default="unknown",
                max_length=20,
            ),
        ),
    ]
