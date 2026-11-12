import pytest
from django.test import Client
from django.urls import reverse


@pytest.mark.django_db
def test_dashboard_direct_url_full_shell():
    client = Client()
    response = client.get(reverse("dashboard:index"))
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    
    # Assert persistent shell elements exist on direct load
    assert "<!DOCTYPE html>" in content
    assert 'id="top-header"' in content
    assert 'id="sidebar"' in content
    assert 'id="main-content"' in content
    assert "INDIAN STOCK INTEL" in content
    assert "NIFTY 50" in content

@pytest.mark.django_db
def test_dashboard_htmx_partial_swap():
    client = Client()
    response = client.get(
        reverse("dashboard:index"),
        headers={"HX-Request": "true"}
    )
    assert response.status_code == 200
    content = response.content.decode("utf-8")
    
    # Assert partial response does NOT contain full shell wrappers
    assert "<!DOCTYPE html>" not in content
    assert 'id="sidebar"' not in content
    assert 'id="top-header"' not in content
    assert "Executive Dashboard" in content
    assert "Major Market Indices" in content

@pytest.mark.django_db
def test_market_overview_direct_and_htmx():
    client = Client()
    url = reverse("dashboard:market_overview")

    # 1. Direct request
    res_direct = client.get(url)
    assert res_direct.status_code == 200
    assert "<!DOCTYPE html>" in res_direct.content.decode("utf-8")
    assert "Broad Market Indices" in res_direct.content.decode("utf-8")

    # 2. HTMX request
    res_htmx = client.get(url, headers={"HX-Request": "true"})
    assert res_htmx.status_code == 200
    assert "<!DOCTYPE html>" not in res_htmx.content.decode("utf-8")
    assert "Broad Market Indices" in res_htmx.content.decode("utf-8")

@pytest.mark.django_db
def test_module_placeholders_direct_and_htmx():
    client = Client()
    modules_to_test = [
        "stock_analysis",
        "technical_analysis",
        "screener",
        "portfolio_overview",
        "swing_trading",
        "ai_stock_research",
        "data_sources",
    ]
    for mod in modules_to_test:
        url = reverse("dashboard:placeholder", kwargs={"module_name": mod})
        
        # Direct URL load
        res_direct = client.get(url)
        assert res_direct.status_code == 200
        assert "<!DOCTYPE html>" in res_direct.content.decode("utf-8")
        
        # HTMX partial load
        res_htmx = client.get(url, headers={"HX-Request": "true"})
        assert res_htmx.status_code == 200
        assert "<!DOCTYPE html>" not in res_htmx.content.decode("utf-8")
        assert mod.replace("_", " ").title() in res_htmx.content.decode("utf-8")

@pytest.mark.django_db
def test_custom_404_page():
    client = Client()
    response = client.get("/non-existent-route-9999/")
    assert response.status_code == 404
    assert "Resource Not Found" in response.content.decode("utf-8")
