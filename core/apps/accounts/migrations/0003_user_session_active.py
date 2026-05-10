from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0002_user_failed_device_login_count_user_is_blocked_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='user',
            name='session_active',
            field=models.BooleanField(default=False),
        ),
    ]
