from django.db import migrations

NAME = "Defective store"


def create(apps, schema_editor):
    """Create the Defective store. There is exactly one.

    Location names are unique ignoring case, so if a location called "Defective store" (any case)
    already exists it is reused, but only when no stock line has ever been posted there. A used one
    holds good stock that would silently drop out of every good-stock figure once flagged, so the
    migration stops with a RuntimeError and the location must be renamed first.
    """
    Location = apps.get_model("inventory", "Location")
    StockLine = apps.get_model("inventory", "StockLine")
    place = Location.objects.filter(name__iexact=NAME).first()
    if place is None:
        place = Location(name=NAME)
    elif StockLine.objects.filter(location=place).exists():
        raise RuntimeError(
            f'A location named "{place.name}" already has stock entries, so it cannot become the '
            "Defective store. Rename that location (e.g. in the masters page), then run migrate again."
        )
    place.is_defective_store = True
    place.is_active = True
    place.save()


def unflag(apps, schema_editor):
    apps.get_model("inventory", "Location").objects.filter(is_defective_store=True).update(
        is_defective_store=False
    )


class Migration(migrations.Migration):
    dependencies = [("inventory", "0005_defective_store")]
    operations = [migrations.RunPython(create, unflag)]
