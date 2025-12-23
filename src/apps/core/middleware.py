import time
from django.contrib.auth import logout
from django.shortcuts import redirect
from django.urls import reverse

class IdleLogoutMiddleware:
    """
    Faz logout se o usuário ficar inativo por X segundos.
    Atualiza last_activity apenas quando há request autenticado.
    """
    def __init__(self, get_response):
        self.get_response = get_response
        self.timeout = 600  # 10 min

    def __call__(self, request):
        if request.user.is_authenticated:
            now = int(time.time())
            last = request.session.get("last_activity")

            if last is not None and (now - int(last)) > self.timeout:
                logout(request)
                request.session.flush()
                return redirect(reverse("login"))

            # atualiza "atividade" em toda request autenticada
            request.session["last_activity"] = now

        return self.get_response(request)
