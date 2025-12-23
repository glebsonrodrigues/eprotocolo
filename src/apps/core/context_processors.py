import time

def session_time_left(request):
    """
    Disponibiliza nos templates a quantidade de segundos restantes
    para expirar por inatividade.
    """
    if not request.user.is_authenticated:
        return {"session_time_left": 0}

    timeout = 600  # 10 minutos
    last = request.session.get("last_activity")
    if not last:
        # se ainda não existe, considera "agora"
        last = int(time.time())
        request.session["last_activity"] = last

    now = int(time.time())
    remaining = timeout - (now - int(last))
    if remaining < 0:
        remaining = 0

    return {"session_time_left": remaining}
