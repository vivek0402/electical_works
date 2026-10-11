from django.apps import AppConfig
from django.db.models.signals import post_migrate


class AccountsConfig(AppConfig):
    name = "apps.accounts"
    label = "accounts"

    def ready(self):
        from .roles import sync_role_groups

        # Runs after every migrate, so permissions of models added in later phases
        # are attached to the role groups automatically.
        post_migrate.connect(sync_role_groups, sender=self)
