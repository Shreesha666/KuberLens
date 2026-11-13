"""
IPO Lifecycle Domain Logic.
Handles deterministic milestone tracking, timeline step resolution,
and status synchronization.
"""
from datetime import date
from typing import Any

from django.utils import timezone


def get_status_badge_class(status: str) -> str:
    """Returns consistent Bootstrap badge classes for IPO status pills."""
    mapping = {
        "LIVE": "bg-success text-white animate-pulse",
        "UPCOMING": "bg-primary-subtle text-primary border border-primary-subtle",
        "CLOSED": "bg-secondary-subtle text-secondary border",
        "ALLOTMENT_FINALIZED": "bg-info-subtle text-info-emphasis border border-info-subtle",
        "LISTED": "bg-dark text-white",
        "DRHP_FILED": "bg-warning-subtle text-warning-emphasis border border-warning-subtle",
        "SEBI_APPROVED": "bg-info-subtle text-info border border-info-subtle",
        "WITHDRAWN": "bg-danger-subtle text-danger border border-danger-subtle",
        "CANCELLED": "bg-danger text-white",
        "POSTPONED": "bg-warning text-dark",
    }
    return mapping.get(status, "bg-light text-secondary border")


def get_timeline_milestones(ipo: Any) -> list[dict[str, Any]]:
    """
    Computes an ordered timeline with completion status for UI step rendering.
    """
    today: date = timezone.now().date()
    steps = [
        {
            "key": "drhp",
            "name": "DRHP / RHP",
            "date": ipo.rhp_date or ipo.drhp_date,
            "status": "COMPLETED" if (ipo.rhp_date or ipo.drhp_date) else "PENDING",
        },
        {
            "key": "open",
            "name": "Issue Opens",
            "date": ipo.open_date,
            "status": "COMPLETED" if (ipo.open_date and today > ipo.open_date)
                      else ("CURRENT" if (ipo.open_date and today == ipo.open_date) else "UPCOMING"),
        },
        {
            "key": "close",
            "name": "Issue Closes",
            "date": ipo.close_date,
            "status": "COMPLETED" if (ipo.close_date and today > ipo.close_date)
                      else ("CURRENT" if (ipo.close_date and today == ipo.close_date) else "UPCOMING"),
        },
        {
            "key": "allotment",
            "name": "Basis of Allotment",
            "date": ipo.allotment_date,
            "status": "COMPLETED" if (ipo.allotment_date and today > ipo.allotment_date)
                      else ("CURRENT" if (ipo.allotment_date and today == ipo.allotment_date) else "UPCOMING"),
        },
        {
            "key": "listing",
            "name": "Listing on Exchanges",
            "date": ipo.listing_date,
            "status": "COMPLETED" if (ipo.listing_date and today >= ipo.listing_date)
                      else ("CURRENT" if (ipo.listing_date and today == ipo.listing_date) else "UPCOMING"),
        },
    ]
    return steps

