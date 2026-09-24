from datetime import date, datetime

from django import template


register = template.Library()
_MONTH_ABBREVIATIONS = (
    "Jan",
    "Feb",
    "Mar",
    "Apr",
    "May",
    "Jun",
    "Jul",
    "Aug",
    "Sep",
    "Oct",
    "Nov",
    "Dec",
)


@register.filter
def benchmark_date(value: date) -> str:
    """Format a seeded date without consulting system timezone databases."""
    if not isinstance(value, date):
        return ""
    return f"{_MONTH_ABBREVIATIONS[value.month - 1]} {value.day}, {value.year}"


@register.filter
def benchmark_timestamp(value: datetime) -> str:
    """Format seeded comment timestamps in a locale-independent form."""
    if not isinstance(value, datetime):
        return ""
    return f"{benchmark_date(value)} {value.hour:02d}:{value.minute:02d}"
