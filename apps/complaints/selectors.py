"""All reads for the complaints screens. Views call these; no queries in templates."""

import re
from collections import Counter
from datetime import timedelta

from django.db.models import Count, Max, Prefetch, Q

from apps.defectives.models import DefectivePiece

from .filters import AGE_BUCKETS, CLOSED_SINCE_TABS, FINISHED, TAB_LABELS, TABS
from .models import FINISHED_STATUSES, OPEN_STATUSES, Complaint, ComplaintEvent, Site, Status
from .phones import format_phone


def age_days(c, today):
    """Days since the complaint was reported, until it was closed."""
    return ((c.closed_on or today) - c.reported_on).days


def awaiting_days(c, today):
    """Days spent in Awaiting material (the paused clock), summed from the events in date order."""
    total, since = 0, None
    for ev in c.events.all():
        if since is not None and ev.to_status != Status.AWAITING_MATERIAL:
            total += (ev.at - since).days
            since = None
        if ev.to_status == Status.AWAITING_MATERIAL and since is None:
            since = ev.at
    if since is not None:
        total += ((c.closed_on or today) - since).days
    return total


def complaint_qs(events=True):
    """Complaints with what a list row or the detail page shows (site, company, technicians, events,
    visits). events=False skips the events query for callers that need only the age, not awaiting days."""
    prefetch = ["technicians"]
    if events:
        prefetch.append(Prefetch("events", queryset=ComplaintEvent.objects.select_related("by")))
    return (
        Complaint.objects.select_related("site", "company")
        .prefetch_related(*prefetch)
        .annotate(n_visits=Count("visits", distinct=True), last_visit=Max("visits__visit_date"))
    )


def complaint_visits(c):
    """A complaint's visits, newest first, with the parts-given OUT (and its undo), lines and pieces."""
    return list(
        c.visits.select_related("out_entry", "out_entry__reversed_by").prefetch_related(
            "technicians",
            "out_entry__lines__item",
            Prefetch("pieces", queryset=DefectivePiece.objects.select_related("item").order_by("id")),
        )
    )


def site_option(site):
    """What the site picker needs for one site."""
    return {
        "id": site.pk,
        "name": site.name,
        "city": site.city,
        "contact": site.contact_name,
        "phone": site.phone,
        "phone_display": format_phone(site.phone),  # what the picker types into the phone box
    }


def site_options():
    return [site_option(s) for s in Site.objects.filter(is_active=True)]


def group_cities(names):
    """[{label, n}] for city names grouped ignoring case (the list filters with city__iexact), most first.
    The first spelling seen is the label. The dashboard and the city dropdown both use this."""
    counts, spelling = Counter(), {}
    for name in names:
        counts[name.lower()] += 1
        spelling.setdefault(name.lower(), name)
    return [
        {"label": spelling[key], "n": n} for key, n in sorted(counts.items(), key=lambda kv: (-kv[1], kv[0]))
    ]


def cities():
    """Distinct city names for the filter dropdown, A to Z; "Vizag" and "vizag" are one option."""
    names = Site.objects.order_by("id").values_list("city", flat=True)
    return sorted((c["label"] for c in group_cities(names)), key=str.lower)


def complaint_search_q(q):
    """Free-text match shared by the complaints list and the global search: complaint no., company ref, site,
    fault, contact name, and (when q looks like a phone number) the digits of the phone."""
    cond = (
        Q(number__icontains=q)
        | Q(company_ref__icontains=q)
        | Q(site__name__icontains=q)
        | Q(fault__icontains=q)
        | Q(contact_name__icontains=q)
    )
    digits = re.sub(r"\D", "", q)
    if len(digits) >= 4 and re.fullmatch(r"[\d\s+\-]+", q):
        cond |= Q(phone__contains=digits)
    return cond


def age_bucket(days):
    for key, _, low, high in AGE_BUCKETS:
        if days >= low and (high is None or days <= high):
            return key
    return AGE_BUCKETS[0][0]


def in_tab(c, tab):
    if tab == "all":
        return True
    if tab == "open":
        return c.status in OPEN_STATUSES
    if tab == FINISHED:
        return c.status in FINISHED_STATUSES
    return c.status == tab


def complaint_row(c, today, events=True):
    return {
        "c": c,
        "age": age_days(c, today),
        "awaiting": awaiting_days(c, today) if events else None,
        "techs": ", ".join(t.name for t in c.technicians.all()),
    }


def complaint_rows(f, today):
    """(rows, tabs). Rows match every filter; tabs are [(key, label, count)] counted before the tab filter."""
    complaints = complaint_qs()
    if f.company:
        complaints = complaints.filter(company=f.company)
    if f.city:
        complaints = complaints.filter(site__city__iexact=f.city)
    if f.technician:
        complaints = complaints.filter(technicians=f.technician)
    if f.closed_since and f.tab in CLOSED_SINCE_TABS:  # the open tabs ignore it
        complaints = complaints.filter(closed_on__gt=f.closed_since)
    if f.q:
        complaints = complaints.filter(complaint_search_q(f.q))
    rows = [complaint_row(c, today) for c in complaints]
    if f.age:
        rows = [r for r in rows if age_bucket(r["age"]) == f.age]
    tabs = [(key, TAB_LABELS[key], sum(1 for r in rows if in_tab(r["c"], key))) for key in TABS]
    return [r for r in rows if in_tab(r["c"], f.tab)], tabs


def status_counts():
    """{status: number of complaints} for every status (0 when none)."""
    counts = dict(Complaint.objects.values_list("status").annotate(n=Count("id")))
    return {s: counts.get(s, 0) for s in Status.values}


def open_rows(today, events=False):
    """Row dicts for every open complaint. Age needs no events; pass events=True for awaiting days too."""
    qs = complaint_qs(events=events).filter(status__in=OPEN_STATUSES)
    return [complaint_row(c, today, events=events) for c in qs]


def age_counts(rows):
    """[{key, label, n, alert}] for the age buckets over some rows."""
    return [
        {
            "key": key,
            "label": label,
            "n": sum(1 for r in rows if age_bucket(r["age"]) == key),
            "alert": key == AGE_BUCKETS[-1][0],
        }
        for key, label, _, _ in AGE_BUCKETS
    ]


def closed_since_count(since):
    """Complaints Closed or Not covered after `since` (what the dashboard's tile and its link list)."""
    return Complaint.objects.filter(status__in=FINISHED_STATUSES, closed_on__gt=since).count()


def dashboard(today):
    """Figures for the complaints dashboard. Every count is what its link's list shows: open figures come from
    the open complaints, "closed in the last 30 days" is closed_on after today - 30 days."""
    rows = open_rows(today)
    since = today - timedelta(days=30)
    ages = age_counts(rows)
    companies = Counter((r["c"].company_id, r["c"].company.name) for r in rows)
    cities = group_cities(r["c"].site.city for r in rows)
    return {
        "counts": status_counts(),
        "open": len(rows),
        "closed_30": closed_since_count(since),
        "since": since,
        "ages": ages,
        "ages_top": max([a["n"] for a in ages] + [1]),
        "oldest": sorted(rows, key=lambda r: (-r["age"], r["c"].number))[:6],
        "companies": [
            {"id": cid, "label": name, "n": n}
            for (cid, name), n in sorted(companies.items(), key=lambda kv: (-kv[1], kv[0][1]))
        ],
        "companies_top": max(list(companies.values()) + [1]),
        "cities": cities,
        "cities_top": max([c["n"] for c in cities] + [1]),
    }
