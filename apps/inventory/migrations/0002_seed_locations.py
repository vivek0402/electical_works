from django.db import migrations

# Confirmed by the client (one sheet each in Vizag_Store_All_Material_List.xlsx).
LOCATIONS = ["Svkml", "Vizag Office", "TV Shop", "Kartika Class"]


def seed(apps, schema_editor):
    Location = apps.get_model("inventory", "Location")
    for name in LOCATIONS:
        Location.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    Location = apps.get_model("inventory", "Location")
    Location.objects.filter(name__in=LOCATIONS).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]

    operations = [migrations.RunPython(seed, unseed)]
