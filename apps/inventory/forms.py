from django import forms
from django.conf import settings
from django.core.exceptions import NON_FIELD_ERRORS
from django.db.models import Q
from django.utils import timezone

from .models import AdjustReason, Company, FittingType, InSource, Location, OutTarget, SpareType, Unit


class TablerFormMixin:
    """Give every widget Tabler classes; mark invalid fields once the form has been cleaned."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
            if isinstance(field.widget, forms.RadioSelect):
                continue  # rendered by hand as Tabler select-groups
            if isinstance(field.widget, forms.Select):
                css = "form-select"
            elif isinstance(field.widget, forms.CheckboxInput):
                css = "form-check-input"
            else:
                css = "form-control"
            field.widget.attrs["class"] = css

    def full_clean(self):
        super().full_clean()
        for name in self.errors:
            widget = self.fields[name].widget if name in self.fields else None
            if widget is not None:
                widget.attrs["class"] = widget.attrs.get("class", "") + " is-invalid"


class ItemForm(TablerFormMixin, forms.Form):
    code = forms.CharField(
        max_length=80,
        label="Item code",
        widget=forms.TextInput(attrs={"placeholder": "e.g. LG66-040-078-480IT", "autocomplete": "off"}),
    )
    spare_type = forms.ModelChoiceField(SpareType.objects.filter(is_active=True), empty_label="Choose…")
    company = forms.ModelChoiceField(
        Company.objects.filter(is_active=True), label="Company / brand", empty_label=None
    )
    description = forms.CharField(
        max_length=200,
        required=False,
        widget=forms.TextInput(attrs={"placeholder": "e.g. LED driver 40W 480mA"}),
    )
    cat_ref = forms.CharField(
        max_length=80,
        required=False,
        label="Used in fitting (Product Cat Ref)",
        widget=forms.TextInput(attrs={"placeholder": "e.g. LF40-192-060-57-HE", "list": "it-cat-refs"}),
    )
    fitting_type = forms.ModelChoiceField(
        FittingType.objects.filter(is_active=True), required=False, empty_label="None"
    )
    wattage_w = forms.IntegerField(min_value=0, required=False, label="Wattage")
    current_ma = forms.IntegerField(min_value=0, required=False, label="Current")
    unit = forms.ChoiceField(choices=Unit.choices, initial=Unit.NOS)
    reorder_level = forms.IntegerField(min_value=0, initial=0, label="Reorder level")
    aliases = forms.CharField(
        required=False,
        label="Other spellings of this code",
        widget=forms.TextInput(attrs={"placeholder": "e.g. EI08437, EIO-8437"}),
    )
    is_active = forms.BooleanField(required=False, initial=True, label="Active")

    def __init__(self, *args, item=None, **kwargs):
        super().__init__(*args, **kwargs)
        # An item whose master was deactivated later must stay editable.
        if item is not None:
            for name, model, fk in (
                ("spare_type", SpareType, item.spare_type_id),
                ("company", Company, item.company_id),
                ("fitting_type", FittingType, item.fitting_type_id),
            ):
                self.fields[name].queryset = model.objects.filter(Q(is_active=True) | Q(pk=fk))
            # Changing the unit would change the meaning of every quantity already posted.
            if item.lines.exists():
                self.fields["unit"].disabled = True
                self.fields["unit"].initial = item.unit
        self.fields["cat_ref"].widget.attrs["list"] = f"{self.prefix or 'it'}-cat-refs"
        if not self.is_bound and not self.initial.get("company"):
            default = _default_company()
            if default:
                self.fields["company"].initial = default.pk

    def clean_aliases(self):
        return [a.strip() for a in self.cleaned_data["aliases"].split(",") if a.strip()]

    @classmethod
    def initial_from(cls, item):
        return {
            "code": item.code,
            "spare_type": item.spare_type_id,
            "company": item.company_id,
            "description": item.description,
            "cat_ref": item.cat_ref,
            "fitting_type": item.fitting_type_id,
            "wattage_w": item.wattage_w,
            "current_ma": item.current_ma,
            "unit": item.unit,
            "reorder_level": item.reorder_level,
            "aliases": ", ".join(item.aliases.values_list("alias", flat=True)),
            "is_active": item.is_active,
        }


def _default_company():
    return Company.objects.filter(name=settings.DEFAULT_COMPANY, is_active=True).first()


class EntryHeaderForm(TablerFormMixin, forms.Form):
    entry_date = forms.DateField(
        label="Date", widget=forms.DateInput(attrs={"type": "date"}, format="%Y-%m-%d")
    )
    location = forms.ModelChoiceField(Location.objects.filter(is_active=True), empty_label=None)
    note = forms.CharField(
        required=False, label="Remarks", widget=forms.Textarea(attrs={"rows": 2, "placeholder": "Optional"})
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields["entry_date"].widget.attrs["max"] = timezone.localdate().isoformat()

    def clean_entry_date(self):
        value = self.cleaned_data["entry_date"]
        if value > timezone.localdate():
            raise forms.ValidationError("The date can't be in the future.")
        return value

    def first_error(self):
        """The first problem as one sentence, with the field's label when it belongs to a field."""
        name, errors = next(iter(self.errors.items()))
        if name == NON_FIELD_ERRORS:
            return errors[0]
        return f"{self.fields[name].label or name.replace('_', ' ').capitalize()}: {errors[0]}"


