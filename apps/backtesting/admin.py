from django.contrib import admin

from apps.backtesting.models import BacktestRun, BacktestStrategy


@admin.register(BacktestStrategy)
class BacktestStrategyAdmin(admin.ModelAdmin):
    list_display = ("name", "strategy_type", "stop_loss_pct", "target_pct", "is_system_preset")
    list_filter = ("strategy_type", "is_system_preset")
    search_fields = ("name", "description")


@admin.register(BacktestRun)
class BacktestRunAdmin(admin.ModelAdmin):
    list_display = ("listing", "strategy", "user", "total_return_pct", "win_rate_pct", "total_trades", "created_at")
    list_filter = ("status", "strategy")
    search_fields = ("listing__symbol", "strategy__name", "user__username")
