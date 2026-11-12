"""
Broker Integration Models.
Complies with Master Specification Section 22 and Architecture 2.1.
Enforces AES/Fernet encryption for all stored broker API secrets and access tokens.
Strictly research-only; no automated order placement endpoints exist.
"""
from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.encryption import decrypt_value, encrypt_value
from apps.core.models import AuditedModel


class BrokerName(models.TextChoices):
    ZERODHA = "ZERODHA", "Zerodha Kite Connect"


class ConnectionStatus(models.TextChoices):
    DISCONNECTED = "DISCONNECTED", "Disconnected"
    CONNECTED = "CONNECTED", "Connected (Active)"
    EXPIRED = "EXPIRED", "Session Expired (Re-authentication Required)"
    ERROR = "ERROR", "Authentication Error"


class BrokerConnection(AuditedModel):
    """
    Secure connection profile for broker account synchronization.
    API secrets and access tokens are strictly stored as encrypted ciphertexts.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="broker_connections",
    )
    broker_name = models.CharField(
        max_length=50,
        choices=BrokerName.choices,
        default=BrokerName.ZERODHA,
        db_index=True,
    )
    api_key = models.CharField(
        max_length=100,
        help_text="Broker API Key (publicly safe identifier).",
    )
    api_secret_encrypted = models.TextField(
        blank=True,
        help_text="Fernet-encrypted broker API secret.",
    )
    request_token = models.CharField(
        max_length=150,
        blank=True,
        help_text="Daily ephemeral OAuth request token from broker login callback.",
    )
    access_token_encrypted = models.TextField(
        blank=True,
        help_text="Fernet-encrypted broker session access token.",
    )
    public_token = models.CharField(
        max_length=150,
        blank=True,
        help_text="Public websocket token for market stream connection.",
    )
    token_expires_at = models.DateTimeField(
        null=True,
        blank=True,
        db_index=True,
        help_text="Kite access tokens expire daily at ~06:00 AM IST.",
    )
    status = models.CharField(
        max_length=30,
        choices=ConnectionStatus.choices,
        default=ConnectionStatus.DISCONNECTED,
        db_index=True,
    )
    is_active = models.BooleanField(
        default=False,
        db_index=True,
    )
    last_synced_at = models.DateTimeField(
        null=True,
        blank=True,
    )
    sync_summary = models.JSONField(
        default=dict,
        blank=True,
        help_text="Audit details of the most recent holdings sync.",
    )

    class Meta:
        ordering = ["-updated_at"]
        verbose_name = "Broker Connection"
        verbose_name_plural = "Broker Connections"
        constraints = [
            models.UniqueConstraint(
                fields=["user", "broker_name"],
                name="unique_user_broker_connection",
            )
        ]

    def __str__(self) -> str:
        return f"{self.user.username} - {self.get_broker_name_display()} [{self.status}]"

    def set_api_secret(self, secret_plaintext: str) -> None:
        """
        Encrypts and stores the broker API secret.
        """
        if secret_plaintext:
            self.api_secret_encrypted = encrypt_value(secret_plaintext.strip())
        else:
            self.api_secret_encrypted = ""

    def get_api_secret(self) -> str:
        """
        Decrypts and returns the plaintext broker API secret.
        """
        if not self.api_secret_encrypted:
            return ""
        return decrypt_value(self.api_secret_encrypted)

    def set_access_token(self, token_plaintext: str) -> None:
        """
        Encrypts and stores the active session access token.
        """
        if token_plaintext:
            self.access_token_encrypted = encrypt_value(token_plaintext.strip())
        else:
            self.access_token_encrypted = ""

    def get_access_token(self) -> str:
        """
        Decrypts and returns the plaintext access token.
        """
        if not self.access_token_encrypted:
            return ""
        return decrypt_value(self.access_token_encrypted)

    def is_token_valid(self) -> bool:
        """
        Returns True if connection is marked CONNECTED and session has not expired.
        """
        if self.status != ConnectionStatus.CONNECTED or not self.access_token_encrypted:
            return False
        if self.token_expires_at and self.token_expires_at <= timezone.now():
            return False
        return True

