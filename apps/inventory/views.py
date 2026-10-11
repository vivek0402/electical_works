from django.shortcuts import render
from django.utils import timezone

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE

from . import selectors


@role_required(OFFICE)
def dashboard(request):
    today = timezone.localdate()
    weeks = selectors.weekly_in_out(today)
    return render(
        request,
        "inventory/dashboard.html",
        {
            "stats": selectors.dashboard_stats(today),
            "weeks": weeks,
            "weeks_chart": [{"label": w["label"], "in": w["qty_in"], "out": w["qty_out"]} for w in weeks],
            "locations": selectors.location_unit_totals(),
            "recent": selectors.recent_entries(),
            "today": today,
        },
    )
