from django.db import models


class Counter(models.Model):
    """Last number used per document series (DEF, RB, CMP, VIS). Locked while a number is taken."""

    prefix = models.CharField(max_length=4, primary_key=True)
    last = models.PositiveIntegerField(default=0)

    def __str__(self):
        return f"{self.prefix}: {self.last}"


class TokenClaim(models.Model):
    """A one-time form token that a save has claimed (see tokens.guarded_post).

    The row is inserted inside the saving transaction, so a second request carrying the same token waits for
    the first to finish and then finds this row instead of saving again. `saved` is what the first request
    saved (an entry number or a URL), so the second can be sent to it. A refused save rolls the row back,
    leaving the token free for a retry. Old rows are pruned as new ones are written."""

    token = models.CharField(max_length=64, primary_key=True)
    action = models.CharField(max_length=64)  # the fingerprint of what was posted
    saved = models.TextField(blank=True)
    created_at = models.DateTimeField(auto_now_add=True, db_index=True)

    def __str__(self):
        return f"{self.token[:8]}… {self.saved}"
