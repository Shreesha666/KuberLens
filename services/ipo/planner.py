"""
IPO Bid Planning & Retail Lottery Allotment Probability Engine.
Implements:
1. Interactive Bid Calculator per Section 11 of IPO_research.md:
   - Category limits (Retail <= 2L, sHNI 2L-10L, bHNI > 10L)
   - UPI Limit compliance (<= 5L for UPI; > 5L ASBA mandatory)
   - Cut-off price validation
   - Scenario gain/loss projections
2. Allotment Probability Estimator per Section 12 of IPO_research.md:
   - SEBI retail lottery model: P = min(1.0, 1 / Retail Subscription Multiple)
   - Multi-account family PAN diversification simulator: P(>= 1 allotment) = 1 - (1 - P)^N
   - sHNI / bHNI allotment mechanics
   - SEBI duplicate PAN rejection compliance warnings
"""
from decimal import Decimal
from typing import Any

from django.utils import timezone

from apps.ipo.models import IPOMaster, IPOStatus
from services.ipo.subscription import get_subscription_summary


def calculate_bid_plan(
    ipo: IPOMaster,
    category: str = "RETAIL",
    lots: int = 1,
    custom_bid_price: Decimal | None = None,
    custom_lot_size: int | None = None,
    is_cutoff: bool = True,
    budget: Decimal | None = None,
) -> dict[str, Any]:
    """
    Computes precise lot sizing, capital commitment, regulatory category eligibility,
    payment routing (UPI vs ASBA), and scenario outcomes.
    Supports both announced RHP issues and pre-RHP pipeline simulation mode.
    """
    has_announced_pricing = (
        ipo.price_band_max is not None and ipo.effective_upper_price > Decimal("0.00")
    ) or (
        ipo.issue_price is not None and ipo.issue_price > Decimal("0.00")
    )

    if has_announced_pricing:
        lot_size = custom_lot_size if (custom_lot_size and custom_lot_size > 0) else ipo.effective_lot_size
        price_min = ipo.price_band_min or ipo.issue_price or Decimal("0.00")
        price_max = ipo.effective_upper_price

        # Determine effective bid price
        if is_cutoff or custom_bid_price is None:
            effective_price = price_max
        else:
            # Clamp custom price to price band if defined
            if price_min > Decimal("0.00") and price_max > Decimal("0.00"):
                effective_price = max(price_min, min(price_max, custom_bid_price))
            else:
                effective_price = custom_bid_price
    else:
        # Pipeline / Simulation Mode for Pre-RHP issues
        is_cutoff = False
        price_min = Decimal("0.00")
        price_max = Decimal("0.00")
        if custom_bid_price is not None and custom_bid_price > Decimal("0.00"):
            effective_price = custom_bid_price
        else:
            effective_price = Decimal("0.00")

        if custom_lot_size is not None and custom_lot_size > 0:
            lot_size = custom_lot_size
        elif ipo.lot_size and ipo.lot_size > 1:
            lot_size = ipo.lot_size
        elif effective_price > Decimal("0.00"):
            # Estimate SEBI retail lot size targeting ~₹14,500 - ₹15,000
            lot_size = max(1, int(Decimal("14800.00") // effective_price))
        else:
            lot_size = 50  # Default simulation lot size

    lots = max(1, lots)
    total_shares = lots * lot_size
    amount_per_lot = lot_size * effective_price
    total_amount = total_shares * effective_price
    min_retail_amount = lot_size * (price_max if has_announced_pricing else effective_price)

    # Dynamic lot limits
    if amount_per_lot > Decimal("0.00"):
        max_retail_lots = max(1, int(Decimal("200000.00") // amount_per_lot))
        min_shni_lots = int(Decimal("200000.00") // amount_per_lot) + 1
    else:
        max_retail_lots = 13
        min_shni_lots = 14

    # Regulatory category validations
    warnings: list[str] = []
    is_eligible = True

    if not has_announced_pricing and effective_price == Decimal("0.00"):
        warnings.append(
            f"Official price band and lot size for {ipo.company_name} have not yet been announced (pre-RHP pipeline stage). "
            f"Enter an estimated share price below to simulate lot sizing and capital blocking."
        )

    # 1. Category Limit Checks
    if category == "RETAIL":
        # SEBI limit for Retail Individual Investors is ₹2,00,000
        if total_amount > Decimal("200000.00"):
            is_eligible = False
            warnings.append(
                f"Retail application amount (₹{total_amount:,.2f}) exceeds the SEBI ₹2,00,000 statutory limit. "
                f"Maximum allowed retail lots: {max_retail_lots} lot(s). Switch to sHNI category for bids above ₹2 Lakhs."
            )
    elif category == "sHNI":
        # Small HNI must be > ₹2,00,000 and <= ₹10,00,000
        if total_amount <= Decimal("200000.00") and amount_per_lot > Decimal("0.00"):
            is_eligible = False
            warnings.append(
                f"Small HNI (sHNI) bids must strictly exceed ₹2,00,000. "
                f"Minimum required sHNI bid: {min_shni_lots} lot(s) (₹{min_shni_lots * amount_per_lot:,.2f})."
            )
        elif total_amount > Decimal("1000000.00"):
            is_eligible = False
            warnings.append(
                f"Small HNI bids cannot exceed ₹10,00,000 (Current: ₹{total_amount:,.2f}). "
                f"Switch to Big HNI (bHNI) category for bids above ₹10 Lakhs."
            )
        if is_cutoff:
            warnings.append("Cut-off price bidding is not permitted for HNI/NII categories per SEBI guidelines. Price locked at cap.")
    elif category == "bHNI":
        # Big HNI must exceed ₹10,00,000
        min_bhni_lots = int(Decimal("1000000.00") // amount_per_lot) + 1 if amount_per_lot > 0 else 1
        if total_amount <= Decimal("1000000.00") and amount_per_lot > Decimal("0.00"):
            is_eligible = False
            warnings.append(
                f"Big HNI (bHNI) bids must strictly exceed ₹10,00,000. "
                f"Minimum required bHNI bid: {min_bhni_lots} lot(s) (₹{min_bhni_lots * amount_per_lot:,.2f})."
            )
        if is_cutoff:
            warnings.append("Cut-off price bidding is not permitted for HNI/NII categories.")

    # 2. Payment Mandate Validation (NPCI/SEBI UPI Limit: ₹5 Lakhs)
    if total_amount <= Decimal("500000.00"):
        payment_mode = "UPI_MANDATE"
        payment_note = "Eligible for 1-Click UPI Autopay Mandate (Google Pay, PhonePe, BHIM, Paytm) up to ₹5 Lakhs."
    else:
        payment_mode = "ASBA_NETBANKING"
        payment_note = "Amount exceeds ₹5,00,000 UPI limit. Must be submitted via Bank ASBA (NetBanking) funds-blocked mandate."

    # 3. Budget analysis if provided
    max_lots_within_budget = None
    remaining_budget = None
    if budget and budget > Decimal("0.00") and amount_per_lot > Decimal("0.00"):
        max_lots_within_budget = int(budget // amount_per_lot)
        remaining_budget = budget - (lots * amount_per_lot)

    # 4. Scenario Projections
    latest_gmp = ipo.gmp_records.order_by("-observed_at").first()
    gmp_gain_per_share = latest_gmp.reported_gmp if latest_gmp else Decimal("0.00")
    gmp_listing_price = effective_price + gmp_gain_per_share

    scenarios = [
        {
            "label": "GMP Market Estimate",
            "listing_price": gmp_listing_price,
            "gain_percent": round((gmp_gain_per_share / effective_price * Decimal("100.0")), 1) if effective_price > 0 else Decimal("0.0"),
            "total_gain": total_shares * gmp_gain_per_share,
            "badge_class": "bg-success text-white" if gmp_gain_per_share > 0 else "bg-secondary text-white",
        },
        {
            "label": "Bullish Expansion (+25%)",
            "listing_price": round(effective_price * Decimal("1.25"), 2),
            "gain_percent": Decimal("25.0"),
            "total_gain": round(total_amount * Decimal("0.25"), 2),
            "badge_class": "bg-success text-white",
        },
        {
            "label": "Moderate Listing (+10%)",
            "listing_price": round(effective_price * Decimal("1.10"), 2),
            "gain_percent": Decimal("10.0"),
            "total_gain": round(total_amount * Decimal("0.10"), 2),
            "badge_class": "bg-primary text-white",
        },
        {
            "label": "Flat Listing (0%)",
            "listing_price": effective_price,
            "gain_percent": Decimal("0.0"),
            "total_gain": Decimal("0.00"),
            "badge_class": "bg-secondary text-white",
        },
        {
            "label": "Discount Listing (-10%)",
            "listing_price": round(effective_price * Decimal("0.90"), 2),
            "gain_percent": Decimal("-10.0"),
            "total_gain": round(total_amount * Decimal("-0.10"), 2),
            "badge_class": "bg-danger text-white",
        },
    ]

    return {
        "ipo": ipo,
        "category": category,
        "lots": lots,
        "lot_size": lot_size,
        "total_shares": total_shares,
        "bid_price": effective_price,
        "is_cutoff": is_cutoff,
        "amount_per_lot": amount_per_lot,
        "total_amount": total_amount,
        "min_retail_amount": min_retail_amount,
        "payment_mode": payment_mode,
        "payment_note": payment_note,
        "is_eligible": is_eligible,
        "warnings": warnings,
        "budget": budget,
        "max_lots_within_budget": max_lots_within_budget,
        "remaining_budget": remaining_budget,
        "scenarios": scenarios,
        "has_announced_pricing": has_announced_pricing,
        "is_simulation_mode": not has_announced_pricing,
        "max_retail_lots": max_retail_lots,
        "min_shni_lots": min_shni_lots,
    }


def estimate_allotment_probability(
    ipo: IPOMaster,
    category: str = "RETAIL",
    lots_applied: int = 1,
    num_pan_accounts: int = 1,
) -> dict[str, Any]:
    """
    Computes mathematical allotment probabilities under SEBI randomized lottery rules.
    Under SEBI guidelines:
    - Retail oversubscription: Allotment is decided by computerized lottery where every
      successful applicant gets strictly 1 minimum lot.
    - Applying for multiple lots under the SAME PAN does NOT increase retail allotment odds.
    - Applying with N distinct family PAN accounts multiplies the probability: P = 1 - (1 - P_single)^N.
    """
    sub_summary = get_subscription_summary(ipo)
    latest_sub = sub_summary["latest"]

    lot_size = ipo.effective_lot_size
    total_shares = ipo.total_shares_offered or 1000000
    retail_quota_pct = ipo.retail_quota_percent or Decimal("35.00")

    # Category shares and lots reserved
    if category == "RETAIL":
        quota_shares = int(Decimal(str(total_shares)) * (retail_quota_pct / Decimal("100.0")))
        quota_lots = quota_shares // lot_size if lot_size > 0 else 1
        if latest_sub and latest_sub.retail_subscription and latest_sub.retail_subscription > Decimal("0.00"):
            sub_multiple = latest_sub.retail_subscription
        elif latest_sub and latest_sub.total_subscription and latest_sub.total_subscription > Decimal("0.00"):
            sub_multiple = latest_sub.total_subscription
        else:
            sub_multiple = None
        sub_apps = latest_sub.total_applications if latest_sub else None
    elif category == "sHNI":
        nii_quota_pct = ipo.nii_quota_percent or Decimal("15.00")
        # sHNI typically gets 1/3 of NII quota (5% of total issue)
        quota_shares = int(Decimal(str(total_shares)) * ((nii_quota_pct / Decimal("3.0")) / Decimal("100.0")))
        quota_lots = quota_shares // (lot_size * 14) if lot_size > 0 else 1  # 14 lots min sHNI
        if latest_sub and latest_sub.nii_subscription and latest_sub.nii_subscription > Decimal("0.00"):
            sub_multiple = latest_sub.nii_subscription
        elif latest_sub and latest_sub.total_subscription and latest_sub.total_subscription > Decimal("0.00"):
            sub_multiple = latest_sub.total_subscription
        else:
            sub_multiple = None
        sub_apps = None
    else:
        # Default fallback
        quota_shares = int(Decimal(str(total_shares)) * Decimal("0.10"))
        quota_lots = quota_shares // lot_size if lot_size > 0 else 1
        sub_multiple = latest_sub.total_subscription if (latest_sub and latest_sub.total_subscription and latest_sub.total_subscription > Decimal("0.00")) else None
        sub_apps = None

    today = timezone.now().date()
    is_pre_issue = ipo.status in [IPOStatus.UPCOMING, IPOStatus.DRHP_FILED, IPOStatus.SEBI_APPROVED] or (ipo.open_date is None) or (ipo.open_date > today)

    # Base Probability Calculation for 1 PAN
    if sub_multiple is None or (is_pre_issue and not latest_sub):
        is_awaiting_data = True
        is_lottery = False
        single_pan_prob = Decimal("100.0")
        selected_prob = 100.0
        status_note = "Official exchange bidding has not opened yet. Real-time subscription multiples and mathematical SEBI lottery probability will calculate once Day-1 bids are recorded."
    elif sub_multiple <= Decimal("1.00"):
        # Fully available / undersubscribed
        is_awaiting_data = False
        single_pan_prob = Decimal("100.0")
        selected_prob = 100.0
        is_lottery = False
        status_note = f"Category is currently undersubscribed at {sub_multiple:.2f}x. Under SEBI rules, all valid applications are guaranteed allotment of requested lots."
    else:
        is_awaiting_data = False
        is_lottery = True
        # If application count is published:
        if sub_apps and sub_apps > quota_lots and quota_lots > 0:
            prob_float = min(1.0, float(quota_lots) / float(sub_apps))
        else:
            # Derived from subscription multiple: P = 1 / Multiple
            prob_float = min(1.0, 1.0 / float(sub_multiple))

        single_pan_prob = Decimal(str(round(prob_float * 100.0, 2)))
        status_note = f"Category is oversubscribed at {sub_multiple:.2f}x. Allotment decided via randomized SEBI lottery (1 lot per winning PAN)."
        selected_prob = round((1.0 - ((1.0 - prob_float) ** num_pan_accounts)) * 100.0, 1)

    # Multi-account family PAN diversification analysis (N distinct PANs)
    num_pan_accounts = max(1, min(5, num_pan_accounts))

    family_scenarios: list[dict[str, Any]] = []
    for n in range(1, 6):
        if is_awaiting_data:
            family_scenarios.append({
                "pans": n,
                "probability_percent": 100.0,
                "expected_allotments": n,
                "is_selected": n == num_pan_accounts,
            })
        else:
            p_float = float(single_pan_prob) / 100.0
            at_least_one = 1.0 - ((1.0 - p_float) ** n)
            family_scenarios.append({
                "pans": n,
                "probability_percent": round(at_least_one * 100.0, 1),
                "expected_allotments": round(p_float * n, 2),
                "is_selected": n == num_pan_accounts,
            })

    compliance_notes = [
        "SEBI Lottery Rule: For oversubscribed retail issues, applying for more than 1 lot under the same PAN does NOT increase your probability of getting allotted.",
        "Strictly 1 PAN per Application: Applying multiple times with the same PAN number results in technical rejection of ALL applications by the registrar.",
        "Family Diversification: Applying for 1 lot each across distinct family member PANs is completely legitimate and mathematically maximizes allotment odds.",
    ]

    return {
        "ipo": ipo,
        "category": category,
        "lots_applied": lots_applied,
        "num_pan_accounts": num_pan_accounts,
        "quota_shares": quota_shares,
        "quota_lots": quota_lots,
        "subscription_multiple": sub_multiple or Decimal("1.00"),
        "is_lottery": is_lottery,
        "is_awaiting_data": is_awaiting_data,
        "status_note": status_note,
        "single_pan_probability": single_pan_prob,
        "selected_probability": selected_prob,
        "family_scenarios": family_scenarios,
        "compliance_notes": compliance_notes,
    }

