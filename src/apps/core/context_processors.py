import time
from django.conf import settings
from django.db.models import Q

from protocolos.models import Processo, Departamento
from protocolos.utils import setor_esta_pendente_de_recebimento


def session_time_left(request):
    """
    Disponibiliza nos templates a quantidade de segundos restantes
    para expirar por inatividade.
    """
    if not request.user.is_authenticated:
        return {"session_time_left": 0}

    timeout = int(getattr(settings, "SESSION_COOKIE_AGE", 600))

    last = request.session.get("last_activity")
    if not last:
        last = int(time.time())
        request.session["last_activity"] = last

    now = int(time.time())
    remaining = timeout - (now - int(last))
    if remaining < 0:
        remaining = 0

    return {"session_time_left": remaining}


def caixa_entrada_counter(request):
    """
    Contador de processos pendentes de recebimento para mostrar no layout.
    Atenção: esta abordagem ainda faz loop, mas reduz carga quando possível.
    """
    if not request.user.is_authenticated:
        return {"caixa_entrada_qtd": 0}

    perfil = getattr(request.user, "perfil", None)
    papel = getattr(perfil, "papel", "CONSULTA")
    eh_admin = (papel == "ADMIN")

    # Usuário não-admin: pega setores onde é responsável/substituto
    setores_ids = []
    if not eh_admin:
        setores_ids = list(
            Departamento.objects.filter(
                Q(responsavel_id=request.user.id) | Q(substituto_id=request.user.id)
            ).values_list("id", flat=True)
        )
        if not setores_ids:
            return {"caixa_entrada_qtd": 0}

    # Carrega processos com o mínimo de dados (evita peso de objetos grandes)
    # Obs: setor_esta_pendente_de_recebimento provavelmente consulta movimentações,
    # então aqui a redução é modesta, mas já ajuda.
    qs = Processo.objects.all().only("id", "status", "recebido_em", "recebido_por_id")

    qtd = 0
    for p in qs:
        pendente, setor_atual = setor_esta_pendente_de_recebimento(p)

        if not pendente:
            continue

        if eh_admin:
            qtd += 1
            continue

        if setor_atual and setor_atual.id in setores_ids:
            qtd += 1

    return {"caixa_entrada_qtd": qtd}
