import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


class CustomUser(AbstractUser):
    """
    Primary custom user model implemented before initial database migrations.
    Uses UUID primary key and stores Indian investor profile attributes.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    phone_number = models.CharField(max_length=20, blank=True, null=True)
    preferred_timezone = models.CharField(max_length=50, default="Asia/Kolkata")
    is_verified = models.BooleanField(default=False)

    class Meta:
        db_table = "accounts_user"
        ordering = ["username"]

    def __str__(self):
        return self.username

    def get_preference(self):
        pref, _ = UserPreference.objects.get_or_create(user=self)
        return pref

class UserPreference(models.Model):
    """
    Stores user preferences including theme and alerting preferences.
    """
    THEME_CHOICES = [
        ("light", "Clean Light Theme"),
        ("dark", "Financial Dark Theme"),
    ]

    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name="preference"
    )
    theme = models.CharField(max_length=10, choices=THEME_CHOICES, default="light")
    default_chart_interval = models.CharField(max_length=10, default="1d")
    email_alerts_enabled = models.BooleanField(default=True)
    in_app_alerts_enabled = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        db_table = "accounts_user_preference"

    def __str__(self):
        return f"Preferences for {self.user.username}"
