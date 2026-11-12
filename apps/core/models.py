import uuid

from django.db import models


class AuditedModel(models.Model):
    """
    Abstract base model providing UUID primary key, creation,
    and modification timestamps for all domain entities.
    """
    id = models.UUIDField(primary_key=True, default=uuid.uuid4, editable=False)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)
    updated_at = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True
        ordering = ["-created_at"]
