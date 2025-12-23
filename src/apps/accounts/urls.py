from django.urls import path
from . import views

urlpatterns = [
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    path("usuarios/", views.usuarios_list, name="usuarios_list"),
    path("usuarios/novo/", views.usuario_create, name="usuario_create"),
    path("usuarios/<int:pk>/editar/", views.usuario_update, name="usuario_update"),
]
