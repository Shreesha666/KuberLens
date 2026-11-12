from django.urls import path

from apps.brokers.views import (
    BrokerCompleteOAuthView,
    BrokerDisconnectView,
    BrokerSaveCredentialsView,
    BrokerSettingsView,
    BrokerSyncNowView,
    DerivativesOverviewView,
)

app_name = "brokers"

urlpatterns = [
    path("", BrokerSettingsView.as_view(), name="settings"),
    path("credentials/", BrokerSaveCredentialsView.as_view(), name="save_credentials"),
    path("callback/", BrokerCompleteOAuthView.as_view(), name="complete_oauth"),
    path("sync/", BrokerSyncNowView.as_view(), name="sync_now"),
    path("disconnect/", BrokerDisconnectView.as_view(), name="disconnect"),
    path("derivatives/", DerivativesOverviewView.as_view(), name="derivatives"),
]

