"""
IPO Domain Models.
Covers the entire Indian IPO lifecycle: DRHP Filed, Approved, Upcoming, Live,
Closed, Allotment Finalized, and Post-Listing Performance across Mainboard and SME exchanges.
"""
from decimal import Decimal

from django.conf import settings
from django.db import models
from django.utils import timezone

from apps.core.models import AuditedModel
from apps.instruments.models import ExchangeListing


class IssueType(models.TextChoices):
    MAINBOARD = "MAINBOARD", "Mainboard"
    SME = "SME", "SME (NSE Emerge / BSE SME)"


class IPOStatus(models.TextChoices):
    DRHP_FILED = "DRHP_FILED", "DRHP Filed"
    SEBI_APPROVED = "SEBI_APPROVED", "SEBI Approved"
    UPCOMING = "UPCOMING", "Upcoming"
    LIVE = "LIVE", "Live / Open"
    CLOSED = "CLOSED", "Closed"
    ALLOTMENT_FINALIZED = "ALLOTMENT_FINALIZED", "Allotment Finalized"
    LISTED = "LISTED", "Listed"
    WITHDRAWN = "WITHDRAWN", "Withdrawn"
    POSTPONED = "POSTPONED", "Postponed"
    CANCELLED = "CANCELLED", "Cancelled"


class IPOMaster(AuditedModel):
    """
    Canonical record for an Indian Initial Public Offering (Mainboard or SME).
    """
    symbol = models.CharField(max_length=30, unique=True, db_index=True)
    company_name = models.CharField(max_length=200)
    isin = models.CharField(max_length=20, blank=True, default="")
    issue_type = models.CharField(
        max_length=20,
        choices=IssueType.choices,
        default=IssueType.MAINBOARD,
        db_index=True,
    )
    exchange = models.CharField(
        max_length=20,
        choices=[("NSE", "NSE"), ("BSE", "BSE"), ("BOTH", "NSE & BSE")],
        default="BOTH",
    )
    sector = models.CharField(max_length=100, blank=True, default="", db_index=True)
    industry = models.CharField(max_length=100, blank=True, default="")
    description = models.TextField(blank=True, default="")
    status = models.CharField(
        max_length=30,
        choices=IPOStatus.choices,
        default=IPOStatus.UPCOMING,
        db_index=True,
    )

    # Lifecycle Milestones
    drhp_date = models.DateField(null=True, blank=True)
    rhp_date = models.DateField(null=True, blank=True)
    open_date = models.DateField(null=True, blank=True, db_index=True)
    close_date = models.DateField(null=True, blank=True, db_index=True)
    allotment_date = models.DateField(null=True, blank=True)
    refund_date = models.DateField(null=True, blank=True)
    demat_credit_date = models.DateField(null=True, blank=True)
    listing_date = models.DateField(null=True, blank=True, db_index=True)

    # Issue Pricing & Lot Structure
    price_band_min = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    price_band_max = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    issue_price = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    lot_size = models.PositiveIntegerField(default=1)
    min_investment = models.DecimalField(max_digits=14, decimal_places=2, null=True, blank=True)

    # Issue Size Breakdown (in ₹ Crores)
    total_issue_size_cr = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    fresh_issue_cr = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    offer_for_sale_cr = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_shares_offered = models.BigIntegerField(null=True, blank=True)

    # Category Reservations (%)
    retail_quota_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("35.00"))
    qib_quota_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("50.00"))
    nii_quota_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("15.00"))
    employee_quota_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))

    # Promoter Holdings
    promoter_holding_pre_issue = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)
    promoter_holding_post_issue = models.DecimalField(max_digits=5, decimal_places=2, null=True, blank=True)

    # Intermediaries & Links
    lead_managers = models.CharField(max_length=500, blank=True, default="")
    registrar = models.CharField(max_length=200, blank=True, default="")
    registrar_portal_url = models.URLField(max_length=500, blank=True, default="")
    drhp_url = models.URLField(max_length=500, blank=True, default="")
    rhp_url = models.URLField(max_length=500, blank=True, default="")
    official_exchange_url = models.URLField(max_length=500, blank=True, default="")

    # Post-Listing Performance Tracking
    listing_day_open = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    listing_day_close = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    listing_day_high = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    listing_day_low = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    listing_day_gain_percent = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    # Active Listed Instrument Reference (when listed on NSE/BSE)
    listing = models.ForeignKey(
        ExchangeListing,
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="ipo_records",
    )

    class Meta:
        db_table = "ipo_master"
        ordering = ["-open_date", "symbol"]
        indexes = [
            models.Index(fields=["status", "open_date"]),
            models.Index(fields=["issue_type", "status"]),
        ]

    def __str__(self):
        return f"{self.company_name} ({self.symbol}) - {self.get_status_display()}"

    @property
    def price_band_display(self) -> str:
        if self.price_band_min and self.price_band_max:
            if self.price_band_min == self.price_band_max:
                return f"₹{self.price_band_min:,.2f}"
            return f"₹{self.price_band_min:,.0f} - ₹{self.price_band_max:,.0f}"
        if self.issue_price:
            return f"₹{self.issue_price:,.2f}"
        return "TBA"

    @property
    def effective_upper_price(self) -> Decimal:
        return self.price_band_max or self.issue_price or self.price_band_min or Decimal("0.00")

    @property
    def calculated_min_investment(self) -> Decimal:
        if self.min_investment:
            return self.min_investment
        price = self.effective_upper_price
        if price > Decimal("0.00") and self.lot_size > 0:
            return price * Decimal(str(self.lot_size))
        return Decimal("0.00")

    @property
    def is_currently_open(self) -> bool:
        today = timezone.now().date()
        if self.open_date and self.close_date:
            return self.open_date <= today <= self.close_date
        return self.status == IPOStatus.LIVE

    @property
    def latest_subscription(self):
        return self.subscriptions.order_by("-day_number").first()


