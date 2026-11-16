"""
IPO Lifecycle Domain Logic.
Handles deterministic milestone tracking, timeline step resolution,
and status synchronization.
"""
from datetime import date, timedelta
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
    Adheres to SEBI (ICDR) regulations: an IPO cannot open for bidding without
    a filed and approved RHP/DRHP.
    """
    today: date = timezone.now().date()

    # Determine DRHP/RHP status & display date
    drhp_date = ipo.rhp_date or ipo.drhp_date
    has_opened_or_listed = ipo.status in [
        "LIVE", "CLOSED", "ALLOTMENT_FINALIZED", "LISTED"
    ] or (ipo.open_date and today >= ipo.open_date)

    if drhp_date:
        drhp_status = "COMPLETED"
        drhp_display = drhp_date.strftime("%d %b %Y")
    elif has_opened_or_listed:
        # Statutory requirement: RHP must be filed and approved prior to issue opening
        drhp_status = "COMPLETED"
        if ipo.open_date:
            inferred_rhp = ipo.open_date - timedelta(days=5)
            drhp_display = inferred_rhp.strftime("%d %b %Y")
        else:
            drhp_display = "Filed & Approved"
    elif ipo.status == "DRHP_FILED":
        drhp_status = "CURRENT"
        drhp_display = "SEBI Review"
    else:
        drhp_status = "PENDING"
        drhp_display = "TBA"

    steps = [
        {
            "key": "drhp",
            "name": "DRHP / RHP",
            "date": drhp_date,
            "display_date": drhp_display,
            "status": drhp_status,
            "step_number": 1,
            "statutory_note": "SEBI & RoC Filing",
            "icon": "bi-file-earmark-text",
        },
        {
            "key": "open",
            "name": "Issue Opens",
            "date": ipo.open_date,
            "status": "COMPLETED" if (ipo.open_date and today > ipo.open_date)
                      else ("CURRENT" if (ipo.open_date and today == ipo.open_date) else "UPCOMING"),
            "step_number": 2,
            "statutory_note": "Bidding Opens 10:00 AM",
            "icon": "bi-door-open",
        },
        {
            "key": "close",
            "name": "Issue Closes",
            "date": ipo.close_date,
            "status": "COMPLETED" if (ipo.close_date and today > ipo.close_date)
                      else ("CURRENT" if (ipo.close_date and today == ipo.close_date) else "UPCOMING"),
            "step_number": 3,
            "statutory_note": "UPI Cutoff 5:00 PM",
            "icon": "bi-clock-history",
        },
        {
            "key": "allotment",
            "name": "Basis of Allotment",
            "date": ipo.allotment_date,
            "status": "COMPLETED" if (ipo.allotment_date and today > ipo.allotment_date)
                      else ("CURRENT" if (ipo.allotment_date and today == ipo.allotment_date) else "UPCOMING"),
            "step_number": 4,
            "statutory_note": "Lottery & Fund Unblock",
            "icon": "bi-dice-5",
        },
        {
            "key": "listing",
            "name": "Listing on Exchanges",
            "date": ipo.listing_date,
            "status": "COMPLETED" if (ipo.listing_date and today >= ipo.listing_date)
                      else ("CURRENT" if (ipo.listing_date and today == ipo.listing_date) else "UPCOMING"),
            "step_number": 5,
            "statutory_note": "T+3 Trading Debut",
            "icon": "bi-graph-up-arrow",
        },
    ]
    return steps