class StockInForm(EntryHeaderForm):
    subtype = forms.ChoiceField(
        choices=InSource.choices, initial=InSource.SUPPLIER, widget=forms.RadioSelect, label="Received from"
    )
    company = forms.ModelChoiceField(
        Company.objects.filter(is_active=True),
        required=False,
        label="Supplier / company",
        empty_label="Choose…",
    )
    party = forms.CharField(
        max_length=120,
        required=False,
        label="Site / customer",
        widget=forms.TextInput(attrs={"list": "parties", "placeholder": "e.g. Dr Reddys, Vizag"}),
    )
    ref = forms.CharField(
        max_length=60,
        required=False,
        label="DC / bill no.",
        widget=forms.TextInput(attrs={"placeholder": "e.g. DC 4512"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if not self.is_bound and not self.initial.get("company"):
            default = _default_company()
            if default:
                self.fields["company"].initial = default.pk

    def clean(self):
        data = super().clean()
        source = data.get("subtype")
        if source == InSource.SUPPLIER:
            if not data.get("company"):
                raise forms.ValidationError("Choose the supplier.")
            data["party"] = data["company"].name
        elif source == InSource.RETURN:
            if not data.get("party", "").strip():
                raise forms.ValidationError("Enter the site / customer.")
            data["company"] = None
        elif source == InSource.OPENING:
            data["party"], data["company"] = "Opening stock (first count)", None
        return data


class StockOutForm(EntryHeaderForm):
    subtype = forms.ChoiceField(
        choices=OutTarget.choices, initial=OutTarget.SITE, widget=forms.RadioSelect, label="Issued to"
    )
    party = forms.CharField(
        max_length=120,
        required=False,
        label="Name",
        widget=forms.TextInput(attrs={"list": "parties", "placeholder": "e.g. GMR Airport, Vizag"}),
    )
    ref = forms.CharField(
        max_length=60,
        required=False,
        label="Job / reference no.",
        widget=forms.TextInput(attrs={"placeholder": "Optional"}),
    )

    def clean(self):
        data = super().clean()
        if data.get("subtype") and not data.get("party", "").strip():
            target = OutTarget(data["subtype"]).label.lower()
            raise forms.ValidationError(f"Enter who it was issued to ({target}).")
        return data


class TransferForm(EntryHeaderForm):
    to_location = forms.ModelChoiceField(
        Location.objects.filter(is_active=True), empty_label=None, label="To location"
    )

    def clean(self):
        data = super().clean()
        if data.get("location") and data.get("location") == data.get("to_location"):
            raise forms.ValidationError("From and To locations must be different.")
        return data


class AdjustForm(EntryHeaderForm):
    reason = forms.ChoiceField(choices=[("", "Choose…"), *AdjustReason.choices], required=False)
    note = forms.CharField(
        label="Note",
        widget=forms.Textarea(
            attrs={"rows": 2, "placeholder": "What happened? e.g. 2 lenses cracked in storage"}
        ),
        error_messages={"required": "Write a short note explaining the adjustment."},
    )

    def clean_reason(self):
        if not self.cleaned_data["reason"]:
            raise forms.ValidationError("Choose the reason for the adjustment.")
        return self.cleaned_data["reason"]


class UndoForm(forms.Form):
    # Not required here: undo_entry() gives the friendly "Please give a reason." for a blank one.
    reason = forms.CharField(max_length=200, required=False)
