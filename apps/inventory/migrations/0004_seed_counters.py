from django.db import migrations

KINDS = ["IN", "OUT", "TRF", "ADJ", "REV"]


def seed(apps, schema_editor):
    Counter = apps.get_model("inventory", "EntryCounter")
    for kind in KINDS:
        Counter.objects.get_or_create(kind=kind)


def unseed(apps, schema_editor):
    apps.get_model("inventory", "EntryCounter").objects.filter(kind__in=KINDS).delete()


class Migration(migrations.Migration):
    dependencies = [("inventory", "0003_ledger")]
    operations = [migrations.RunPython(seed, unseed)]
