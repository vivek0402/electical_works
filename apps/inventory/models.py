from django.db import models


class Location(models.Model):
    """A place that holds stock (store, office, shop…).

    Deactivate, never delete, once it has history.
    """

    name = models.CharField(max_length=80, unique=True)
    is_active = models.BooleanField(default=True)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["name"]

    def __str__(self):
        return self.name
