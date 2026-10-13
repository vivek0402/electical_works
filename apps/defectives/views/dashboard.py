from django.shortcuts import render
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE

from .. import selectors
from ..models import Outcome

REJECTED = {Outcome.REJECTED_RETURNED, Outcome.REJECTED_SCRAPPED}


@never_cache
@role_required(OFFICE)
def defectives_dashboard(request):
    d = selectors.dashboard(timezone.localdate())
    chart = [{"label": label, "n": n, "bad": value in REJECTED} for value, label, n in d["outcomes"]]
    return render(request, "defectives/dashboard.html", {"d": d, "outcomes_chart": chart})
