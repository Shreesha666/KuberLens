from django.contrib import admin

from apps.brokers.models import BrokerConnection
from apps.market.models import DerivativeContract


@admin.register(BrokerConnection)
class BrokerConnectionAdmin(admin.ModelAdmin):
    list_display = ["user", "broker_name", "status", "is_active", "token_expires_at", "last_synced_at"]
    list_filter = ["broker_name", "status", "is_active"]
    search_fields = ["user__username", "user__email", "api_key"]
    readonly_fields = ["created_at", "updated_at", "last_synced_at"]


@admin.register(DerivativeContract)
class DerivativeContractAdmin(admin.ModelAdmin):
    list_display = ["trading_symbol", "underlying_listing", "contract_type", "option_type", "strike_price", "expiry_date", "lot_size", "open_interest"]
    list_filter = ["contract_type", "option_type", "expiry_date", "is_active"]
    search_fields = ["trading_symbol", "underlying_listing__symbol"]
    ordering = ["expiry_date", "strike_price"]

