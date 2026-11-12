import logging
from decimal import Decimal

from django.contrib import messages
from django.contrib.auth.mixins import LoginRequiredMixin
from django.http import HttpResponseRedirect
from django.shortcuts import get_object_or_404, redirect
from django.urls import reverse
from django.views import View
from django.views.generic import ListView

from apps.core.mixins import HTMXResponseMixin
from apps.instruments.models import ExchangeListing
from apps.market.models import MarketQuote
from apps.technical_analysis.models import TechnicalIndicatorSnapshot
from apps.watchlists.models import Watchlist, WatchlistItem

logger = logging.getLogger(__name__)


class WatchlistListView(LoginRequiredMixin, HTMXResponseMixin, ListView):
    """
    Main watchlists hub view showing all user watchlists and items in the active watchlist.
    """
    model = Watchlist
    template_name = "watchlists/watchlist_list.html"
    partial_template_name = "watchlists/partials/watchlist_list_partial.html"
    context_object_name = "watchlists"
    active_nav = "watchlists"

    def get_queryset(self):
        return Watchlist.objects.filter(user=self.request.user).order_by("-is_default", "name")

    def get_context_data(self, **kwargs):
        context = super().get_context_data(**kwargs)
        context["page_title"] = "My Watchlists & Tracking"
        watchlists = list(context["watchlists"])

        # Ensure at least one default watchlist exists
        if not watchlists:
            default_wl = Watchlist.objects.create(
                user=self.request.user,
                name="Primary Watchlist",
                description="Core tracking watchlist",
                is_default=True,
            )
            watchlists = [default_wl]
            context["watchlists"] = watchlists

        active_id = self.request.GET.get("watchlist_id")
        active_wl = None
        if active_id:
            active_wl = next((w for w in watchlists if str(w.id) == active_id), None)
        if not active_wl:
            active_wl = watchlists[0]

        context["active_watchlist"] = active_wl

        # Fetch items for active watchlist with latest quote & technical signal
        items = list(
            WatchlistItem.objects.filter(watchlist=active_wl)
            .select_related("listing__instrument", "listing__exchange")
            .order_by("sort_order", "-created_at")
        )

        listing_ids = [item.listing_id for item in items]
        latest_quotes = {}
        for q in MarketQuote.objects.filter(listing_id__in=listing_ids).order_by("-retrieved_at"):
            lid = str(q.listing_id)
            if lid not in latest_quotes:
                latest_quotes[lid] = q

        latest_tech = {}
        for t in TechnicalIndicatorSnapshot.objects.filter(listing_id__in=listing_ids).order_by("-timestamp"):
            lid = str(t.listing_id)
            if lid not in latest_tech:
                latest_tech[lid] = t

        for item in items:
            q = latest_quotes.get(str(item.listing_id))
            t = latest_tech.get(str(item.listing_id))
            item.quote = q
            item.tech = t

            cur_price = q.price if q else item.added_price
            if item.added_price > Decimal("0.00"):
                diff = cur_price - item.added_price
                pct = (diff / item.added_price) * Decimal("100.0")
                item.gain_since_added = diff
                item.gain_pct_since_added = pct
            else:
                item.gain_since_added = Decimal("0.00")
                item.gain_pct_since_added = Decimal("0.00")

        context["items"] = items
        return context


class WatchlistCreateView(LoginRequiredMixin, View):
    """
    Creates a new user watchlist.
    """
    def post(self, request, *args, **kwargs):
        name = request.POST.get("name", "").strip()
        description = request.POST.get("description", "").strip()

        if not name:
            messages.error(request, "Watchlist name is required.")
            return redirect("watchlists:list")

        wl, created = Watchlist.objects.get_or_create(
            user=request.user,
            name=name,
            defaults={"description": description},
        )
        if created:
            messages.success(request, f"Created watchlist '{wl.name}'.")
        else:
            messages.info(request, f"Watchlist '{wl.name}' already exists.")

        redirect_url = f"{reverse('watchlists:list')}?watchlist_id={wl.id}"
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)


