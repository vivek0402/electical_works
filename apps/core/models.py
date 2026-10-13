from django.db import models


class Counter(models.Model):
    """Last number used per document series (DEF, RB, CMP, VIS). Locked while a number is taken."""

    prefix = models.CharField(max_length=4, primary_key=True)
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.prefix}: {self.last}"
