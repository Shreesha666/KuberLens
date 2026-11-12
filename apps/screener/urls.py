from django.urls import path

from apps.screener.views import (
    ScreenerDeleteConfigView,
    ScreenerExportView,
    ScreenerView,
)

app_name = "screener"

urlpatterns = [
    path("", ScreenerView.as_view(), name="index"),
    path("export/", ScreenerExportView.as_view(), name="export"),
    path("configs/<uuid:pk>/delete/", ScreenerDeleteConfigView.as_view(), name="delete_config"),
]
