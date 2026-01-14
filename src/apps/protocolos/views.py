from __future__ import annotations

from collections import defaultdict
import re

from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.db.models import OuterRef, Subquery, Q, Count
from django.http import HttpResponseForbidden, JsonResponse
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_GET, require_POST

from .forms import (
    MovimentacaoForm,
    ProcessoCreateForm,
    PessoaForm,
    TipoProcessoForm,
    DepartamentoForm,
    DepartamentoMembroForm,
)
from .models import (
    Processo,
    MovimentacaoProcesso,
    TipoProcesso,
    Departamento,
    DepartamentoMembro,
    Pessoa,
)
from .utils import setor_esta_pendente_de_recebimento

# =============================================================================
# Helpers de permissão
# =============================================================================

def _qs_processos_com_setor_atual():
    last_mov = (
        MovimentacaoProcesso.objects
        .filter(processo=OuterRef("pk"))
        .order_by("-registrado_em")
    )

    return (
        Processo.objects.all()
        .select_related("tipo_processo", "criado_por")
        .annotate(
            ultima_tramitacao=Subquery(last_mov.values("registrado_em")[:1]),
            setor_atual=Subquery(last_mov.values("departamento_destino__nome")[:1]),
            setor_atual_id=Subquery(last_mov.values("departamento_destino_id")[:1]),
        )
    )

def _papel_usuario(user):
    perfil = getattr(user, "perfil", None)
    return getattr(perfil, "papel", "CONSULTA")


def _somente_admin_ou_protocolista(user):
    return _papel_usuario(user) in ("ADMIN", "PROTOCOLISTA")


def _aplicar_efeitos_movimentacao_no_processo(processo: Processo, mov: MovimentacaoProcesso) -> None:
    """
    Mantém o Processo consistente com a movimentação recém-criada.

    Regras:
    - ARQUIVADO -> status ARQUIVADO
    - ENCAMINHADO -> limpa recebido_* (fica pendente de recebimento no novo setor)
    - RECEBIDO -> atualiza recebido_* com quem recebeu e quando
    """
    if mov.acao == MovimentacaoProcesso.Acao.ARQUIVADO:
        processo.status = Processo.Status.ARQUIVADO
        processo.save(update_fields=["status"])
        return

    if mov.acao == MovimentacaoProcesso.Acao.ENCAMINHADO:
        processo.recebido_em = None
        processo.recebido_por = None

        if hasattr(Processo.Status, "EM_TRAMITACAO"):
            processo.status = Processo.Status.EM_TRAMITACAO
            processo.save(update_fields=["recebido_em", "recebido_por", "status"])
        else:
            processo.save(update_fields=["recebido_em", "recebido_por"])
        return

    if mov.acao == MovimentacaoProcesso.Acao.RECEBIDO:
        processo.recebido_em = mov.registrado_em or timezone.now()
        processo.recebido_por = mov.registrado_por
        processo.save(update_fields=["recebido_em", "recebido_por"])
        return

# =============================================================================
# Home
# =============================================================================

@login_required
def home(request):
    papel = _papel_usuario(request.user)
    if papel == "ADMIN":
        return dashboard_admin(request)
    return dashboard_user(request)

