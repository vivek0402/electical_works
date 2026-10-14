from django import forms
from django.conf import settings
from django.utils import timezone

from apps.inventory.forms import TablerFormMixin
from apps.inventory.models import Company, Location

from .models import Priority, Site, Status, Technician
from .phones import normalise_phone
from .services import visit_next_options

DATE = forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
PHONE_TYPED_MAX = (
    16  # '+91 98765 43210' or '0891-2345678' as typed; stored as digits (phones.normalise_phone)
)


def phone_widget(placeholder="10-digit mobile or STD landline"):
    return forms.TextInput(
        attrs={
            "type": "tel",
            "inputmode": "tel",
            "maxlength": PHONE_TYPED_MAX,
            "autocomplete": "off",
            "placeholder": placeholder,
        }
    )


class PhoneMixin:
    """`phone` as stored (digits), with the friendly message when it is neither a mobile nor a landline."""

    def clean_phone(self):
        try:
            return normalise_phone(self.cleaned_data["phone"], allow_landline=True)
        except ValueError as exc:
            raise forms.ValidationError(str(exc)) from exc


class ComplaintForm(PhoneMixin, TablerFormMixin, forms.Form):
    """New complaint. Site and technician fields accept hidden ones too, so a page opened before one was
    hidden gets the service's message ("… is hidden"), while the lists only offer active ones."""

    site = forms.ModelChoiceField(
        Site.objects.all(),
        error_messages={"required": "Choose the site.", "invalid_choice": "Choose the site."},
    )
    contact_name = forms.CharField(
        max_length=80,
        required=False,
        label="Contact person",
        widget=forms.TextInput(attrs={"placeholder": "Filled from the site"}),
    )
    phone = forms.CharField(max_length=PHONE_TYPED_MAX, required=False, widget=phone_widget())
    company = forms.ModelChoiceField(
        Company.objects.filter(is_active=True),
        label="Company (whose product failed)",
        empty_label=None,
        widget=forms.Select(attrs={"data-ts": ""}),
        error_messages={"invalid_choice": "Choose the company whose product failed."},
    )
    company_ref = forms.CharField(
        max_length=60,
        required=False,
        label="Company complaint no.",
        widget=forms.TextInput(attrs={"placeholder": "The company's ticket no., if any"}),
    )
    reported_on = forms.DateField(
        label="Reported on",
        widget=DATE,
        error_messages={"required": "Choose the date the complaint was reported."},
    )
    qty_affected = forms.IntegerField(
        min_value=1,
        required=False,
        label="Qty affected",
        widget=forms.NumberInput(
            attrs={"min": 1, "step": 1, "inputmode": "numeric", "placeholder": "e.g. 6"}
        ),
        error_messages={"min_value": "Quantity affected must be a whole number of 1 or more."},
    )
    fault = forms.CharField(
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "e.g. 6 linear fittings flickering on the 2nd floor"}
        ),
        error_messages={"required": "Describe the fault."},
    )
    priority = forms.ChoiceField(choices=Priority.choices, initial=Priority.NORMAL, widget=forms.RadioSelect)
    technicians = forms.ModelMultipleChoiceField(
        Technician.objects.all(),
        required=False,
        widget=forms.SelectMultiple(attrs={"data-ts": "", "placeholder": "Assign now or later"}),
        error_messages={"invalid_choice": "Choose technicians from the list."},
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["reported_on"].widget.attrs["max"] = timezone.localdate().isoformat()
        # Offer only active sites and technicians (the fields accept any, so the service names a hidden one).
        # site-picker.js rebuilds the site list from sites-data, which is also active-only.
        self.fields["site"].widget.choices = [("", "")] + [
            (s.pk, str(s)) for s in Site.objects.filter(is_active=True)
        ]
        self.fields["technicians"].widget.choices = [
            (t.pk, t.name) for t in Technician.objects.filter(is_active=True)
        ]
        if not self.is_bound and not self.initial.get("company"):
            default = Company.objects.filter(name=settings.DEFAULT_COMPANY, is_active=True).first()
            if default:
                self.fields["company"].initial = default.pk


class SiteForm(PhoneMixin, TablerFormMixin, forms.Form):
    """The New site modal (prefix "ns", so its ids don't clash with the complaint form's)."""

    name = forms.CharField(
        max_length=120,
        label="Site name",
        error_messages={"required": "Enter the site name."},
        widget=forms.TextInput(attrs={"placeholder": "e.g. Andhra University", "autocomplete": "off"}),
    )
    city = forms.CharField(
        max_length=60,
        error_messages={"required": "Enter the city."},
        widget=forms.TextInput(attrs={"list": "site-cities", "placeholder": "e.g. Visakhapatnam"}),
    )
    contact_name = forms.CharField(
        max_length=80,
        required=False,
        label="Contact person",
        widget=forms.TextInput(attrs={"placeholder": "Name at the site"}),
    )
    phone = forms.CharField(max_length=PHONE_TYPED_MAX, required=False, widget=phone_widget())
    address = forms.CharField(
        required=False, widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional"})
    )


class VisitForm(TablerFormMixin, forms.Form):
    """The visit header. The two item tables (parts given, failed parts collected) are parsed separately
    (entry_lines). Technicians accept hidden ones too, so a page opened before one was hidden gets the
    service's message ("… is hidden"), while the list only offers active ones."""

    visit_date = forms.DateField(
        label="Visit date", widget=DATE, error_messages={"required": "Choose the visit date."}
    )
    technicians = forms.ModelMultipleChoiceField(
        Technician.objects.all(),
        label="Technicians who attended",
        widget=forms.SelectMultiple(attrs={"data-ts": "", "placeholder": "Choose who attended"}),
        error_messages={
            "required": "Choose who attended.",
            "invalid_choice": "Choose technicians from the list.",
        },
    )
    work_done = forms.CharField(
        label="Work done",
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "e.g. Changed 2 drivers, 4 fittings still to check"}
        ),
        error_messages={"required": "Write what work was done."},
    )
    location = forms.ModelChoiceField(
        Location.objects.good().filter(is_active=True),
        empty_label=None,
        label="From location",
        error_messages={"invalid_choice": "Choose a good-stock location for the parts given."},
    )
    next_status = forms.ChoiceField(
        label="Status after this visit",
        widget=forms.RadioSelect,
        error_messages={
            "required": "Choose the status after the visit.",
            "invalid_choice": "Choose one of the statuses offered.",
        },
    )

    def __init__(self, *args, complaint, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["next_status"].choices = [(s, Status(s).label) for s in visit_next_options(complaint)]
        self.fields["visit_date"].widget.attrs.update(
            min=complaint.reported_on.isoformat(), max=timezone.localdate().isoformat()
        )
        self.fields["technicians"].widget.choices = [
            (t.pk, t.name) for t in Technician.objects.filter(is_active=True)
        ]


class TechnicianForm(TablerFormMixin, forms.Form):
    """Add or edit a technician. The phone is a mobile only (the service checks it)."""

    name = forms.CharField(
        max_length=60,
        error_messages={"required": "Enter the name of the technician."},
        widget=forms.TextInput(attrs={"placeholder": "e.g. Suresh", "autocomplete": "off"}),
    )
    phone = forms.CharField(
        max_length=PHONE_TYPED_MAX, required=False, widget=phone_widget(placeholder="10-digit mobile")
    )
