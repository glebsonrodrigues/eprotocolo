from django.urls import path
from . import views

from .views_password_reset import (
    PasswordResetView,
    PasswordResetDoneView,
    PasswordResetConfirmView,
    PasswordResetCompleteView,
)

urlpatterns = [
    # Login / Logout
    path("login/", views.login_view, name="login"),
    path("logout/", views.logout_view, name="logout"),

    # Usuários
    path("usuarios/", views.usuarios_list, name="usuarios_list"),
    path("usuarios/novo/", views.usuario_create, name="usuario_create"),
    path("usuarios/<int:pk>/editar/", views.usuario_update, name="usuario_update"),

    # =========================
    # RESET DE SENHA
    # =========================
    path("password-reset/", PasswordResetView.as_view(), name="password_reset"),
    path("password-reset/done/", PasswordResetDoneView.as_view(), name="password_reset_done"),
    path("reset/<uidb64>/<token>/", PasswordResetConfirmView.as_view(), name="password_reset_confirm"),
    path("reset/done/", PasswordResetCompleteView.as_view(), name="password_reset_complete"),
]
