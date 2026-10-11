from django.contrib import admin
from django.contrib.auth.admin import UserAdmin as BaseUserAdmin
from django.contrib.auth.models import User

from .models import Profile


class ProfileInline(admin.StackedInline):
    model = Profile
    can_delete = False


class UserAdmin(BaseUserAdmin):
    # Replaces the stock User admin: adds home location and shows roles in the list.
    inlines = [ProfileInline]
    list_display = ["username", "first_name", "last_name", "role_names", "is_active"]
    list_filter = ["groups", "is_active"]

    @admin.display(description="Roles")
    def role_names(self, obj):
        return ", ".join(g.name for g in obj.groups.all())

    def get_queryset(self, request):
        return super().get_queryset(request).prefetch_related("groups")


admin.site.unregister(User)
admin.site.register(User, UserAdmin)