class IPOSubscriptionSnapshot(AuditedModel):
    """
    Time-series category-wise subscription snapshots.
    """
    ipo = models.ForeignKey(IPOMaster, on_delete=models.CASCADE, related_name="subscriptions")
    day_number = models.PositiveSmallIntegerField(default=1)  # Day 1, Day 2, Day 3
    qib_subscription = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    nii_subscription = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    retail_subscription = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    employee_subscription = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    total_subscription = models.DecimalField(max_digits=8, decimal_places=2, default=Decimal("0.00"))
    total_applications = models.PositiveIntegerField(null=True, blank=True)
    snapshot_timestamp = models.DateTimeField(default=timezone.now)
    source = models.CharField(max_length=50, default="OFFICIAL_EXCHANGE")

    class Meta:
        db_table = "ipo_subscription_snapshot"
        ordering = ["-snapshot_timestamp"]
        unique_together = [("ipo", "day_number")]

    def __str__(self):
        return f"{self.ipo.symbol} Day {self.day_number}: {self.total_subscription}x"


class IPOFundamentals(AuditedModel):
    """
    Extracted financial health, growth, balance sheet and valuation metrics from RHP/DRHP.
    """
    ipo = models.OneToOneField(IPOMaster, on_delete=models.CASCADE, related_name="fundamentals")
    reporting_currency = models.CharField(max_length=10, default="INR")

    # Financials (₹ Crores)
    revenue_fy_prev2 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    revenue_fy_prev1 = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    revenue_fy_latest = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    revenue_cagr_3yr = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)

    ebitda_latest = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    ebitda_margin_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    pat_latest = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    pat_margin_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)

    net_worth = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    total_borrowings = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    cash_flow_operations = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)
    free_cash_flow = models.DecimalField(max_digits=12, decimal_places=2, null=True, blank=True)

    roe_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    roce_percent = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    post_issue_pe = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    post_issue_pb = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    peer_industry_pe = models.DecimalField(max_digits=8, decimal_places=2, null=True, blank=True)
    peer_comparison_data = models.JSONField(default=list, blank=True)

    # Narrative highlights
    key_strengths = models.TextField(blank=True, default="")
    key_risks = models.TextField(blank=True, default="")
    use_of_proceeds = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ipo_fundamentals"

    def __str__(self):
        return f"{self.ipo.symbol} Fundamentals (FY Latest: ₹{self.revenue_fy_latest or 0} Cr)"

    @property
    def debt_equity_ratio(self):
        if self.total_borrowings is not None and self.net_worth and self.net_worth > Decimal("0.00"):
            return round(self.total_borrowings / self.net_worth, 2)
        return None


class DocumentType(models.TextChoices):
    DRHP = "DRHP", "Draft Red Herring Prospectus (DRHP)"
    RHP = "RHP", "Red Herring Prospectus (RHP)"
    PROSPECTUS = "PROSPECTUS", "Final Prospectus"
    PRICE_BAND_AD = "PRICE_BAND_AD", "Price Band Advertisement"
    ANCHOR_ALLOCATION = "ANCHOR_ALLOCATION", "Anchor Investor Allocation"
    BASIS_OF_ALLOTMENT = "BASIS_OF_ALLOTMENT", "Basis of Allotment Document"
    OTHER = "OTHER", "Other Regulatory Filing"


