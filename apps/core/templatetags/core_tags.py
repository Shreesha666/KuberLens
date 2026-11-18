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
    """Format a monetary amount in Indian Rupee format with proper negative placement e.g. -₹1,02,425.21."""
    if value is None or value == "":
        return "₹0.00"
    try:
        val = Decimal(str(value))
        if val < 0:
            return f"-₹{abs(val):,.2f}"
        return f"₹{val:,.2f}"
    except Exception:
        return f"₹{value}"


@register.filter
def indian_inr(value):
    """Format monetary amount in authentic Indian numbering e.g. ₹4,99,170.84 or ₹10,00,000.00."""
    if value is None or value == "":
        return "₹0.00"
    try:
        val = Decimal(str(value))
        is_neg = val < 0
        val = abs(val)
        parts = f"{val:.2f}".split(".")
        int_p, dec_p = parts[0], parts[1]
        if len(int_p) <= 3:
            res = int_p
        else:
            last3 = int_p[-3:]
            rem = int_p[:-3]
            groups = []
            while len(rem) > 2:
                groups.insert(0, rem[-2:])
                rem = rem[:-2]
            if rem:
                groups.insert(0, rem)
            res = ",".join(groups) + "," + last3
        sign = "-₹" if is_neg else "₹"
        return f"{sign}{res}.{dec_p}"
    except Exception:
        return f"₹{value}"


@register.filter
def indian_inr_signed(value):
    """Format monetary amount in authentic Indian numbering with explicit + / - sign."""
    if value is None or value == "":
        return "₹0.00"
    try:
        val = Decimal(str(value))
        if val == Decimal("0.00") or val == 0:
            return "₹0.00"
        is_pos = val > 0
        prefix = "+₹" if is_pos else "-₹"
        val = abs(val)
        parts = f"{val:.2f}".split(".")
        int_p, dec_p = parts[0], parts[1]
        if len(int_p) <= 3:
            res = int_p
        else:
            last3 = int_p[-3:]
            rem = int_p[:-3]
            groups = []
            while len(rem) > 2:
                groups.insert(0, rem[-2:])
                rem = rem[:-2]
            if rem:
                groups.insert(0, rem)
            res = ",".join(groups) + "," + last3
        return f"{prefix}{res}.{dec_p}"
    except Exception:
        return f"₹{value}"


@register.filter
def format_inr_signed(value):
    """Format monetary amount with explicit + / - sign e.g. +₹1,013.54 or -₹1,011.50."""
    if value is None or value == "":
        return "₹0.00"
    try:
        val = Decimal(str(value))
        if val > 0:
            return f"+₹{val:,.2f}"
        elif val < 0:
            return f"-₹{abs(val):,.2f}"
        return "₹0.00"
    except Exception:
        return f"₹{value}"


@register.filter
def intcomma_inr(value):
    """Formats an integer or decimal with thousand separators, e.g. 67308 -> 67,308"""
    if value is None or value == "":
        return "0"
    try:
        val = Decimal(str(value))
        return f"{val:,.0f}"
    except Exception:
        return str(value)


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


@register.filter
def safe_markdown(value):
    """
    Safely parses common inline markdown elements (**bold**, *italic*) and line breaks,
    escaping raw HTML to prevent injection while rendering cleanly styled rich text.
    """
    if not value:
        return ""
    import html
    import re

    escaped = html.escape(str(value))
    # Replace **bold** with <strong>bold</strong>
    bold_sub = re.sub(r"\*\*(.+?)\*\*", r"<strong>\1</strong>", escaped)
    # Replace *italic* with <em>italic</em>
    italic_sub = re.sub(r"\*(.+?)\*", r"<em>\1</em>", bold_sub)
    # Split paragraphs by double newline, or single newlines with br
    paragraphs = [p.strip().replace("\n", "<br>") for p in italic_sub.split("\n\n") if p.strip()]
    rendered = "".join(f"<p class='mb-2'>{p}</p>" for p in paragraphs)
    return mark_safe(rendered)