class WatchlistDeleteView(LoginRequiredMixin, View):
    """
    Deletes a user watchlist.
    """
    def post(self, request, pk, *args, **kwargs):
        wl = get_object_or_404(Watchlist, id=pk, user=request.user)
        name = wl.name
        wl.delete()
        messages.success(request, f"Deleted watchlist '{name}'.")

        redirect_url = reverse("watchlists:list")
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)


class WatchlistItemAddView(LoginRequiredMixin, View):
    """
    Adds a stock to a specific watchlist with target price and notes.
    """
    def post(self, request, pk, *args, **kwargs):
        wl = get_object_or_404(Watchlist, id=pk, user=request.user)
        symbol = request.POST.get("symbol", "").strip().upper()
        target_str = request.POST.get("target_price")
        stop_str = request.POST.get("stop_loss")
        notes = request.POST.get("notes", "").strip()

        listing = get_object_or_404(ExchangeListing, symbol=symbol, is_tradeable=True)

        latest_quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
        cur_price = latest_quote.price if latest_quote else Decimal("0.00")

        target_val = Decimal(target_str) if target_str else None
        stop_val = Decimal(stop_str) if stop_str else None

        item, created = WatchlistItem.objects.get_or_create(
            watchlist=wl,
            listing=listing,
            defaults={
                "added_price": cur_price,
                "target_price": target_val,
                "stop_loss": stop_val,
                "notes": notes,
            },
        )
        if not created:
            if target_val is not None:
                item.target_price = target_val
            if stop_val is not None:
                item.stop_loss = stop_val
            if notes:
                item.notes = notes
            item.save()
            messages.info(request, f"Updated {listing.symbol} in '{wl.name}'.")
        else:
            messages.success(request, f"Added {listing.symbol} to '{wl.name}'.")

        redirect_url = f"{reverse('watchlists:list')}?watchlist_id={wl.id}"
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)


class WatchlistItemDeleteView(LoginRequiredMixin, View):
    """
    Removes a stock from a watchlist.
    """
    def post(self, request, pk, *args, **kwargs):
        item = get_object_or_404(WatchlistItem, id=pk, watchlist__user=request.user)
        wl_id = item.watchlist.id
        symbol = item.listing.symbol
        item.delete()
        messages.success(request, f"Removed {symbol} from watchlist.")

        redirect_url = f"{reverse('watchlists:list')}?watchlist_id={wl_id}"
        if request.htmx:
            resp = HttpResponseRedirect(redirect_url)
            resp["HX-Redirect"] = redirect_url
            return resp
        return redirect(redirect_url)


class WatchlistQuickAddView(LoginRequiredMixin, View):
    """
    Modal/Dropdown endpoint to quickly add a stock to any watchlist from the screener or stock detail view.
    """
    def post(self, request, *args, **kwargs):
        symbol = request.POST.get("symbol", "").strip().upper()
        watchlist_id = request.POST.get("watchlist_id")
        notes = request.POST.get("notes", "").strip()

        listing = get_object_or_404(ExchangeListing, symbol=symbol, is_tradeable=True)

        if watchlist_id:
            wl = get_object_or_404(Watchlist, id=watchlist_id, user=request.user)
        else:
            wl, _ = Watchlist.objects.get_or_create(
                user=request.user,
                is_default=True,
                defaults={"name": "Primary Watchlist"},
            )

        latest_quote = MarketQuote.objects.filter(listing=listing).order_by("-retrieved_at").first()
        cur_price = latest_quote.price if latest_quote else Decimal("0.00")

        item, created = WatchlistItem.objects.get_or_create(
            watchlist=wl,
            listing=listing,
            defaults={
                "added_price": cur_price,
                "notes": notes,
            },
        )
        if created:
            messages.success(request, f"Added {symbol} to watchlist '{wl.name}'.")
        else:
            messages.info(request, f"{symbol} is already in '{wl.name}'.")

        next_url = request.POST.get("next") or reverse("watchlists:list")
        if request.htmx:
            resp = HttpResponseRedirect(next_url)
            resp["HX-Redirect"] = next_url
            return resp
        return redirect(next_url)
