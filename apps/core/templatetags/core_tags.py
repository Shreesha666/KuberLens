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


@register.simple_tag
def bull_icon(size=14, css_class=""):
    """Renders a precision financial charging bull SVG icon."""
    classes = f"trend-animal-icon trend-bull-icon {css_class}".strip()
    return mark_safe(
        f'<svg class="{classes}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" style="vertical-align: -0.15em; display: inline-block;">'
        f'<path d="M20.67 4.28c-.62-.05-1.29.3-1.8 1.02-.75 1.05-1.6 1.83-2.6 2.25C15.02 7.2 13.56 7 12 7s-3.02.2-4.27.55c-1-.42-1.85-1.2-2.6-2.25-.51-.72-1.18-1.07-1.8-1.02-.85.07-1.52.8-1.59 1.76-.08 1.09.58 2.15 1.57 2.65.17 1.5.76 2.89 1.71 4.02 1.34 1.58 3.19 2.59 5.24 2.85v3.44c0 .55.45 1 1 1s1-.45 1-1v-3.44c2.05-.26 3.9-1.27 5.24-2.85.95-1.13 1.54-2.52 1.71-4.02.99-.5 1.65-1.56 1.57-2.65-.07-.96-.74-1.69-1.59-1.76zM12 16.5c-2.48 0-4.5-1.34-4.5-3 0-.55.45-1 1-1h7c.55 0 1 .45 1 1 0 1.66-2.02 3-4.5 3z"/>'
        f'</svg>'
    )


@register.simple_tag
def bear_icon(size=14, css_class=""):
    """Renders a precision financial prowling bear SVG icon."""
    classes = f"trend-animal-icon trend-bear-icon {css_class}".strip()
    return mark_safe(
        f'<svg class="{classes}" width="{size}" height="{size}" viewBox="0 0 24 24" fill="currentColor" aria-hidden="true" style="vertical-align: -0.15em; display: inline-block;">'
        f'<path d="M19.5 4.5c-1.38 0-2.5 1.12-2.5 2.5 0 .28.05.54.14.79-1.44-.81-3.14-1.29-4.96-1.29s-3.52.48-4.96 1.29c.09-.25.14-.51.14-.79 0-1.38-1.12-2.5-2.5-2.5S2.36 5.62 2.36 7c0 1.19.83 2.18 1.95 2.43-.27.82-.43 1.7-.43 2.61 0 4.42 3.63 8 8.12 8s8.12-3.58 8.12-8c0-.91-.16-1.79-.43-2.61 1.12-.25 1.95-1.24 1.95-2.43 0-1.38-1.14-2.5-2.64-2.5zM12 18c-3.31 0-6-2.24-6-5 0-.55.45-1 1-1h10c.55 0 1 .45 1 1 0 2.76-2.69 5-6 5zm-3.5-5.5c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1zm7 0c-.55 0-1-.45-1-1s.45-1 1-1 1 .45 1 1-.45 1-1 1z"/>'
        f'</svg>'
    )


@register.simple_tag
def trend_badge(signal, size=14, css_class=""):
    """Renders a glowing trend signal badge with accompanying bull or bear icon."""
    sig = str(signal).strip().upper() if signal else "NEUTRAL"
    if "BULL" in sig:
        b_icon = bull_icon(size=size)
        label = "BULLISH" if sig in ("BULLISH", "BULLISH_CROSS") else sig.replace("_", " ")
        return mark_safe(f'<span class="badge badge-bullish {css_class}">{b_icon}<span>{label}</span></span>')
    elif "BEAR" in sig:
        b_icon = bear_icon(size=size)
        label = "BEARISH" if sig in ("BEARISH", "BEARISH_CROSS") else sig.replace("_", " ")
        return mark_safe(f'<span class="badge badge-bearish {css_class}">{b_icon}<span>{label}</span></span>')
    else:
        label = "NEUTRAL" if sig == "NEUTRAL" else sig.replace("_", " ")
        return mark_safe(f'<span class="badge badge-neutral-trend {css_class}"><span>{label}</span></span>')


