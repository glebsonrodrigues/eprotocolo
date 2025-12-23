from django.urls import path
from . import views

urlpatterns = [
    path("", views.home, name="home"),

    path("processos/", views.processos_list, name="processos_list"),
    path("processos/<int:pk>/", views.processo_detail, name="processo_detail"),
]
