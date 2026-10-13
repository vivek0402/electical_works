from django.contrib.auth.models import Group, User

from apps.inventory.models import Company, Item, Location, SpareType

PASSWORD = "test-pass-123"


def make_user(username, role=None, superuser=False):
    user = User.objects.create_user(username=username, password=PASSWORD, first_name=username.title())
    if superuser:
        user.is_staff = user.is_superuser = True
        user.save()
    if role:
        user.groups.add(Group.objects.get(name=role))
    return user


def loc(name="Vizag Office"):
    return Location.objects.get(name=name)


def store():
    """The Defective store (created by migration inventory 0006)."""
    return Location.defective_store()


def make_item(code, unit="NOS", reorder=0, spare_type="Driver", company="Wipro Lighting", **extra):
    """search_key is recomputed by Item.save(), so it is not passed here."""
    return Item.objects.create(
        code=code,
        unit=unit,
        reorder_level=reorder,
        spare_type=SpareType.objects.get(name=spare_type),
        company=Company.objects.get(name=company),
        **extra,
    )
