"""Admin-only page to add and switch off locations, companies, fitting types and spare types."""

from django.conf import settings
from django.contrib import messages
from django.db import IntegrityError, transaction
from django.http import JsonResponse
from django.shortcuts import redirect, render
from django.views.decorators.http import require_POST

from apps.accounts.decorators import role_required
from apps.accounts.roles import ADMIN, OFFICE

from .filters import _text
from .models import Company, FittingType, Location, SpareType, StockBalance
from .services import MasterError, add_master

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
    if model is Location and row.is_defective_store:
        return f"{row.name} holds the defective pieces and can't be hidden."
    if model is Location and StockBalance.objects.filter(location=row).exclude(qty=0).exists():
        return f"{row.name} still holds stock. Move or adjust it to zero first."
    if model is Company and row.name == settings.DEFAULT_COMPANY:
        return f"{row.name} is the default supplier and can't be hidden."
    if model in (Location, Company):
        others = model.objects.filter(is_active=True).exclude(pk=row.pk)
        if model is Location:
            others = others.filter(is_defective_store=False)
        if not others.exists():
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


@role_required(OFFICE)
@require_POST
def master_add(request):
    """Add a master typed into a form picker; returns JSON for the picker."""
    try:
        row, created = add_master(kind=request.POST.get("kind"), name=request.POST.get("name"))
    except MasterError as exc:
        return JsonResponse({"ok": False, "error": exc.message})
    return JsonResponse({"ok": True, "id": row.pk, "name": row.name, "created": created})
