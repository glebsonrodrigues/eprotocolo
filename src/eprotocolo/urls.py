from django.contrib import admin
from django.urls import path, include

urlpatterns = [
    # admin pode ficar, mas você não precisa usar
    path("admin/", admin.site.urls),

    path("", include("accounts.urls")),
    path("", include("protocolos.urls")),
]