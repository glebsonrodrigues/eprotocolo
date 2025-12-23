from django.contrib.auth import authenticate, login, logout
from django.contrib.auth.decorators import login_required
from django.shortcuts import render, redirect
from django.urls import reverse
from django.views.decorators.http import require_http_methods


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
