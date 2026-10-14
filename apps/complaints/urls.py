from django.urls import path

from . import views

urlpatterns = [
    path("complaints/new/", views.complaint_new, name="complaint_new"),
    path("complaints/<str:number>/", views.complaint_detail, name="complaint_detail"),
    path("complaints/<str:number>/visit/", views.visit_new, name="visit_new"),
    path("complaints/<str:number>/status/", views.complaint_status, name="complaint_status"),
    path("complaints/<str:number>/not-covered/", views.complaint_not_covered, name="complaint_not_covered"),
    path(
        "complaints/<str:number>/visits/<str:visit>/undo-parts/",
        views.visit_undo_parts,
        name="visit_undo_parts",
    ),
    path("sites/quick-create/", views.site_quick_create, name="site_quick_create"),
]
