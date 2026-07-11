from decimal import Decimal

from django.db import migrations, models


def backfill_original_price(apps, schema_editor):
    """Fill original_price = price for existing rows where it is still 0."""
    BillItem = apps.get_model("sales", "BillItem")
    for item in BillItem.objects.all().iterator():
        item.original_price = item.price
        item.save(update_fields=["original_price"])


class Migration(migrations.Migration):

    dependencies = [
        (
            "sales",
            "0003_rename_billing_bil_whatsap_0a8f2d_idx_billing_bil_whatsap_146f99_idx",
        ),
    ]

    operations = [
        migrations.AddField(
            model_name="billitem",
            name="original_price",
            field=models.DecimalField(
                decimal_places=2,
                default=Decimal("0.00"),
                max_digits=10,
            ),
        ),
        migrations.RunPython(backfill_original_price, migrations.RunPython.noop),
    ]
