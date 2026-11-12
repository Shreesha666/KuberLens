import logging

from django.db import connection
from django.http import JsonResponse
from django.utils import timezone
from django.views import View

logger = logging.getLogger(__name__)

class HealthCheckView(View):
    """
    Service health check endpoint reporting application and database status.
    """
    def get(self, request, *args, **kwargs):
        db_status = "healthy"
        try:
            with connection.cursor() as cursor:
                cursor.execute("SELECT 1;")
                cursor.fetchone()
        except Exception as e:
            logger.error("Database health check failed: %s", e)
            db_status = f"unhealthy: {e}"

        status_code = 200 if "unhealthy" not in db_status else 503
        return JsonResponse(
            {
                "status": "ok" if status_code == 200 else "degraded",
                "database": db_status,
                "timestamp_utc": timezone.now().isoformat(),
            },
            status=status_code,
        )

def custom_page_not_found(request, exception=None):
    from django.shortcuts import render
    return render(request, "errors/404.html", status=404)

def custom_server_error(request):
    from django.shortcuts import render
    return render(request, "errors/500.html", status=500)
