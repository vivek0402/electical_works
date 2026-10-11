"""The three roles, as Django Groups. Role checks are enforced server-side via `role_required`."""

from django.contrib.auth.models import Group, Permission

ADMIN = "ADMIN"
OFFICE = "OFFICE"
TECHNICIAN = "TECHNICIAN"
ROLES = (ADMIN, OFFICE, TECHNICIAN)

# Model permissions granted to each role ("app_label.codename"). ADMIN gets every permission.
# Extend this as each phase adds models; `sync_role_groups` re-applies it after every migrate.
ROLE_PERMISSIONS = {
    OFFICE: [
        "inventory.view_location",
        "inventory.view_item",
        "inventory.add_item",
        "inventory.change_item",
        "inventory.view_itemalias",
        "inventory.add_itemalias",
        "inventory.view_stockdocument",
        "inventory.view_stockmovement",
        "inventory.view_stockbalance",
    ],
    TECHNICIAN: [
        "inventory.view_location",
        "inventory.view_item",
        "inventory.view_stockbalance",
    ],
}


def sync_role_groups(**kwargs):
    """Create the role groups and set their permissions. Idempotent; connected to post_migrate."""
    for role in ROLES:
        group, _ = Group.objects.get_or_create(name=role)
        if role == ADMIN:
            group.permissions.set(Permission.objects.all())
            continue
        perms = []
        for dotted in ROLE_PERMISSIONS.get(role, []):
            app_label, codename = dotted.split(".")
            perms.extend(
                Permission.objects.filter(content_type__app_label=app_label, codename=codename)
            )
        group.permissions.set(perms)


def user_roles(user):
    """Set of role names the user holds. Superusers count as ADMIN."""
    if not user.is_authenticated:
        return set()
    if not hasattr(user, "_role_cache"):
        roles = set(user.groups.filter(name__in=ROLES).values_list("name", flat=True))
        if user.is_superuser:
            roles.add(ADMIN)
        user._role_cache = roles
    return user._role_cache


def has_role(user, *roles):
    """True if the user holds any of `roles`. ADMIN may do everything."""
    held = user_roles(user)
    return ADMIN in held or bool(held.intersection(roles))
