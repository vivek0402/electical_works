from django.contrib import admin
from django.urls import include, path

admin.site.site_header = "SVKML Electrical Works — Admin"
admin.site.site_title = "SVKML Admin"
admin.site.index_title = "Masters"

urlpatterns = [
    path("admin/", admin.site.urls),
    path("", include("apps.accounts.urls")),
    path("", include("apps.core.urls")),
]
