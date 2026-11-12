from django.urls import path

from apps.reports.views import (
    PrintableTearSheetView,
    ReportCenterView,
    ReportExportView,
)

app_name = "reports"

urlpatterns = [
    path("", ReportCenterView.as_view(), name="center"),
    path("export/", ReportExportView.as_view(), name="export"),
    path("print/", PrintableTearSheetView.as_view(), name="print_tearsheet"),
]

