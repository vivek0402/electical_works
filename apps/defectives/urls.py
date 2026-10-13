from django.urls import path

from . import views

urlpatterns = [
    path("defectives/mark/", views.mark_defective, name="mark_defective"),
]
