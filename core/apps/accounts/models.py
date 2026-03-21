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

    shop = models.ForeignKey(
        Shop,
        on_delete=models.CASCADE,
        null=True,
        blank=True,
        related_name="users"
    )

    def save(self, *args, **kwargs):
        if not self.password.startswith("pbkdf2"):
            self.set_password(self.password)
        super().save(*args, **kwargs)