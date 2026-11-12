from decimal import Decimal

from django import template
from django.urls import reverse
from django.utils.safestring import mark_safe

register = template.Library()

@register.filter
def financial_color(value):
    """
    Returns text-success for positive values, text-danger for negative values,
    or text-muted for zero/none.
    """
    if value is None or value == "":
        return "text-muted"
    try:
        val_str = str(value).replace("%", "").replace("+", "").replace(",", "").strip()
        num = Decimal(val_str)
        if num > 0:
            return "text-success"
        elif num < 0:
            return "text-danger"
        return "text-muted"
    except Exception:
        return "text-muted"

@register.filter
def format_inr(value):
    """Format a monetary amount in Indian Rupee format."""
    if value is None or value == "":
        return "₹0.00"
    try:
        val = Decimal(str(value))
        return f"₹{val:,.2f}"
    except Exception:
        return f"₹{value}"


@register.simple_tag
def stock_logo(target, size=32, css_class=""):
    """
    Renders an <img> tag pointing to the cached local proxy endpoint for the stock logo.
    Accepts either an ExchangeListing, Holding, Instrument, or a raw symbol string.
    """
    symbol = getattr(target, "symbol", None)
    if not symbol and hasattr(target, "listing"):
        symbol = getattr(target.listing, "symbol", None)
    if not symbol:
        symbol = str(target) if target else ""

    clean_sym = symbol.strip().upper()
    if not clean_sym:
        return ""

    url = reverse("stocks:stock_logo", kwargs={"symbol": clean_sym})
    classes = f"stock-logo rounded flex-shrink-0 border {css_class}".strip()
    return mark_safe(
        f'<img src="{url}" alt="{clean_sym} logo" width="{size}" height="{size}" '
        f'class="{classes}" loading="lazy" style="object-fit: contain; aspect-ratio: 1/1; background-color: var(--bs-card-bg, #fff);" />'
    )

