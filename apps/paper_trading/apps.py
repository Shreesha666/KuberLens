from django.apps import AppConfig


class PaperTradingConfig(AppConfig):
    default_auto_field = "django.db.models.BigAutoField"
    name = "apps.paper_trading"
    verbose_name = "Paper Trading Simulation"

    def ready(self):
        import apps.paper_trading.signals  # noqa: F401

