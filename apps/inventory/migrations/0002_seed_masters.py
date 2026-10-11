from django.db import migrations

SEED = {
    "Location": ["Vizag Office", "Svkml", "TV Shop", "Kartika Class"],
    "Company": ["Wipro Lighting", "Finolex Cables", "Havells", "Sri Sai Electricals", "Lakshmi Traders"],
    "FittingType": [
        "Flood light",
        "Linear / batten",
        "Street light",
        "High bay",
        "Downlight",
        "Well glass",
        "Bulkhead",
        "Panel",
    ],
    "SpareType": [
        "Driver",
        "PCB / LED module",
        "Lens",
        "Complete fitting",
        "Controller",
        "Switch",
        "Wire / cable",
        "Accessory",
        "Other",
    ],
}


def seed(apps, schema_editor):
    for model, names in SEED.items():
        Model = apps.get_model("inventory", model)
        for name in names:
            Model.objects.get_or_create(name=name)


def unseed(apps, schema_editor):
    for model, names in SEED.items():
        apps.get_model("inventory", model).objects.filter(name__in=names).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0001_initial")]
    operations = [migrations.RunPython(seed, unseed)]
