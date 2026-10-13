from django.urls import path

from . import views

urlpatterns = [
    path("defectives/mark/", views.mark_defective, name="mark_defective"),
    path("defectives/pieces/<str:tag>/", views.piece_detail, name="piece_detail"),
    path("defectives/batches/", views.return_batches, name="return_batches"),
    path("defectives/batches/new/", views.batch_new, name="batch_new"),
    path("defectives/batches/<str:number>/", views.batch_detail, name="batch_detail"),
    path("defectives/batches/<str:number>/add/", views.batch_add, name="batch_add"),
    path("defectives/batches/<str:number>/remove/", views.batch_remove, name="batch_remove"),
    path("defectives/batches/<str:number>/dispatch/", views.batch_dispatch, name="batch_dispatch"),
    path("defectives/batches/<str:number>/settle/", views.batch_settle, name="batch_settle"),
]
