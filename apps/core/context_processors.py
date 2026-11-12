
def shell_context(request):
    """
    Supplies context variables required by the persistent HTML application shell
    (Header, Ticker, Data Freshness status, and Navigation categories).
    """
    current_theme = "light"
    unread_notifs = 0
    if hasattr(request, "user") and request.user.is_authenticated:
        pref = getattr(request.user, "preference", None) or request.user.get_preference()
        current_theme = pref.theme
        try:
            from apps.notifications.models import Notification
            unread_notifs = Notification.objects.filter(user=request.user, is_read=False).count()
        except Exception:
            unread_notifs = 0

    return {
        "platform_title": "KuberLens",
        "current_theme": current_theme,
        "market_status": {
            "is_open": False,
            "session_name": "Post-Market",
            "exchange": "NSE",
        },
        "market_ticker": [
            {
                "symbol": "NIFTY 50",
                "price": "24,180.80",
                "change": "+142.30",
                "change_percent": "+0.59%",
                "is_positive": True,
            },
            {
                "symbol": "SENSEX",
                "price": "79,480.20",
                "change": "+450.15",
                "change_percent": "+0.57%",
                "is_positive": True,
            },
            {
                "symbol": "NIFTY BANK",
                "price": "51,215.40",
                "change": "-85.60",
                "change_percent": "-0.17%",
                "is_positive": False,
            },
        ],
        "data_freshness": {
            "source_type": "EOD",
            "freshness_status": "FRESH",
            "label": "Settled EOD (NSE)",
            "css_class": "badge-soft-success",
        },
        "unread_notifications_count": unread_notifs,
    }
