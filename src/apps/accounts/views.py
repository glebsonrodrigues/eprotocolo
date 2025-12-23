from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods

from accounts.permissions import only_admin
from django.contrib.auth import get_user_model
from django.contrib import messages

from .forms import UsuarioCreateForm, UsuarioUpdateForm

User = get_user_model()


@require_http_methods(["GET", "POST"])
def login_view(request):
    # Se já estiver autenticado, manda pra home
    if request.user.is_authenticated:
        return redirect("home")  # ajuste o nome se sua home tiver outro name

    error = None
    if request.method == "POST":
        username = request.POST.get("username", "").strip()
        password = request.POST.get("password", "")

        user = authenticate(request, username=username, password=password)
        if user is not None:
            login(request, user)

            # Se existir "next", respeita
            next_url = request.GET.get("next")
            return redirect(next_url or "home")
        else:
            error = "Usuário ou senha inválidos."

    return render(request, "accounts/login.html", {"error": error})


@require_http_methods(["POST"])
def logout_view(request):
    logout(request)
    return redirect("login")


@only_admin
def usuarios_list(request):
    usuarios = User.objects.select_related("perfil").order_by("username")
    return render(request, "accounts/usuarios_list.html", {"usuarios": usuarios})


@only_admin
def usuario_create(request):
    if request.method == "POST":
        form = UsuarioCreateForm(request.POST)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuário criado com sucesso.")
            return redirect("usuarios_list")
    else:
        form = UsuarioCreateForm()

    return render(
        request,
        "accounts/usuario_form.html",
        {
            "form": form,
            "titulo": "Novo usuário",
        },
    )


@only_admin
def usuario_update(request, pk):
    user = User.objects.select_related("perfil").get(pk=pk)

    if request.method == "POST":
        form = UsuarioUpdateForm(request.POST, instance=user)
        if form.is_valid():
            form.save()
            messages.success(request, "Usuário atualizado com sucesso.")
            return redirect("usuarios_list")
    else:
        form = UsuarioUpdateForm(instance=user)

    return render(
        request,
        "accounts/usuario_form.html",
        {
            "form": form,
            "titulo": f"Editar usuário: {user.username}",
        },
    )
