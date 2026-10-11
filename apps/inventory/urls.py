from django.urls import path

from . import views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("stock/", views.current_stock, name="current_stock"),
    path("low-stock/", views.low_stock, name="low_stock"),
    path("movements/", views.movements, name="movements"),
    path("items/", views.items, name="items"),
    path("items/new/", views.item_new, name="item_new"),
    path("items/quick-create/", views.item_quick_create, name="item_quick_create"),
    path("items/check-code/", views.item_check_code, name="item_check_code"),
    path("items/<int:pk>/", views.item_detail, name="item_detail"),
    path("items/<int:pk>/edit/", views.item_edit, name="item_edit"),
]
