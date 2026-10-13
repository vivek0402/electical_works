from django import forms

from apps.inventory.forms import EntryHeaderForm
from apps.inventory.models import Location


class MarkDefectiveForm(EntryHeaderForm):
    """Date and the good-stock location the faulty pieces were found at.

    No remarks box: each line has its own fault.
    """

    note = None
    location = forms.ModelChoiceField(
        Location.objects.good().filter(is_active=True), empty_label=None, label="Found at location"
    )
