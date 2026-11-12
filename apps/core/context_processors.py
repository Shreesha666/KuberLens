
def shell_context(request):
    """
    Supplies context variables required by the persistent HTML application shell
    (Header, Ticker, Data Freshness status, and Navigation categories).
    """
    return {
        "platform_title": "Indian Stock Intelligence",
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
        "unread_notifications_count": 0,
    }
