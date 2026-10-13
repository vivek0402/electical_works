from django.contrib.auth.models import Group, User
from django.utils import timezone

from apps.inventory.models import Company, EntryKind, Item, Location, SpareType
from apps.inventory.services import Line, post_entry

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


def give_stock(item, qty, user, place=None):
    """A supplier Stock IN of `qty` at `place` (default Vizag Office), dated today."""
    return post_entry(
        kind=EntryKind.IN,
        entry_date=timezone.localdate(),
        lines=[Line(item, place or loc(), qty)],
        user=user,
        subtype="SUPPLIER",
        party="Test supplier",
    )


def make_pieces(item, qty, user, fault="no output"):
    """`qty` tagged pieces in the Defective store: stocked at Vizag Office, then marked defective."""
    from apps.defectives.services import mark_defective

    give_stock(item, qty, user)
    _, pieces = mark_defective(
        location=loc(), lines=[(item, qty, fault)], entry_date=timezone.localdate(), user=user
    )
    return pieces


def make_site(name="BARC", city="Visakhapatnam", **extra):
    """A site (reused if one with exactly this name and city exists)."""
    from apps.complaints.models import Site

    return Site.objects.get_or_create(name=name, city=city, defaults=extra)[0]


def make_tech(name="Ramu", **extra):
    from apps.complaints.models import Technician

    return Technician.objects.get_or_create(name=name, defaults=extra)[0]
