import os

from django.contrib.auth.models import Group, User
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from apps.accounts.roles import ADMIN, OFFICE, sync_role_groups

SEED_USERS = [("admin", "Admin", ADMIN, True), ("office", "Office", OFFICE, False)]


class Command(BaseCommand):
    help = "Create the role groups and the default users. Re-runnable: existing passwords are kept."

    @transaction.atomic
    def handle(self, *args, **options):
        password = os.environ.get("SEED_PASSWORD")
        if not password:
            raise CommandError("Set SEED_PASSWORD in the environment (.env) before seeding.")
        sync_role_groups()
        for username, first_name, role, superuser in SEED_USERS:
            user, created = User.objects.get_or_create(username=username, defaults={"first_name": first_name})
            if created:
                user.set_password(password)
            user.is_staff = user.is_superuser = superuser
            user.save()
            user.groups.add(Group.objects.get(name=role))
            self.stdout.write(f"{username:<8} {role:<7} {'created' if created else 'exists'}")
