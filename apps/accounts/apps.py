from django.apps import AppConfig
from django.db.models.signals import m2m_changed, post_migrate


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        from .roles import sync_role_groups

        # No `sender=`: this app has no models, so Django never emits post_migrate for it.
        # Running after every app's migrate (idempotent) also attaches permissions of later apps.
        post_migrate.connect(sync_role_groups, dispatch_uid="accounts.sync_role_groups")

        from django.contrib.auth.models import User

        from .roles import sync_staff_flag

        m2m_changed.connect(
            sync_staff_flag, sender=User.groups.through, dispatch_uid="accounts.sync_staff_flag"
        )
