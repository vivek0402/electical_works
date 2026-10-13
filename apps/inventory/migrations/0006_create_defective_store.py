from django.db import migrations

NAME = "Defective store"


def create(apps, schema_editor):
    """Create (or flag an existing, same-named) Defective store. There is exactly one."""
    Location = apps.get_model("inventory", "Location")
    place = Location.objects.filter(name__iexact=NAME).first() or Location(name=NAME)
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
