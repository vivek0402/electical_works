"""All reads for the complaints screens. Views call these; no queries in templates."""

from django.db.models import Count, Max, Prefetch

from apps.defectives.models import DefectivePiece

from .models import Complaint, ComplaintEvent, Site, Status


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


def complaint_qs():
    """Complaints with what a list row or the detail page shows (site, company, technicians, events,
    visits)."""
    return (
        Complaint.objects.select_related("site", "company")
        .prefetch_related(
            "technicians", Prefetch("events", queryset=ComplaintEvent.objects.select_related("by"))
        )
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
    }


def site_options():
    return [site_option(s) for s in Site.objects.filter(is_active=True)]


def cities():
    return list(Site.objects.order_by("city").values_list("city", flat=True).distinct())
