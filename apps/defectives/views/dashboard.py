from urllib.parse import urlencode

from django.shortcuts import render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.cache import never_cache

from apps.accounts.decorators import role_required
from apps.accounts.roles import OFFICE
from apps.inventory.context_processors import service_counts

from .. import selectors
from ..models import Outcome

REJECTED = {Outcome.REJECTED_RETURNED, Outcome.REJECTED_SCRAPPED}


@never_cache
@role_required(OFFICE)
def defectives_dashboard(request):
    d = selectors.dashboard(timezone.localdate(), service_counts(request)[1])
    pieces = reverse("defective_pieces")
    bars = [
        {
            "label": label,
            "n": n,
            "alert": value in REJECTED,
            "href": f"{pieces}?{urlencode({'answered': value, 'since': d['since'].isoformat()})}",
        }
        for value, label, n in d["outcomes"]
    ]
    attention = []
    if d["in_store"]:
        oldest = d["oldest"][0]
        days = oldest["days"]
        attention.append(
            {
                "tone": "wait",
                "icon": "building-warehouse",
                "n": d["in_store"],
                "title": "Pieces in store, not yet in a batch",
                "sub": f"Oldest: {oldest['piece'].tag}, {days} day{'' if days == 1 else 's'} in store",
                "go": "Make a return batch",
                "href": f"{pieces}?status=IN_STORE",
            }
        )
    if d["overdue"]:
        attention.append(
            {
                "tone": "alert",
                "icon": "clock",
                "n": d["overdue"],
                "title": f"Batches sent over {selectors.OVERDUE_DAYS} days ago, still waiting",
                "sub": "The company has not answered for every piece.",
                "go": "Chase the company",
                "href": f"{reverse('return_batches')}?waiting_over={selectors.OVERDUE_DAYS}",
            }
        )
    return render(
        request,
        "defectives/dashboard.html",
        {
            "d": d,
            "attention": attention,
            "bars": bars,
            "bars_top": max([b["n"] for b in bars] + [1]),
        },
    )
