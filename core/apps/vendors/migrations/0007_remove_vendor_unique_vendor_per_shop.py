from django.db import migrations


class Migration(migrations.Migration):
    dependencies = [
        ("vendors", "0006_alter_stockentry_paid_amount"),
    ]

    operations = [
        migrations.RemoveConstraint(
            model_name="vendor",
            name="unique_vendor_per_shop",
        ),
    ]
