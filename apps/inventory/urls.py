from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("stock/", views.current_stock, name="current_stock"),
    path("low-stock/", views.low_stock, name="low_stock"),
    path("movements/", views.movements, name="movements"),
]
