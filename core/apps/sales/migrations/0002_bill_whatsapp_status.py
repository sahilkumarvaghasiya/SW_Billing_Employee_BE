from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ("sales", "0001_initial"),
    ]

    operations = [
        migrations.AddField(
            model_name="bill",
            name="whatsapp_status",
            field=models.CharField(
                choices=[
                    ("pending", "Pending"),
                    ("sent", "Sent"),
                    ("failed", "Failed"),
                ],
                default="pending",
                max_length=10,
            ),
        ),
        migrations.AddIndex(
            model_name="bill",
            index=models.Index(
                fields=["whatsapp_status"],
                name="billing_bil_whatsap_0a8f2d_idx",
            ),
        ),
    ]
