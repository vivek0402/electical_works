"""Admin-only page to add and switch off locations, companies, fitting types and spare types."""

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN

from .filters import _text
from .models import Company, FittingType, Location, SpareType, StockBalance

KINDS = {
    "location": (Location, "Locations", "map-pin"),
    "company": (Company, "Suppliers / companies", "building-store"),
    "fitting_type": (FittingType, "Fitting types", "bulb"),
    "spare_type": (SpareType, "Spare types", "components"),
}
NAME_MAX = Location._meta.get_field("name").max_length


@role_required(ADMIN)
def masters(request):
    if request.method == "POST":
        model, label, _ = KINDS.get(request.POST.get("kind"), (None, "", ""))
        name = " ".join(_text(request.POST.get("name")).split())
        if model is None or not name:
            messages.error(request, "Unknown list." if model is None else "Type a name.")
        elif len(name) > NAME_MAX:
            messages.error(request, f"That name is too long (most {NAME_MAX} characters).")
        elif model.objects.filter(name__iexact=name).exists():
            messages.error(request, f"{name} already exists in {label.lower()}.")
        else:
            try:
                with transaction.atomic():
                    model.objects.create(name=name)
            except IntegrityError:  # someone added the same name a moment ago
                messages.error(request, f"{name} already exists in {label.lower()}.")
            else:
                messages.success(request, f"Added {name}.")
        return redirect("masters")
    groups = [
        (key, label, icon, model.objects.order_by("-is_active", "name"))
        for key, (model, label, icon) in KINDS.items()
    ]
    return render(request, "inventory/masters.html", {"groups": groups, "name_max": NAME_MAX})


def _refuse_hide(model, label, row):
    """Reason this row may not be hidden, or None."""
    if model is Location and StockBalance.objects.filter(location=row).exclude(qty=0).exists():
        return f"{row.name} still holds stock. Move or adjust it to zero first."
    if model is Company and row.name == settings.DEFAULT_COMPANY:
        return f"{row.name} is the default supplier and can't be hidden."
    if model in (Location, Company) and not model.objects.filter(is_active=True).exclude(pk=row.pk).exists():
        return f"At least one {'location' if model is Location else 'company'} must stay active."
    return None


@role_required(ADMIN)
@require_POST
def masters_toggle(request):
    model, label, _ = KINDS.get(request.POST.get("kind"), (None, "", ""))
    row = None
    if model is not None:
        try:
            row = model.objects.filter(pk=request.POST.get("pk")).first()
        except (ValueError, TypeError):
            row = None
    if row is None:
        messages.error(request, "Nothing to change.")
    elif row.is_active and (reason := _refuse_hide(model, label, row)):
        messages.error(request, reason)
    else:
        row.is_active = not row.is_active
        row.save(update_fields=["is_active"])
        messages.success(request, f"{row.name} is now {'active' if row.is_active else 'hidden from forms'}.")
    return redirect("masters")
