from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.shops.models import Shop

class User(AbstractUser):

    class Role(models.TextChoices):
        MANAGER = 'manager', 'Manager'
        EMPLOYEE = 'employee', 'Employee'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE
    )
    token_version = models.PositiveIntegerField(default=1)
    failed_device_login_count = models.PositiveIntegerField(default=0)
    is_blocked = models.BooleanField(default=False)
    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users"
    )

    def save(self, *args, **kwargs):
        if self.pk:
            old = User.objects.filter(pk=self.pk).first()

            if old and old.is_blocked and not self.is_blocked:
                self.failed_device_login_count = 0
                self.token_version += 1

        if not self.password.startswith("pbkdf2"):
            self.set_password(self.password)

        super().save(*args, **kwargs)