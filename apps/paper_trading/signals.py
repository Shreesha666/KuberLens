from django.conf import settings
from django.db.models.signals import post_save
from django.dispatch import receiver

from apps.paper_trading.models import PaperAccount


@receiver(post_save, sender=settings.AUTH_USER_MODEL)
def create_user_paper_account(sender, instance, created, **kwargs):
    """
    Automatically provisions a default PaperAccount with ₹10,00,000 virtual balance
    when a new user registers in KuberLens.
    """
    if created:
        PaperAccount.objects.get_or_create(user=instance)

