from django.urls import path

from apps.watchlists.views import (
    WatchlistCreateView,
    WatchlistDeleteView,
    WatchlistItemAddView,
    WatchlistItemDeleteView,
    WatchlistListView,
    WatchlistQuickAddView,
)

app_name = "watchlists"

urlpatterns = [
    path("", WatchlistListView.as_view(), name="list"),
    path("add/", WatchlistCreateView.as_view(), name="add_watchlist"),
    path("<uuid:pk>/delete/", WatchlistDeleteView.as_view(), name="delete_watchlist"),
    path("<uuid:pk>/items/add/", WatchlistItemAddView.as_view(), name="add_item"),
    path("items/<uuid:pk>/delete/", WatchlistItemDeleteView.as_view(), name="delete_item"),
    path("quick-add/", WatchlistQuickAddView.as_view(), name="quick_add"),
]