class IPODocument(AuditedModel):
    """
    Official regulatory filings and prospectus documents.
    """
    ipo = models.ForeignKey(IPOMaster, on_delete=models.CASCADE, related_name="documents")
    doc_type = models.CharField(max_length=30, choices=DocumentType.choices, default=DocumentType.RHP)
    title = models.CharField(max_length=255)
    file_url = models.URLField(max_length=500)
    filing_date = models.DateField(null=True, blank=True)
    file_size_mb = models.DecimalField(max_digits=6, decimal_places=2, null=True, blank=True)
    is_verified = models.BooleanField(default=True)
    source = models.CharField(max_length=100, default="SEBI / Exchange")

    class Meta:
        db_table = "ipo_document"
        ordering = ["-filing_date", "doc_type"]

    def __str__(self):
        return f"{self.ipo.symbol} - {self.get_doc_type_display()}"


class IPOScoring(AuditedModel):
    """
    Transparent weighted quantitative research scoring and horizon evaluations.
    """
    ipo = models.OneToOneField(IPOMaster, on_delete=models.CASCADE, related_name="scoring")
    business_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    financials_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    valuation_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    growth_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    governance_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    structure_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    demand_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))
    overall_score = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("0.00"))

    recommendation = models.CharField(
        max_length=40,
        choices=[
            ("STRONG_RESEARCH_CANDIDATE", "Strong Research Candidate"),
            ("CONSIDER_APPLYING", "Consider Applying"),
            ("APPLY_WITH_CAUTION", "Apply with Caution"),
            ("AVOID", "Avoid"),
            ("INSUFFICIENT_DATA", "Insufficient Data"),
        ],
        default="CONSIDER_APPLYING",
    )

    listing_gain_potential = models.CharField(max_length=20, default="MODERATE")  # HIGH, MODERATE, LOW
    short_term_potential = models.CharField(max_length=20, default="MODERATE")  # POSITIVE, NEUTRAL, CAUTION
    long_term_potential = models.CharField(max_length=20, default="POSITIVE")  # POSITIVE, NEUTRAL, CAUTION
    confidence_level = models.CharField(
        max_length=20,
        choices=[
            ("HIGH", "High Confidence"),
            ("MEDIUM", "Medium Confidence"),
            ("LOW", "Low Confidence"),
        ],
        default="HIGH",
    )
    data_completeness_percent = models.DecimalField(max_digits=5, decimal_places=2, default=Decimal("100.00"))
    strengths_list = models.JSONField(default=list, blank=True)
    risks_list = models.JSONField(default=list, blank=True)
    scoring_rationale = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ipo_scoring"

    def __str__(self):
        return f"{self.ipo.symbol} Score: {self.overall_score}/100 ({self.recommendation})"

    @property
    def composite_score(self) -> Decimal:
        return self.overall_score

    @property
    def score_grade(self) -> str:
        s = self.overall_score
        if s >= Decimal("85.0"):
            return "A+"
        if s >= Decimal("75.0"):
            return "A"
        if s >= Decimal("60.0"):
            return "B"
        if s >= Decimal("45.0"):
            return "C"
        return "D"

    @property
    def recommendation_badge_class(self) -> str:
        rec_badges = {
            "STRONG_RESEARCH_CANDIDATE": "bg-success text-white",
            "CONSIDER_APPLYING": "bg-primary text-white",
            "APPLY_WITH_CAUTION": "bg-warning text-dark",
            "AVOID": "bg-danger text-white",
            "INSUFFICIENT_DATA": "bg-secondary text-white",
        }
        return rec_badges.get(self.recommendation, "bg-secondary text-white")


class IPOGMPRecord(AuditedModel):
    """
    Grey Market Premium tracking.
    Explicitly marked as UNOFFICIAL_MARKET_ESTIMATE and never combined silently with exchange data.
    """
    ipo = models.ForeignKey(IPOMaster, on_delete=models.CASCADE, related_name="gmp_records")
    reported_gmp = models.DecimalField(max_digits=10, decimal_places=2)  # In ₹
    estimated_listing_price = models.DecimalField(max_digits=12, decimal_places=2)
    estimated_gain_percent = models.DecimalField(max_digits=8, decimal_places=2)
    source_name = models.CharField(max_length=100, default="Market Estimates")
    is_unofficial = models.BooleanField(default=True)
    observed_at = models.DateTimeField(default=timezone.now)

    class Meta:
        db_table = "ipo_gmp_record"
        ordering = ["-observed_at"]

    def __str__(self):
        return f"{self.ipo.symbol} GMP: ₹{self.reported_gmp} ({self.estimated_gain_percent:+.1f}%)"


