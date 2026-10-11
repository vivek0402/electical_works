"""The two roles, as Django Groups. Views enforce them with `role_required`."""

from django.contrib.auth.models import Group, Permission

ADMIN = "ADMIN"
OFFICE = "OFFICE"
ROLES = (ADMIN, OFFICE)


def sync_role_groups(**kwargs):
    """Create the role groups. ADMIN gets every model permission (for the Django admin). Idempotent."""
    for role in ROLES:
        group, _ = Group.objects.get_or_create(name=role)
        if role == ADMIN:
            group.permissions.set(Permission.objects.all())


def user_roles(user):
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
