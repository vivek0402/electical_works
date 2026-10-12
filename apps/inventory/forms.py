from django import forms
from django.conf import settings
from django.db.models import Q

from .models import Company, FittingType, SpareType, Unit


class TablerFormMixin:
    """Give every widget Tabler classes; mark invalid fields once the form has been cleaned."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for field in self.fields.values():
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
        self.fields["cat_ref"].widget.attrs["list"] = f"{self.prefix or 'it'}-cat-refs"
        if not self.is_bound and not self.initial.get("company"):
            default = Company.objects.filter(name=settings.DEFAULT_COMPANY, is_active=True).first()
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
