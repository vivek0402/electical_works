from django import forms

from .models import Company, FittingType, SpareType, Unit


class TablerFormMixin:
    """Give every widget Tabler classes; mark invalid fields."""

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name, field in self.fields.items():
            css = (
                "form-select"
                if isinstance(field.widget, forms.Select)
                else ("form-check-input" if isinstance(field.widget, forms.CheckboxInput) else "form-control")
            )
            if self.errors.get(name):
                css += " is-invalid"
            field.widget.attrs["class"] = css


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
        widget=forms.TextInput(attrs={"placeholder": "e.g. LF40-192-060-57-HE", "list": "cat-refs"}),
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
