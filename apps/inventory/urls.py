from django.urls import path

from . import exports, masters, views

urlpatterns = [
    path("", views.dashboard, name="dashboard"),
    path("stock/", views.current_stock, name="current_stock"),
    path("low-stock/", views.low_stock, name="low_stock"),
    path("movements/", views.movements, name="movements"),
    path("items/", views.items, name="items"),
    path("items/export/", exports.items_xlsx, name="items_xlsx"),
    path("items/new/", views.item_new, name="item_new"),
    path("items/quick-create/", views.item_quick_create, name="item_quick_create"),
    path("items/check-code/", views.item_check_code, name="item_check_code"),
    path("items/<int:pk>/", views.item_detail, name="item_detail"),
    path("items/<int:pk>/export/", exports.item_history_xlsx, name="item_history_xlsx"),
    path("items/<int:pk>/edit/", views.item_edit, name="item_edit"),
    path("stock/export/", exports.current_stock_xlsx, name="current_stock_xlsx"),
    path("movements/export/", exports.movements_xlsx, name="movements_xlsx"),
    path("low-stock/export/", exports.low_stock_xlsx, name="low_stock_xlsx"),
    path("stock/in/", views.stock_in, name="stock_in"),
    path("stock/out/", views.stock_out, name="stock_out"),
    path("stock/transfer/", views.transfer, name="transfer"),
    path("stock/adjust/", views.adjust, name="adjust"),
    path("search/", views.global_search, name="global_search"),
    path("masters/", masters.masters, name="masters"),
    path("masters/add/", masters.master_add, name="master_add"),
    path("masters/toggle/", masters.masters_toggle, name="masters_toggle"),
    path("entries/<str:number>/", views.entry_detail, name="entry_detail"),
    path("entries/<str:number>/undo/", views.entry_undo, name="entry_undo"),
]
