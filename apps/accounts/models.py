from django.conf import settings
from django.db import models


class Profile(models.Model):
    """Extra per-user fields; the built-in User stays untouched."""

    user = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="profile"
    )
    home_location = models.ForeignKey(
        "inventory.Location",
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        help_text="Default stock location for this user (e.g. a technician's store).",
    )

    def __str__(self):
        return f"Profile of {self.user}"
