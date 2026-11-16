import pytest
from django.test import Client, RequestFactory
from django.urls import reverse
from django.views.generic import TemplateView

from apps.core.encryption import decrypt_value, encrypt_value
from apps.core.mixins import HTMXResponseMixin
from apps.core.templatetags.core_tags import financial_color, format_inr, safe_markdown


@pytest.mark.django_db
def test_health_check_endpoint():
    client = Client()
    response = client.get(reverse("core:health_check"))
    assert response.status_code == 200
    data = response.json()
    assert data["status"] == "ok"
    assert data["database"] == "healthy"
    assert "timestamp_utc" in data

def test_fernet_encryption_roundtrip():
    secret = "kite_api_secret_12345!@#$%"
    encrypted = encrypt_value(secret)
    assert encrypted != secret
    assert isinstance(encrypted, str)
    decrypted = decrypt_value(encrypted)
    assert decrypted == secret

def test_fernet_tampered_ciphertext():
    with pytest.raises(ValueError, match="Invalid or corrupted ciphertext"):
        decrypt_value("corrupted_invalid_fernet_token")

def test_financial_color_filter():
    assert financial_color("+125.40") == "text-success"
    assert financial_color("-45.20") == "text-danger"
    assert financial_color("0.00") == "text-muted"
    assert financial_color(None) == "text-muted"
    assert financial_color("+1.5%") == "text-success"
    assert financial_color("-2.8%") == "text-danger"

def test_format_inr_filter():
    assert format_inr("24180.80") == "₹24,180.80"
    assert format_inr(1500000) == "₹1,500,000.00"
    assert format_inr(None) == "₹0.00"

class DummyHTMXView(HTMXResponseMixin, TemplateView):
    template_name = "dashboard/dashboard.html"
    partial_template_name = "dashboard/partials/dashboard_partial.html"

def test_htmx_response_mixin_dual_mode():
    factory = RequestFactory()
    
    # 1. Direct Browser Request (request.htmx == False)
    req_direct = factory.get("/test/")
    req_direct.htmx = False
    view_direct = DummyHTMXView()
    view_direct.setup(req_direct)
    assert view_direct.get_template_names() == ["dashboard/dashboard.html"]

    # 2. HTMX Request (request.htmx == True)
    req_htmx = factory.get("/test/", HTTP_HX_REQUEST="true")
    req_htmx.htmx = True
    view_htmx = DummyHTMXView()
    view_htmx.setup(req_htmx)
    assert view_htmx.get_template_names() == ["dashboard/partials/dashboard_partial.html"]


def test_safe_markdown_filter():
    raw = "**HGS (India)** leads with score of **57.8/100**.\n\n*Valuation Note*: Fair value."
    output = str(safe_markdown(raw))
    assert "<strong>HGS (India)</strong>" in output
    assert "<strong>57.8/100</strong>" in output
    assert "<em>Valuation Note</em>" in output
    assert "<p class='mb-2'>" in output
    assert "**" not in output
    assert safe_markdown("") == ""
    assert safe_markdown(None) == ""
