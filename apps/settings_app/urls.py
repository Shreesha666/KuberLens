from django.urls import path

from .views import DataSourcesView

app_name = "settings_app"

urlpatterns = [
    path("data-sources/", DataSourcesView.as_view(), name="data_sources"),
]
