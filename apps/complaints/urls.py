from django.urls import path

from . import exports, views

urlpatterns = [
    path("complaints/", views.complaints_dashboard, name="complaints_dashboard"),
    path("complaints/list/", views.complaint_list, name="complaints"),
    path("complaints/export/", exports.complaints_xlsx, name="complaints_xlsx"),
    path("complaints/pending/export/", exports.pending_complaints_xlsx, name="pending_complaints_xlsx"),
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
    path("sites/", views.sites, name="sites"),
    path("sites/quick-create/", views.site_quick_create, name="site_quick_create"),
    path("sites/<int:pk>/", views.site_detail, name="site_detail"),
    path("sites/<int:pk>/edit/", views.site_edit, name="site_edit"),
    path("sites/<int:pk>/toggle/", views.site_toggle, name="site_toggle"),
    path("technicians/", views.technicians, name="technicians"),
    path("technicians/<int:pk>/edit/", views.technician_edit, name="technician_edit"),
    path("technicians/<int:pk>/toggle/", views.technician_toggle, name="technician_toggle"),
]
