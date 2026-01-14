from django.urls import path
from . import views

urlpatterns = [
    # Home/Dashboards
    path("", views.home, name="home"),
    path("dashboard/admin/", views.dashboard_admin, name="dashboard_admin"),
    path("dashboard/", views.dashboard_user, name="dashboard_user"),

    # Processos
    path("processos/", views.processos_list, name="processos_list"),
    path("processos/novo/", views.processo_create, name="processo_create"),
    path("processos/<int:pk>/", views.processo_detail, name="processo_detail"),
    path("processos/<int:pk>/visualizar/", views.processo_view, name="processo_view"),
    path("processos/<int:pk>/receber/", views.processo_receber, name="processo_receber"),

    # Caixa
    path("caixa/", views.caixa_entrada, name="caixa_entrada"),

    # Pessoas (Requerentes)
    path("pessoas/", views.pessoas_list, name="pessoas_list"),
    path("pessoas/nova/", views.pessoa_create, name="pessoa_create"),
    path("pessoas/<int:pk>/editar/", views.pessoa_update, name="pessoa_update"),
    path("pessoas/<int:pk>/ativo/", views.pessoa_toggle_ativo, name="pessoa_toggle_ativo"),

    # API
    path("api/pessoas/lookup/", views.pessoa_lookup, name="pessoa_lookup"),

    # ==========================
    # CADASTROS (ADMIN)
    # ==========================
    path("cadastros/tipos/", views.tipos_list, name="tipos_list"),
    path("cadastros/tipos/novo/", views.tipo_create, name="tipo_create"),
    path("cadastros/tipos/<int:pk>/editar/", views.tipo_update, name="tipo_update"),
    path("cadastros/tipos/<int:pk>/ativo/", views.tipo_toggle_ativo, name="tipo_toggle_ativo"),

    path("cadastros/departamentos/", views.deptos_list, name="deptos_list"),
    path("cadastros/departamentos/novo/", views.depto_create, name="depto_create"),
    path("cadastros/departamentos/<int:pk>/editar/", views.depto_update, name="depto_update"),
    path("cadastros/departamentos/<int:pk>/ativo/", views.depto_toggle_ativo, name="depto_toggle_ativo"),

    path("cadastros/departamentos/<int:pk>/membros/", views.depto_membros, name="depto_membros"),
    path(
        "cadastros/departamentos/<int:pk>/membros/<int:membro_id>/ativo/",
        views.depto_membro_toggle,
        name="depto_membro_toggle",
    ),
]
