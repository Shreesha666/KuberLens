"""
Tests for Watchlists Module.
Verifies watchlist creation, item tracking, target prices, notes,
quick adding from any page, item removal, and HTMX dual-mode views.
"""
from decimal import Decimal

import pytest
from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone

from apps.instruments.models import Exchange, ExchangeListing, Instrument
from apps.market.models import MarketQuote
from apps.watchlists.models import Watchlist, WatchlistItem

User = get_user_model()


@pytest.fixture
def wl_data(db, client):
    user = User.objects.create_user(
        username="wl_user",
        email="wl@example.com",
        password="password123",
    )
    exchange = Exchange.objects.create(code="NSE", name="NSE")
    inst = Instrument.objects.create(
        isin="INE002A01018",
        display_name="Reliance Industries",
        legal_name="Reliance Industries Limited",
        sector="Energy",
    )
    listing = ExchangeListing.objects.create(instrument=inst, exchange=exchange, symbol="RELIANCE", is_tradeable=True)

    now = timezone.now()
    MarketQuote.objects.create(
        listing=listing,
        price=Decimal("2800.00"),
        open=Decimal("2750.00"),
        high=Decimal("2820.00"),
        low=Decimal("2740.00"),
        close=Decimal("2800.00"),
        previous_close=Decimal("2750.00"),
        change=Decimal("50.00"),
        change_percent=Decimal("1.82"),
        volume=1000000,
        source_provider="YAHOO",
        source_type="DELAYED",
        freshness_status="FRESH",
        source_timestamp=now,
        retrieved_at=now,
    )

    wl = Watchlist.objects.create(
        user=user,
        name="Long-Term Core",
        description="High conviction leaders",
        is_default=True,
    )

    client.force_login(user)
    return {
        "user": user,
        "listing": listing,
        "watchlist": wl,
        "client": client,
    }


@pytest.mark.django_db
class TestWatchlists:
    def test_watchlist_list_full_and_htmx(self, wl_data):
        client = wl_data["client"]
        url = reverse("watchlists:list")

        # Full page
        resp_full = client.get(url)
        assert resp_full.status_code == 200
        assert "watchlists/watchlist_list.html" in [t.name for t in resp_full.templates]
        assert "Long-Term Core" in resp_full.content.decode()

        # HTMX partial
        resp_htmx = client.get(url, HTTP_HX_REQUEST="true")
        assert resp_htmx.status_code == 200
        assert "watchlists/partials/watchlist_list_partial.html" in [t.name for t in resp_htmx.templates]
        assert "<!DOCTYPE html>" not in resp_htmx.content.decode()

    def test_create_and_delete_watchlist(self, wl_data):
        client = wl_data["client"]
        user = wl_data["user"]
        add_url = reverse("watchlists:add_watchlist")

        # Create
        resp = client.post(add_url, data={"name": "Breakout Setups", "description": "Near 52W High"})
        assert resp.status_code == 302
        new_wl = Watchlist.objects.filter(user=user, name="Breakout Setups").first()
        assert new_wl is not None

        # Delete
        del_url = reverse("watchlists:delete_watchlist", kwargs={"pk": new_wl.id})
        del_resp = client.post(del_url)
        assert del_resp.status_code == 302
        assert not Watchlist.objects.filter(id=new_wl.id).exists()

    def test_add_and_remove_item(self, wl_data):
        client = wl_data["client"]
        wl = wl_data["watchlist"]
        listing = wl_data["listing"]
        add_item_url = reverse("watchlists:add_item", kwargs={"pk": wl.id})

        post_data = {
            "symbol": listing.symbol,
            "target_price": "3100.00",
            "stop_loss": "2600.00",
            "notes": "Buy on support pullback",
        }

        # Add item
        resp = client.post(add_item_url, data=post_data)
        assert resp.status_code == 302

        item = WatchlistItem.objects.filter(watchlist=wl, listing=listing).first()
        assert item is not None
        assert item.target_price == Decimal("3100.00")
        assert item.stop_loss == Decimal("2600.00")
        assert item.added_price == Decimal("2800.00")

        # Delete item
        del_item_url = reverse("watchlists:delete_item", kwargs={"pk": item.id})
        del_resp = client.post(del_item_url)
        assert del_resp.status_code == 302
        assert not WatchlistItem.objects.filter(id=item.id).exists()

    def test_quick_add_endpoint(self, wl_data):
        client = wl_data["client"]
        wl = wl_data["watchlist"]
        listing = wl_data["listing"]
        quick_url = reverse("watchlists:quick_add")

        resp = client.post(
            quick_url,
            data={
                "symbol": listing.symbol,
                "watchlist_id": str(wl.id),
                "notes": "Quick added from screener",
            },
        )
        assert resp.status_code == 302
        assert WatchlistItem.objects.filter(watchlist=wl, listing=listing).exists()

    def test_unauthenticated_user_redirect(self, client):
        client.logout()
        resp = client.get(reverse("watchlists:list"))
        assert resp.status_code == 302
        assert "/accounts/login/" in resp["Location"]