# =============================================================================
# Processos - Listagem
# =============================================================================
@login_required
def processos_list(request):
    last_mov = (
        MovimentacaoProcesso.objects
        .filter(processo=OuterRef("pk"))
        .order_by("-registrado_em")
    )

    qs = (
        Processo.objects.all()
        .select_related("tipo_processo", "criado_por")
        .prefetch_related("interessados")
        .annotate(
            ultima_tramitacao=Subquery(last_mov.values("registrado_em")[:1]),
            setor_atual=Subquery(last_mov.values("departamento_destino__nome")[:1]),
            setor_atual_id=Subquery(last_mov.values("departamento_destino_id")[:1]),
        )
        .order_by("-criado_em")
    )

    q = (request.GET.get("q") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    setor = (request.GET.get("setor") or "").strip()
    status = (request.GET.get("status") or "").strip()
    prioridade = (request.GET.get("prioridade") or "").strip()

    if q:
        digits = re.sub(r"\D+", "", q)

        filtros = (
            Q(numero_formatado__icontains=q)
            | Q(assunto__icontains=q)
            | Q(descricao__icontains=q)
            | Q(interessados__nome__icontains=q)
        )

        if digits:
            filtros |= Q(interessados__cpf__icontains=digits)

        qs = qs.filter(filtros).distinct()

    if tipo:
        qs = qs.filter(tipo_processo_id=tipo)

    if setor:
        qs = qs.filter(setor_atual_id=setor)

    if status:
        qs = qs.filter(status=status)

    if prioridade:
        qs = qs.filter(prioridade=prioridade)

    tipos = TipoProcesso.objects.all().order_by("nome")
    setores = Departamento.objects.all().order_by("nome")

    processos = list(qs)
    for p in processos:
        pendente, _setor_atual = setor_esta_pendente_de_recebimento(p)
        p.pendente_recebimento = pendente

    return render(
        request,
        "protocolos/processos_list.html",
        {
            "processos": processos,
            "tipos": tipos,
            "setores": setores,
            "status_choices": Processo.Status.choices,
            "prioridade_choices": Processo.Prioridade.choices,
            "f": {
                "q": q,
                "tipo": tipo,
                "setor": setor,
                "status": status,
                "prioridade": prioridade,
            },
        },
    )


# =============================================================================
# Processo - Receber / Tramitar / Visualizar
# =============================================================================

@require_POST
@login_required
def processo_receber(request, pk: int):
    processo = get_object_or_404(
        Processo.objects.select_related("recebido_por", "tipo_processo", "criado_por")
        .prefetch_related("movimentacoes"),
        pk=pk,
    )

    if processo.status == Processo.Status.ARQUIVADO:
        messages.warning(request, "Processo arquivado: não é possível receber ou tramitar.")
        return redirect("processo_view", pk=processo.pk)

    pendente, setor_atual = setor_esta_pendente_de_recebimento(processo)

    if not setor_atual:
        messages.error(request, "Este processo ainda não foi encaminhado para nenhum setor.")
        return redirect("processo_detail", pk=processo.pk)

    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")

    eh_responsavel = (
        setor_atual.responsavel_id == request.user.id
        or setor_atual.substituto_id == request.user.id
    )

    if not (eh_admin or eh_responsavel):
        return HttpResponseForbidden("Você não tem permissão para receber este processo neste setor.")

    if not pendente:
        messages.info(request, "Este processo já foi recebido neste setor.")
        return redirect("processo_detail", pk=processo.pk)

    with transaction.atomic():
        processo.recebido_em = timezone.now()
        processo.recebido_por = request.user
        processo.save(update_fields=["recebido_em", "recebido_por"])

        mov = MovimentacaoProcesso.objects.create(
            processo=processo,
            tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.INTERNA,
            acao=MovimentacaoProcesso.Acao.RECEBIDO,
            departamento_origem=setor_atual,
            departamento_destino=setor_atual,
            observacao=f"Recebimento confirmado por {request.user.username} no setor {setor_atual.nome}.",
            registrado_por=request.user,
            registrado_em=timezone.now(),
        )

        _aplicar_efeitos_movimentacao_no_processo(processo, mov)

    messages.success(request, f"Processo {processo.numero_formatado} recebido com sucesso.")
    return redirect("caixa_entrada")


@login_required
def processo_detail(request, pk: int):
    processo = get_object_or_404(
        Processo.objects.select_related("tipo_processo", "criado_por", "recebido_por")
        .prefetch_related("interessados", "movimentacoes"),
        pk=pk,
    )

    pendente_recebimento, setor_atual = setor_esta_pendente_de_recebimento(processo)

    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")

    eh_responsavel = False
    if setor_atual:
        eh_responsavel = (
            setor_atual.responsavel_id == request.user.id
            or setor_atual.substituto_id == request.user.id
        )

    pode_receber = bool(setor_atual) and pendente_recebimento and (eh_admin or eh_responsavel)

    movimentacoes = processo.movimentacoes.select_related(
        "departamento_origem", "departamento_destino", "registrado_por"
    ).order_by("-registrado_em")

    if request.method == "POST" and processo.status == Processo.Status.ARQUIVADO:
        messages.error(request, "Processo arquivado: não é possível tramitar.")
        return redirect("processo_detail", pk=processo.pk)

    if request.method == "POST":
        if pendente_recebimento:
            messages.error(request, "Aguardando recebimento do responsável do setor antes de tramitar.")
            return redirect("processo_detail", pk=processo.pk)

        form = MovimentacaoForm(request.POST, processo=processo, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                mov = form.save(commit=False)
                mov.processo = processo
                mov.registrado_por = request.user
                mov.save()

                _aplicar_efeitos_movimentacao_no_processo(processo, mov)

            messages.success(request, "Tramitação registrada com sucesso.")
            return redirect("processo_detail", pk=processo.pk)

        messages.error(request, "Corrija os campos destacados.")
    else:
        form = MovimentacaoForm(processo=processo, user=request.user)

    return render(
        request,
        "protocolos/processo_detail.html",
        {
            "processo": processo,
            "movimentacoes": movimentacoes,
            "form": form,
            "setor_atual": setor_atual,
            "pode_receber": pode_receber,
            "pendente_recebimento": pendente_recebimento,
        },
    )


@login_required
def processo_view(request, pk: int):
    processo = get_object_or_404(
        Processo.objects.select_related("tipo_processo", "criado_por", "recebido_por")
        .prefetch_related("interessados", "movimentacoes"),
        pk=pk,
    )

    pendente_recebimento, setor_atual = setor_esta_pendente_de_recebimento(processo)

    movimentacoes = processo.movimentacoes.select_related(
        "departamento_origem", "departamento_destino", "registrado_por"
    ).order_by("-registrado_em")

    return render(
        request,
        "protocolos/processo_view.html",
        {
            "processo": processo,
            "movimentacoes": movimentacoes,
            "setor_atual": setor_atual,
            "pendente_recebimento": pendente_recebimento,
        },
    )


# =============================================================================
# Caixa de Entrada
# =============================================================================
@login_required
def caixa_entrada(request):
    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")

    setores_ids = []
    setores_map = {}

    if not eh_admin:
        setores = Departamento.objects.filter(
            Q(responsavel_id=request.user.id) | Q(substituto_id=request.user.id)
        ).order_by("nome")

        setores_ids = list(set(setores.values_list("id", flat=True)))
        setores_map = {s.id: s for s in setores}

        if not setores_ids:
            return render(
                request,
                "protocolos/caixa_entrada.html",
                {
                    "eh_admin": False,
                    "pendentes_por_setor": [],
                    "no_setor_por_setor": [],
                    "setores_usuario": [],
                },
            )

    last_mov = (
        MovimentacaoProcesso.objects
        .filter(processo=OuterRef("pk"))
        .order_by("-registrado_em")
    )

    qs = (
        Processo.objects.all()
        .select_related("tipo_processo", "criado_por")
        .prefetch_related("interessados")
        .annotate(
            ultima_tramitacao=Subquery(last_mov.values("registrado_em")[:1]),
            setor_atual=Subquery(last_mov.values("departamento_destino__nome")[:1]),
            setor_atual_id=Subquery(last_mov.values("departamento_destino_id")[:1]),
        )
        .order_by("-criado_em")
    )

    if not eh_admin:
        qs = qs.filter(setor_atual_id__in=setores_ids)

    processos = list(qs)

    pendentes_dict = defaultdict(list)
    no_setor_dict = defaultdict(list)

    for p in processos:
        pendente, setor_atual = setor_esta_pendente_de_recebimento(p)
        if not setor_atual:
            continue

        p.pendente_recebimento = pendente

        if pendente:
            pendentes_dict[setor_atual.id].append(p)
        else:
            no_setor_dict[setor_atual.id].append(p)

    if eh_admin:
        all_setores_ids = set(list(pendentes_dict.keys()) + list(no_setor_dict.keys()))
        if all_setores_ids:
            setores = Departamento.objects.filter(id__in=all_setores_ids).order_by("nome")
            setores_map = {s.id: s for s in setores}

    def ordenar_por_nome(item):
        setor_id, _lista = item
        setor = setores_map.get(setor_id)
        return (setor.nome if setor else "")

    pendentes_por_setor = [
        {"setor": setores_map.get(setor_id), "itens": lista, "qtd": len(lista)}
        for setor_id, lista in sorted(pendentes_dict.items(), key=ordenar_por_nome)
    ]

    no_setor_por_setor = [
        {"setor": setores_map.get(setor_id), "itens": lista, "qtd": len(lista)}
        for setor_id, lista in sorted(no_setor_dict.items(), key=ordenar_por_nome)
    ]

    return render(
        request,
        "protocolos/caixa_entrada.html",
        {
            "eh_admin": eh_admin,
            "pendentes_por_setor": pendentes_por_setor,
            "no_setor_por_setor": no_setor_por_setor,
            "setores_usuario": list(setores_map.values()) if not eh_admin else [],
        },
    )


# =============================================================================
# Processo - Create (PROTOCOLO GERAL) - AJUSTADO PARA ano/numero_manual
# =============================================================================
@login_required
def processo_create(request):
    if not _somente_admin_ou_protocolista(request.user):
        return HttpResponseForbidden("Você não tem permissão para criar processos.")

    protocolo_geral = Departamento.objects.filter(
        nome__iexact="PROTOCOLO GERAL",
        tipo=Departamento.Tipo.INTERNO,
        ativo=True,
    ).first()

    if not protocolo_geral:
        messages.error(request, 'Departamento "PROTOCOLO GERAL" (INTERNO/ativo) não encontrado.')
        return redirect("home")

    pessoa = None
    pessoa_status = None  # "ok" | "nao_encontrada"

    if request.method == "POST":
        form = ProcessoCreateForm(request.POST)
        if form.is_valid():
            cpf = form.cleaned_data["cpf"]

            pessoa = Pessoa.objects.filter(cpf=cpf, ativo=True).first()
            if not pessoa:
                pessoa_status = "nao_encontrada"
                messages.error(request, "Pessoa não encontrada. Cadastre o requerente para continuar.")
                return render(
                    request,
                    "protocolos/processo_form.html",
                    {"form": form, "pessoa": None, "pessoa_status": pessoa_status},
                )

            pessoa_status = "ok"

            tipo_processo = form.cleaned_data["tipo_processo"]
            assunto = form.cleaned_data["assunto"]
            descricao = form.cleaned_data["descricao"]
            prioridade = form.cleaned_data["prioridade"]

            numero_manual = form.numero_int
            ano_2d = form.ano_int

            numero_formatado = Processo.format_numero(numero_manual, ano_2d)

            with transaction.atomic():
                processo = Processo.objects.create(
                    ano=ano_2d,
                    numero_manual=numero_manual,
                    numero_formatado=numero_formatado,
                    tipo_processo=tipo_processo,
                    assunto=assunto,
                    descricao=descricao,
                    criado_por=request.user,
                    prioridade=prioridade,
                )
                processo.interessados.add(pessoa)

                mov = MovimentacaoProcesso.objects.create(
                    processo=processo,
                    tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.INTERNA,
                    acao=MovimentacaoProcesso.Acao.RECEBIDO,
                    departamento_origem=protocolo_geral,
                    departamento_destino=protocolo_geral,
                    observacao="Processo criado no PROTOCOLO GERAL.",
                    registrado_por=request.user,
                    registrado_em=timezone.now(),
                )

                processo.recebido_em = timezone.now()
                processo.recebido_por = request.user
                processo.save(update_fields=["recebido_em", "recebido_por"])

                _aplicar_efeitos_movimentacao_no_processo(processo, mov)

            messages.success(request, f"Processo {processo.numero_formatado} criado com sucesso.")
            return redirect("processo_detail", pk=processo.pk)

        messages.error(request, "Corrija os campos destacados.")
    else:
        form = ProcessoCreateForm()

    return render(
        request,
        "protocolos/processo_form.html",
        {"form": form, "pessoa": pessoa, "pessoa_status": pessoa_status},
    )


# =============================================================================
# API AJAX - Lookup Pessoa (CPF ou Nome)
# =============================================================================
@require_GET
@login_required
def pessoa_lookup(request):
    if not _somente_admin_ou_protocolista(request.user):
        return JsonResponse({"results": []}, status=403)

    q = (request.GET.get("q") or "").strip()
    if not q or len(q) < 2:
        return JsonResponse({"results": []})

    digits = re.sub(r"\D+", "", q)

    qs = Pessoa.objects.filter(ativo=True)

    if digits:
        qs = qs.filter(cpf__startswith=digits)
    else:
        qs = qs.filter(nome__icontains=q)

    qs = qs.order_by("nome")[:10]

    results = [{"id": p.id, "nome": p.nome, "cpf": p.cpf} for p in qs]
    return JsonResponse({"results": results})


# =============================================================================
# Pessoas (Requerentes)
# =============================================================================
@login_required
def pessoas_list(request):
    if not _somente_admin_ou_protocolista(request.user):
        return HttpResponseForbidden("Você não tem permissão para acessar o cadastro de pessoas.")

    q = (request.GET.get("q") or "").strip()
    ativo = (request.GET.get("ativo") or "").strip()  # "", "1", "0"

    qs = Pessoa.objects.all().order_by("nome")

    if q:
        digits = re.sub(r"\D+", "", q)
        if digits:
            qs = qs.filter(Q(cpf__icontains=digits) | Q(nome__icontains=q))
        else:
            qs = qs.filter(Q(nome__icontains=q) | Q(cpf__icontains=q))

    if ativo == "1":
        qs = qs.filter(ativo=True)
    elif ativo == "0":
        qs = qs.filter(ativo=False)

    return render(
        request,
        "protocolos/pessoas_list.html",
        {"pessoas": qs, "f": {"q": q, "ativo": ativo}},
    )


@login_required
def pessoa_create(request):
    if not _somente_admin_ou_protocolista(request.user):
        return HttpResponseForbidden("Você não tem permissão para cadastrar pessoas.")

    if request.method == "POST":
        form = PessoaForm(request.POST)
        if form.is_valid():
            pessoa = form.save()
            messages.success(request, f"Pessoa cadastrada: {pessoa.nome}.")
            return redirect("pessoas_list")
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = PessoaForm()

    return render(request, "protocolos/pessoa_form.html", {"form": form, "modo": "create"})


@login_required
def pessoa_update(request, pk: int):
    if not _somente_admin_ou_protocolista(request.user):
        return HttpResponseForbidden("Você não tem permissão para editar pessoas.")

    pessoa = get_object_or_404(Pessoa, pk=pk)

    if request.method == "POST":
        form = PessoaForm(request.POST, instance=pessoa)
        if form.is_valid():
            pessoa = form.save()
            messages.success(request, f"Pessoa atualizada: {pessoa.nome}.")
            return redirect("pessoas_list")
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = PessoaForm(instance=pessoa)

    return render(request, "protocolos/pessoa_form.html", {"form": form, "modo": "update", "pessoa": pessoa})


@require_POST
@login_required
def pessoa_toggle_ativo(request, pk: int):
    if not _somente_admin_ou_protocolista(request.user):
        return HttpResponseForbidden("Você não tem permissão para alterar status da pessoa.")

    pessoa = get_object_or_404(Pessoa, pk=pk)
    pessoa.ativo = not pessoa.ativo
    pessoa.save(update_fields=["ativo"])

    if pessoa.ativo:
        messages.success(request, "Pessoa ATIVADA com sucesso.")
    else:
        messages.warning(request, "Pessoa DESATIVADA com sucesso.")

    return redirect("pessoas_list")


@login_required
def dashboard_admin(request):
    papel = _papel_usuario(request.user)
    if papel != "ADMIN":
        return dashboard_user(request)

    qs = _qs_processos_com_setor_atual()

    total = qs.count()
    ativos = qs.filter(status=Processo.Status.ATIVO).count()
    arquivados = qs.filter(status=Processo.Status.ARQUIVADO).count()

    pendentes = 0
    ultimos = list(
        qs.prefetch_related("interessados")
          .order_by("-criado_em")[:8]
    )
    processos = list(qs.order_by("-criado_em")[:300])
    for p in processos:
        pend, _setor = setor_esta_pendente_de_recebimento(p)
        if pend:
            pendentes += 1

    por_status = (
        qs.values("status")
          .annotate(qtd=Count("id"))
          .order_by("status")
    )
    por_prioridade = (
        qs.values("prioridade")
          .annotate(qtd=Count("id"))
          .order_by("prioridade")
    )

    por_setor = (
        qs.exclude(setor_atual_id__isnull=True)
          .values("setor_atual_id", "setor_atual")
          .annotate(qtd=Count("id"))
          .order_by("-qtd", "setor_atual")
    )[:10]

    return render(
        request,
        "protocolos/dashboard_admin.html",
        {
            "papel": papel,
            "cards": {
                "total": total,
                "ativos": ativos,
                "arquivados": arquivados,
                "pendentes": pendentes,
            },
            "por_status": list(por_status),
            "por_prioridade": list(por_prioridade),
            "por_setor": list(por_setor),
            "ultimos": ultimos,
        },
    )


@login_required
def dashboard_user(request):
    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")

    qs = _qs_processos_com_setor_atual()

    setores = Departamento.objects.filter(
        Q(responsavel_id=request.user.id) | Q(substituto_id=request.user.id),
        ativo=True,
    ).order_by("nome")

    setores_ids = list(set(setores.values_list("id", flat=True)))

    if not eh_admin:
        qs = qs.filter(setor_atual_id__in=setores_ids)

    pendentes = []
    no_setor = []

    processos = list(
        qs.prefetch_related("interessados")
          .order_by("-criado_em")[:300]
    )

    for p in processos:
        pend, setor_atual = setor_esta_pendente_de_recebimento(p)
        if not setor_atual:
            continue
        p.pendente_recebimento = pend

        if pend:
            pendentes.append(p)
        else:
            no_setor.append(p)

    ultimos = list(
        qs.prefetch_related("interessados")
          .order_by("-criado_em")[:8]
    )

    return render(
        request,
        "protocolos/dashboard_user.html",
        {
            "papel": papel,
            "eh_admin": eh_admin,
            "setores_usuario": list(setores),
            "cards": {
                "pendentes": len(pendentes),
                "no_setor": len(no_setor),
                "total_no_meu_recorte": len(processos),
            },
            "pendentes": pendentes[:10],
            "no_setor": no_setor[:10],
            "ultimos": ultimos,
        },
    )

# =============================================================================
# CADASTROS (ADMIN) - NOVAS VIEWS
# =============================================================================

def _somente_admin(user):
    return _papel_usuario(user) == "ADMIN"


# --------------------------
# TIPOS DE PROCESSO
# --------------------------
@login_required
def tipos_list(request):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    q = (request.GET.get("q") or "").strip()
    ativo = (request.GET.get("ativo") or "").strip()  # "", "1", "0"

    qs = TipoProcesso.objects.all().order_by("nome")
    if q:
        qs = qs.filter(Q(nome__icontains=q) | Q(descricao__icontains=q))

    if ativo == "1":
        qs = qs.filter(ativo=True)
    elif ativo == "0":
        qs = qs.filter(ativo=False)

    return render(request, "protocolos/cadastros/tipos_list.html", {"tipos": qs, "f": {"q": q, "ativo": ativo}})


@login_required
def tipo_create(request):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    if request.method == "POST":
        form = TipoProcessoForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Tipo criado: {obj.nome}")
            return redirect("tipos_list")
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = TipoProcessoForm()

    return render(request, "protocolos/cadastros/tipo_form.html", {"form": form, "modo": "create"})


@login_required
def tipo_update(request, pk: int):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    obj = get_object_or_404(TipoProcesso, pk=pk)

    if request.method == "POST":
        form = TipoProcessoForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Tipo atualizado: {obj.nome}")
            return redirect("tipos_list")
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = TipoProcessoForm(instance=obj)

    return render(request, "protocolos/cadastros/tipo_form.html", {"form": form, "modo": "update", "obj": obj})


@require_POST
@login_required
def tipo_toggle_ativo(request, pk: int):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    obj = get_object_or_404(TipoProcesso, pk=pk)
    obj.ativo = not obj.ativo
    obj.save(update_fields=["ativo"])
    messages.success(request, f"Tipo {'ATIVADO' if obj.ativo else 'DESATIVADO'}: {obj.nome}")
    return redirect("tipos_list")


# --------------------------
# DEPARTAMENTOS
# --------------------------
@login_required
def deptos_list(request):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    q = (request.GET.get("q") or "").strip()
    tipo = (request.GET.get("tipo") or "").strip()
    ativo = (request.GET.get("ativo") or "").strip()

    qs = (
        Departamento.objects.all()
        .select_related("responsavel", "substituto")
        .order_by("tipo", "nome")
    )

    if q:
        qs = qs.filter(Q(nome__icontains=q) | Q(sigla__icontains=q))

    if tipo:
        qs = qs.filter(tipo=tipo)

    if ativo == "1":
        qs = qs.filter(ativo=True)
    elif ativo == "0":
        qs = qs.filter(ativo=False)

    return render(
        request,
        "protocolos/cadastros/deptos_list.html",
        {"deptos": qs, "tipos": Departamento.Tipo.choices, "f": {"q": q, "tipo": tipo, "ativo": ativo}},
    )


@login_required
def depto_create(request):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    if request.method == "POST":
        form = DepartamentoForm(request.POST)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Departamento criado: {obj.nome}")
            return redirect("deptos_list")
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = DepartamentoForm()

    return render(request, "protocolos/cadastros/depto_form.html", {"form": form, "modo": "create"})


@login_required
def depto_update(request, pk: int):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    obj = get_object_or_404(Departamento, pk=pk)

    if request.method == "POST":
        form = DepartamentoForm(request.POST, instance=obj)
        if form.is_valid():
            obj = form.save()
            messages.success(request, f"Departamento atualizado: {obj.nome}")
            return redirect("deptos_list")
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = DepartamentoForm(instance=obj)

    return render(request, "protocolos/cadastros/depto_form.html", {"form": form, "modo": "update", "obj": obj})


@require_POST
@login_required
def depto_toggle_ativo(request, pk: int):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    obj = get_object_or_404(Departamento, pk=pk)
    obj.ativo = not obj.ativo
    obj.save(update_fields=["ativo"])
    messages.success(request, f"Departamento {'ATIVADO' if obj.ativo else 'DESATIVADO'}: {obj.nome}")
    return redirect("deptos_list")


# --------------------------
# MEMBROS DO DEPARTAMENTO
# --------------------------
@login_required
def depto_membros(request, pk: int):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    depto = get_object_or_404(Departamento, pk=pk)

    membros = (
        DepartamentoMembro.objects.filter(departamento=depto)
        .select_related("user")
        .order_by("-ativo", "user__username")
    )

    if request.method == "POST":
        form = DepartamentoMembroForm(request.POST)
        if form.is_valid():
            m = form.save(commit=False)
            m.departamento = depto
            m.save()
            messages.success(request, "Membro adicionado.")
            return redirect("depto_membros", pk=depto.pk)
        messages.error(request, "Corrija os campos destacados.")
    else:
        form = DepartamentoMembroForm()

    return render(
        request,
        "protocolos/cadastros/depto_membros.html",
        {"depto": depto, "membros": membros, "form": form},
    )


@require_POST
@login_required
def depto_membro_toggle(request, pk: int, membro_id: int):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    depto = get_object_or_404(Departamento, pk=pk)
    membro = get_object_or_404(DepartamentoMembro, pk=membro_id, departamento=depto)
    membro.ativo = not membro.ativo
    membro.save(update_fields=["ativo"])
    messages.success(request, f"Membro {'ATIVADO' if membro.ativo else 'DESATIVADO'}.")
    return redirect("depto_membros", pk=depto.pk)
