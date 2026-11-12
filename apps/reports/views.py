"""
Reports and Tear-Sheets Views.
Complies with Master Specification Section 23.
Provides centralized reporting hub, CSV export streaming, and print-ready executive tear-sheets.
"""
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponse
from django.shortcuts import redirect
from django.views import View
from django.views.generic import TemplateView

from apps.core.mixins import HTMXResponseMixin
from apps.reports.models import ExportFormat, GeneratedReport, ReportType
from services.reports.generator import ReportGenerator


class ReportCenterView(LoginRequiredMixin, HTMXResponseMixin, TemplateView):
    """
    Centralized Hub for generating research memos, CSV exports, and printable tear-sheets.
    """
    template_name = "reports/report_center.html"
    partial_template_name = "reports/partials/report_center_partial.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user

        recent_reports = GeneratedReport.objects.filter(user=user).order_by("-created_at")[:15]

        context["active_nav"] = "reports"
        context["report_types"] = ReportType.choices
        context["export_formats"] = ExportFormat.choices
        context["recent_reports"] = recent_reports
        return context


class ReportExportView(LoginRequiredMixin, View):
    """
    Executes report compilation and returns downloadable CSV stream or redirects to printable view.
    """
    def post(self, request, *args, **kwargs):
        user = request.user
        report_type = request.POST.get("report_type", ReportType.PORTFOLIO_TEARSHEET)
        export_format = request.POST.get("export_format", ExportFormat.CSV)
        symbol = request.POST.get("symbol", "").strip().upper()

        if export_format == ExportFormat.HTML_PRINT:
            query = f"?type={report_type}"
            if symbol:
                query += f"&symbol={symbol}"
            return redirect(f"/reports/print/{query}")

        # Default CSV export
        filename, csv_data, count = ReportGenerator.generate_csv(user=user, report_type=report_type, symbol=symbol)

        # Audit log the generation
        title = dict(ReportType.choices).get(report_type, "Research Export")
        GeneratedReport.objects.create(
            user=user,
            report_type=report_type,
            export_format=ExportFormat.CSV,
            title=title,
            parameters={"symbol": symbol} if symbol else {},
            report_metadata={
                "data_sources": "NSE India Bhavcopy, Jugaad-Data, Technical Analysis Engine",
                "assumptions": "STT/brokerage deducted; FIFO lot matching; INR denominations.",
            },
            record_count=count,
        )

        response = HttpResponse(csv_data, content_type="text/csv; charset=utf-8")
        response["Content-Disposition"] = f'attachment; filename="{filename}"'
        return response


class PrintableTearSheetView(LoginRequiredMixin, TemplateView):
    """
    Executive printable tear-sheet formatted with clean typography and print media CSS.
    """
    template_name = "reports/print_tearsheet.html"

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        user = self.request.user
        report_type = self.request.GET.get("type", ReportType.PORTFOLIO_TEARSHEET)
        symbol = self.request.GET.get("symbol", "").strip().upper()

        gen_context = ReportGenerator.get_printable_context(user=user, report_type=report_type, symbol=symbol)
        context.update(gen_context)

        # Audit log printable view
        GeneratedReport.objects.create(
            user=user,
            report_type=report_type,
            export_format=ExportFormat.HTML_PRINT,
            title=context["title"],
            parameters={"symbol": symbol} if symbol else {},
            report_metadata={"render_mode": "HTML_PRINT_MEDIA"},
            record_count=len(context.get("holdings", [])),
        )

        return context
