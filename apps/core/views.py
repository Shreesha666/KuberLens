import logging
import mimetypes
import os

from django.conf import settings
from django.contrib.auth.decorators import login_required
from django.db import connection
from django.http import FileResponse, Http404, HttpResponseRedirect, JsonResponse
from django.utils import timezone
from django.utils._os import safe_join
from django.views import View

logger = logging.getLogger(__name__)

DOCS_DIR = os.path.abspath(settings.BASE_DIR / "site")


@login_required
def serve_help_docs(request, path=""):
    """
    Serves the KuberLens V1.0 MkDocs User Guide directly under /help/ within Django.
    Features:
      - Path traversal security via safe_join.
      - Trailing slash redirection for directory URLs to maintain relative asset resolution.
      - Exact MIME type resolution for CSS, JS, SVG, JSON (search index), and images.
      - Preserves client-side MkDocs search, navigation, and responsiveness.
      - Authentication enforcement to protect application documentation.
    """
    clean_path = path.strip("/")
    try:
        target_path = safe_join(DOCS_DIR, clean_path)
    except Exception as e:
        logger.warning("Blocked potential unsafe path in documentation: %s (error: %s)", path, e)
        raise Http404("Invalid documentation path.")

    # If the target path is a directory, resolve index.html
    if os.path.isdir(target_path):
        index_file = os.path.join(target_path, "index.html")
        if os.path.isfile(index_file):
            if path and not path.endswith("/"):
                return HttpResponseRedirect(f"/help/{clean_path}/")
            target_path = index_file
        else:
            raise Http404("Documentation section not found.")

    if not os.path.isfile(target_path):
        raise Http404("Documentation asset not found.")

    # Resolve accurate MIME types
    content_type, encoding = mimetypes.guess_type(target_path)
    if target_path.endswith(".css"):
        content_type = "text/css"
    elif target_path.endswith(".js"):
        content_type = "application/javascript"
    elif target_path.endswith(".json"):
        content_type = "application/json"
    elif target_path.endswith(".svg"):
        content_type = "image/svg+xml"
    elif target_path.endswith(".woff2"):
        content_type = "font/woff2"
    elif target_path.endswith(".png"):
        content_type = "image/png"
    elif target_path.endswith(".jpg") or target_path.endswith(".jpeg"):
        content_type = "image/jpeg"
    elif not content_type:
        content_type = "text/html"

    response = FileResponse(open(target_path, "rb"), content_type=content_type)
    if encoding:
        response["Content-Encoding"] = encoding

    if target_path.endswith(".html"):
        response["Cache-Control"] = "no-cache, must-revalidate"
    else:
        response["Cache-Control"] = "public, max-age=86400"

    return response

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
