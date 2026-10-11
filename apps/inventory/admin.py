from django import forms
from django.contrib import admin

from .models import Item, ItemAlias, Location, StockBalance, StockDocument, StockMovement
from .normalise import normalise_code


class NoDeleteAdmin(admin.ModelAdmin):
    # Master data is deactivated, not deleted (stock history points at it).
    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(Location)
class LocationAdmin(NoDeleteAdmin):
    list_display = ["name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]


class ItemAdminForm(forms.ModelForm):
    class Meta:
        model = Item
        fields = [
            "code",
            "item_type",
            "description",
            "fitting_type",
            "wattage_w",
            "current_ma",
            "brand",
            "unit",
            "reorder_level",
            "is_active",
        ]

    def clean_code(self):
        code = normalise_code(self.cleaned_data["code"])
        if ItemAlias.objects.filter(alias=code).exists():
            raise forms.ValidationError(f"{code} is already an alias of another item.")
        return code


class AliasInlineForm(forms.ModelForm):
    class Meta:
        model = ItemAlias
        fields = ["alias"]

    def clean_alias(self):
        alias = normalise_code(self.cleaned_data["alias"])
        if Item.objects.filter(code=alias).exists():
            raise forms.ValidationError(f"{alias} is already an item code.")
        return alias


class ItemAliasInline(admin.TabularInline):
    model = ItemAlias
    form = AliasInlineForm
    extra = 1


@admin.register(Item)
class ItemAdmin(NoDeleteAdmin):
    form = ItemAdminForm
    inlines = [ItemAliasInline]
    list_display = ["code", "item_type", "description", "wattage_w", "reorder_level", "is_active"]
    list_filter = ["item_type", "is_active", "brand"]
    search_fields = ["code", "aliases__alias", "description", "search_key"]
    readonly_fields = ["search_key", "created_at", "updated_at"]


class ReadOnlyAdmin(admin.ModelAdmin):
    """The ledger is append-only: viewable here, changed only through stock screens."""

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


class StockMovementInline(admin.TabularInline):
    model = StockMovement
    fields = ["item", "location", "bucket", "qty", "batch_code", "pkd_date"]
    readonly_fields = fields
    extra = 0

    def has_add_permission(self, request, obj=None):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False


@admin.register(StockDocument)
class StockDocumentAdmin(ReadOnlyAdmin):
    inlines = [StockMovementInline]
    list_display = ["id", "doc_type", "doc_date", "ref_no", "created_by", "reverses"]
    list_filter = ["doc_type"]
    search_fields = ["ref_no", "reason", "lines__item__code"]
    date_hierarchy = "doc_date"


@admin.register(StockBalance)
class StockBalanceAdmin(ReadOnlyAdmin):
    list_display = ["item", "location", "bucket", "qty", "updated_at"]
    list_filter = ["location", "bucket"]
    search_fields = ["item__code"]
    list_select_related = ["item", "location"]