class IPOFamilyMember(AuditedModel):
    """
    Demat & PAN account profile for a family member.
    Enables coordinated multi-account retail bidding to legally multiply SEBI lottery odds.
    """
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="ipo_family_members",
    )
    name = models.CharField(max_length=100)
    relationship = models.CharField(
        max_length=30,
        choices=[
            ("SELF", "Self"),
            ("SPOUSE", "Spouse"),
            ("PARENT", "Parent"),
            ("SIBLING", "Sibling"),
            ("CHILD", "Child"),
            ("HUF", "HUF"),
            ("OTHER", "Other"),
        ],
        default="SELF",
    )
    pan = models.CharField(max_length=10)
    demat_account = models.CharField(max_length=50, blank=True, default="")
    default_upi_id = models.CharField(max_length=100, blank=True, default="")
    asba_bank_name = models.CharField(max_length=100, blank=True, default="")
    is_primary = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ipo_family_member"
        ordering = ["-is_primary", "name"]
        unique_together = [("user", "pan")]

    def __str__(self):
        return f"{self.name} ({self.masked_pan})"

    @property
    def masked_pan(self) -> str:
        if self.pan and len(self.pan) == 10:
            return f"{self.pan[:5]}****{self.pan[-1]}"
        return self.pan or ""


class IPOApplication(AuditedModel):
    """
    User-specific tracked IPO application with UPI mandate and allotment outcome.
    Kept strictly private to the user.
    """
    user = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="ipo_applications")
    ipo = models.ForeignKey(IPOMaster, on_delete=models.CASCADE, related_name="user_applications")
    family_member = models.ForeignKey(
        "IPOFamilyMember",
        on_delete=models.SET_NULL,
        null=True,
        blank=True,
        related_name="applications",
    )
    investor_category = models.CharField(
        max_length=20,
        choices=[
            ("RETAIL", "Retail Individual (RII) - Up to ₹2 Lakhs"),
            ("sHNI", "Small HNI (bHNI) - ₹2 Lakhs to ₹10 Lakhs"),
            ("bHNI", "Big HNI (bHNI) - Above ₹10 Lakhs"),
            ("EMPLOYEE", "Employee Reservation"),
            ("SHAREHOLDER", "Shareholder Quota"),
        ],
        default="RETAIL",
    )
    application_number = models.CharField(max_length=50, blank=True, default="")
    lots_applied = models.PositiveIntegerField(default=1)
    shares_applied = models.PositiveIntegerField(default=1)
    bid_price = models.DecimalField(max_digits=12, decimal_places=2)
    applied_amount = models.DecimalField(max_digits=14, decimal_places=2)
    is_cutoff_bid = models.BooleanField(default=True)

    # Status tracking
    mandate_status = models.CharField(
        max_length=30,
        choices=[
            ("PENDING", "Mandate Pending"),
            ("APPROVED", "Mandate Approved / Funds Blocked"),
            ("REJECTED", "Mandate Failed / Expired"),
            ("REVOKED", "Revoked / Cancelled"),
        ],
        default="APPROVED",
    )
    allotment_status = models.CharField(
        max_length=30,
        choices=[
            ("AWAITING", "Awaiting Allotment"),
            ("ALLOTTED", "Fully Allotted"),
            ("PARTIALLY_ALLOTTED", "Partially Allotted"),
            ("NOT_ALLOTTED", "Not Allotted / Refund Due"),
            ("REFUNDED", "Funds Unblocked / Refunded"),
        ],
        default="AWAITING",
    )
    allotted_shares = models.PositiveIntegerField(default=0)
    allotted_amount = models.DecimalField(max_digits=14, decimal_places=2, default=Decimal("0.00"))
    demat_account = models.CharField(max_length=50, blank=True, default="")
    listing_strategy = models.CharField(
        max_length=30,
        choices=[
            ("HOLD", "Hold for Long-Term"),
            ("BOOK_PROFIT", "Book Listing Gains at Open"),
            ("PARTIAL_EXIT", "Partial Exit / Recover Capital"),
            ("STOP_LOSS", "Exit on Stop Loss"),
        ],
        default="HOLD",
    )
    transferred_to_portfolio = models.BooleanField(default=False)
    notes = models.TextField(blank=True, default="")

    class Meta:
        db_table = "ipo_user_application"
        ordering = ["-created_at"]

    def __str__(self):
        return f"{self.user} - {self.ipo.symbol} ({self.lots_applied} Lots) - {self.allotment_status}"

    @property
    def refund_amount(self) -> Decimal:
        if self.applied_amount and self.allotted_amount is not None:
            diff = self.applied_amount - self.allotted_amount
            return max(Decimal("0.00"), diff)
        return Decimal("0.00")

