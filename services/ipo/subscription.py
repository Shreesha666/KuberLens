"""
IPO Subscription Analytics Service.
Calculates time-series demand, category breakdowns, day-wise momentum,
and bidding demand acceleration.
"""
from decimal import Decimal
from typing import Any

from apps.ipo.models import IPOMaster, IPOSubscriptionSnapshot


def get_subscription_summary(ipo: IPOMaster) -> dict[str, Any]:
    """
    Computes aggregated subscription analytics and momentum metrics for an IPO.
    """
    snapshots = list(ipo.subscriptions.order_by("day_number"))
    if not snapshots:
        return {
            "has_data": False,
            "latest": None,
            "history": [],
            "momentum_label": "No Bids Recorded",
            "momentum_class": "text-muted",
        }

    latest: IPOSubscriptionSnapshot = snapshots[-1]
    history: list[dict[str, Any]] = []

    prev_sub = Decimal("0.00")
    for s in snapshots:
        day_growth = s.total_subscription - prev_sub
        history.append({
            "day": s.day_number,
            "qib": s.qib_subscription,
            "nii": s.nii_subscription,
            "retail": s.retail_subscription,
            "employee": s.employee_subscription,
            "total": s.total_subscription,
            "apps": s.total_applications,
            "timestamp": s.snapshot_timestamp,
            "delta": day_growth,
        })
        prev_sub = s.total_subscription

    # Demand momentum classification
    if len(snapshots) >= 2:
        last_delta = snapshots[-1].total_subscription - snapshots[-2].total_subscription
        if last_delta >= Decimal("10.00"):
            momentum_label = "Surging Demand Acceleration"
            momentum_class = "text-success fw-bold"
        elif last_delta >= Decimal("2.00"):
            momentum_label = "Steady Demand Growth"
            momentum_class = "text-primary fw-semibold"
        else:
            momentum_label = "Moderate Demand"
            momentum_class = "text-secondary"
    else:
        if latest.total_subscription >= Decimal("5.00"):
            momentum_label = "Strong Opening Demand"
            momentum_class = "text-success fw-semibold"
        elif latest.total_subscription >= Decimal("1.00"):
            momentum_label = "Fully Subscribed"
            momentum_class = "text-primary fw-semibold"
        else:
            momentum_label = "Subscribing"
            momentum_class = "text-secondary"

    return {
        "has_data": True,
        "latest": latest,
        "history": history,
        "snapshots_count": len(snapshots),
        "momentum_label": momentum_label,
        "momentum_class": momentum_class,
        "is_oversubscribed": latest.total_subscription > Decimal("1.00"),
    }

