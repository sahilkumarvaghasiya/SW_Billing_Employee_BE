from django.contrib.auth.hashers import identify_hasher
from django.contrib.auth.models import AbstractUser
from django.db import models
from apps.shops.models import Shop


def _is_password_hashed(raw_value):
    """True if the value is already a hashed password (any configured hasher)."""
    if not raw_value:
        return False
    try:
        identify_hasher(raw_value)
        return True
    except ValueError:
        return False

class User(AbstractUser):

    class Role(models.TextChoices):
        MANAGER = 'manager', 'Manager'
        EMPLOYEE = 'employee', 'Employee'

    role = models.CharField(
        max_length=20,
        choices=Role.choices,
        default=Role.EMPLOYEE
    )
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    token_version = models.PositiveIntegerField(default=1)
    failed_device_login_count = models.PositiveIntegerField(default=0)
    is_blocked = models.BooleanField(default=False)
    feature_access = models.JSONField(default=dict, blank=True)
    session_active = models.BooleanField(default=False)
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

            if old:
                if not old.is_blocked and self.is_blocked:
                    self.session_active = False
                    self.token_version += 1

                if old.is_blocked and not self.is_blocked:
                    self.failed_device_login_count = 0
                    self.session_active = False
                    self.token_version += 1

        # Auto-hash only when a raw (unhashed) password was assigned directly.
        # Using identify_hasher avoids double-hashing an already-hashed value
        # regardless of which hasher produced it (pbkdf2, argon2, bcrypt, ...).
        if not _is_password_hashed(self.password):
            self.set_password(self.password)

        super().save(*args, **kwargs)