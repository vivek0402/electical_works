"""Admin-only page to add and switch off locations, companies, fitting types and spare types."""

from django.contrib import messages
from django.db import IntegrityError, transaction
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN

from .filters import _text
from .models import Company, FittingType, Location, SpareType

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
            messages.error(request, "Type a name.")
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


@role_required(ADMIN)
@require_POST
def masters_toggle(request):
    model = KINDS.get(request.POST.get("kind"), (None,))[0]
    if model is not None:
        try:
            row = model.objects.filter(pk=request.POST.get("pk")).first()
        except (ValueError, TypeError):
            row = None
        if row:
            row.is_active = not row.is_active
            row.save(update_fields=["is_active"])
            messages.success(
                request, f"{row.name} is now {'active' if row.is_active else 'hidden from forms'}."
            )
    return redirect("masters")
