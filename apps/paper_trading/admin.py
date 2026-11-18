from django.contrib import admin

from apps.paper_trading.models import PaperAccount, PaperOrder, PaperPosition, PaperTrade


@admin.register(PaperAccount)
class PaperAccountAdmin(admin.ModelAdmin):
    list_display = ["user", "cash_balance", "margin_utilized", "realized_pnl", "is_active", "created_at"]
    search_fields = ["user__username", "user__email"]
    list_filter = ["is_active"]


@admin.register(PaperOrder)
class PaperOrderAdmin(admin.ModelAdmin):
    list_display = ["account", "listing", "order_side", "product_type", "order_type", "quantity", "status", "created_at"]
    search_fields = ["listing__symbol", "account__user__username"]
    list_filter = ["order_side", "product_type", "order_type", "status"]


@admin.register(PaperPosition)
class PaperPositionAdmin(admin.ModelAdmin):
    list_display = ["account", "listing", "product_type", "quantity", "average_price", "current_price", "unrealized_pnl"]
    search_fields = ["listing__symbol", "account__user__username"]
    list_filter = ["product_type"]


@admin.register(PaperTrade)
class PaperTradeAdmin(admin.ModelAdmin):
    list_display = ["account", "listing", "trade_side", "product_type", "quantity", "execution_price", "total_charges", "executed_at"]
    search_fields = ["listing__symbol", "account__user__username"]
    list_filter = ["trade_side", "product_type"]

