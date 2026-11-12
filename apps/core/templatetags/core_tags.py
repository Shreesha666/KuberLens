from decimal import Decimal

from django import template

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
