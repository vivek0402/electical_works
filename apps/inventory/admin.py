from django.contrib import admin

from .models import Location


@admin.register(Location)
class LocationAdmin(admin.ModelAdmin):
    list_display = ["name", "is_active", "created_at"]
    list_filter = ["is_active"]
    search_fields = ["name"]

    def has_delete_permission(self, request, obj=None):
        # Master data is deactivated, not deleted (stock history points at it).
        return False
