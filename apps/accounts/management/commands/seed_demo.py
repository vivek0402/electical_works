import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.models import Profile
from apps.accounts.roles import ADMIN, OFFICE, TECHNICIAN, sync_role_groups

# OPEN QUESTION Q10: the client's real user list. Until confirmed: these defaults.
SEED_USERS = [
    {"username": "admin", "first_name": "Admin", "role": ADMIN, "superuser": True},
    {"username": "office", "first_name": "Office", "role": OFFICE},
    {"username": "ramu", "first_name": "Ramu", "role": TECHNICIAN},
    {"username": "apparao", "first_name": "Apparao", "role": TECHNICIAN},
]


class Command(BaseCommand):
    help = "Create the role groups and default users. Safe to re-run: existing passwords are kept."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get("SEED_PASSWORD")
        if not password:
            raise CommandError("Set SEED_PASSWORD in the environment (.env) before seeding.")

        sync_role_groups()
        for spec in SEED_USERS:
            superuser = spec.get("superuser", False)
            user, created = User.objects.get_or_create(
                username=spec["username"],
                defaults={"first_name": spec["first_name"]},
            )
            if created:
                user.set_password(password)
            user.is_staff = superuser
            user.is_superuser = superuser
            user.save()
            user.groups.add(Group.objects.get(name=spec["role"]))
            Profile.objects.get_or_create(user=user)
            verb = "created" if created else "exists"
            self.stdout.write(f"{spec['username']:<10} {spec['role']:<11} {verb}")
        self.stdout.write(self.style.SUCCESS("Seed complete."))
