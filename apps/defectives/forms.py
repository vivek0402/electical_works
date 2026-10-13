from django import forms

from apps.inventory.forms import EntryHeaderForm, TablerFormMixin
from apps.inventory.models import Location

from .models import GOOD_OUTCOMES, Outcome
from .services import COURIER_MAX, DOCKET_MAX

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")


class MarkDefectiveForm(EntryHeaderForm):
    """Date and the good-stock location the faulty pieces were found at.

    No remarks box: each line has its own fault.
    """

    note = None
    location = forms.ModelChoiceField(
        Location.objects.good().filter(is_active=True), empty_label=None, label="Found at location"
    )


class DispatchForm(TablerFormMixin, forms.Form):
    """Parses the dispatch modal. The service gives the friendly messages for empty courier / docket."""

    dispatched_on = forms.DateField(
        label="Dispatch date", widget=DATE, error_messages={"required": "Choose the dispatch date."}
    )
    courier = forms.CharField(max_length=COURIER_MAX, required=False)
    docket_no = forms.CharField(max_length=DOCKET_MAX, required=False, label="Docket / LR no.")


class SettleForm(TablerFormMixin, forms.Form):
    """Parses the settle panel. Missing outcome / date / location get the service's messages."""

    outcome = forms.ChoiceField(choices=Outcome.choices, required=False, widget=forms.RadioSelect)
    settled_on = forms.DateField(required=False, label="Date answered", widget=DATE)
    to_location = forms.ModelChoiceField(
        Location.objects.good().filter(is_active=True), required=False, label="Goes into location"
    )

    def clean(self):
        data = super().clean()
        if data.get("outcome") not in GOOD_OUTCOMES:
            data["to_location"] = None  # only a replacement or repair goes into a good location
        return data
