# apps/protocolos/views.py
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
# Helpers
# =============================================================================

def _last_mov_subquery():
    return (
        MovimentacaoProcesso.objects
        .filter(processo=OuterRef("pk"))
        .order_by("-registrado_em")
    )


def _qs_processos_com_setor_atual():
    last_mov = _last_mov_subquery()

    return (
        Processo.objects.all()
        .select_related("tipo_processo", "criado_por", "responsavel_setor")
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


def _somente_admin(user):
    return _papel_usuario(user) == "ADMIN"


def _usuario_tem_vinculo_com_setor(user, setor: Departamento) -> bool:
    """
    ✅ Compatível com seus models:
    - responsável/substituto OU
    - membro ativo (Departamento.membros)
    """
    if not setor:
        return False

    if setor.responsavel_id == user.id or setor.substituto_id == user.id:
        return True

    return setor.membros.filter(user_id=user.id, ativo=True).exists()


def _aplicar_efeitos_movimentacao_no_processo(processo: Processo, mov: MovimentacaoProcesso) -> None:
    """
    Mantém o Processo consistente com a movimentação recém-criada.
    + ✅ Setores multiusuário: ao mudar de setor, limpa responsavel_setor.
    """
    if mov.acao == MovimentacaoProcesso.Acao.ARQUIVADO:
        processo.status = Processo.Status.ARQUIVADO
        processo.save(update_fields=["status"])
        return

    if mov.acao in (MovimentacaoProcesso.Acao.ENCAMINHADO, MovimentacaoProcesso.Acao.DEVOLVIDO):
        # ✅ mudou de setor -> limpa atribuição interna do setor anterior
        if hasattr(processo, "responsavel_setor"):
            processo.responsavel_setor = None

        # ao encaminhar interno, zera recebido_*
        if mov.tipo_tramitacao == MovimentacaoProcesso.TipoTramitacao.INTERNA:
            processo.recebido_em = None
            processo.recebido_por = None

        if hasattr(Processo.Status, "EM_TRAMITACAO"):
            processo.status = Processo.Status.EM_TRAMITACAO
            processo.save(update_fields=["recebido_em", "recebido_por", "status", "responsavel_setor"])
        else:
            processo.save(update_fields=["recebido_em", "recebido_por", "responsavel_setor"])
        return

    if mov.acao == MovimentacaoProcesso.Acao.RECEBIDO:
        if mov.tipo_tramitacao == MovimentacaoProcesso.TipoTramitacao.INTERNA:
            processo.recebido_em = mov.registrado_em or timezone.now()
            processo.recebido_por = mov.registrado_por
            processo.save(update_fields=["recebido_em", "recebido_por"])
        return

    # RECEBIDO_EXTERNO: não altera recebido_* (é só histórico)


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
    qs = (
        _qs_processos_com_setor_atual()
        .prefetch_related("interessados")
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

    tipos = TipoProcesso.objects.filter(ativo=True).order_by("nome")
    setores = Departamento.objects.filter(ativo=True).order_by("nome")

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
            "f": {"q": q, "tipo": tipo, "setor": setor, "status": status, "prioridade": prioridade},
        },
    )


# =============================================================================
# Processo - Receber INTERNO
# =============================================================================

@require_POST
@login_required
def processo_receber(request, pk: int):
    processo = get_object_or_404(
        Processo.objects.select_related("recebido_por", "tipo_processo", "criado_por", "responsavel_setor")
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

    if setor_atual.tipo != Departamento.Tipo.INTERNO:
        messages.warning(
            request,
            f"Este processo está em um órgão EXTERNO ({setor_atual.nome}). "
            f"Use apenas o RETORNO DO ÓRGÃO EXTERNO para voltar ao interno."
        )
        return redirect("processo_detail", pk=processo.pk)

    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")

    tem_vinculo = _usuario_tem_vinculo_com_setor(request.user, setor_atual)
    if not (eh_admin or tem_vinculo):
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


# =============================================================================
# Processo - Retorno do órgão externo
# =============================================================================

@require_POST
@login_required
def processo_retorno_externo(request, pk: int):
    processo = get_object_or_404(
        Processo.objects.select_related("tipo_processo", "criado_por", "recebido_por", "responsavel_setor")
        .prefetch_related("movimentacoes"),
        pk=pk,
    )

    if processo.status == Processo.Status.ARQUIVADO:
        messages.error(request, "Processo arquivado: não é possível registrar retorno.")
        return redirect("processo_detail", pk=processo.pk)

    _pendente, setor_atual = setor_esta_pendente_de_recebimento(processo)
    if not setor_atual:
        messages.error(request, "Este processo ainda não possui setor atual.")
        return redirect("processo_detail", pk=processo.pk)

    if setor_atual.tipo != Departamento.Tipo.EXTERNO:
        messages.info(request, "Este processo não está em órgão EXTERNO.")
        return redirect("processo_detail", pk=processo.pk)

    destino_id = (request.POST.get("destino_interno") or "").strip()
    if not destino_id:
        messages.error(request, "Selecione o setor interno de destino.")
        return redirect("processo_detail", pk=processo.pk)

    destino = get_object_or_404(
        Departamento,
        pk=destino_id,
        tipo=Departamento.Tipo.INTERNO,
        ativo=True,
    )

    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")

    # regra segura: ADMIN pode; demais, precisa ter vínculo com o destino
    if not eh_admin:
        if not _usuario_tem_vinculo_com_setor(request.user, destino):
            return HttpResponseForbidden("Você não tem permissão para registrar retorno para este setor interno.")

    with transaction.atomic():
        mov = MovimentacaoProcesso.objects.create(
            processo=processo,
            tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.EXTERNA,
            acao=MovimentacaoProcesso.Acao.DEVOLVIDO,
            departamento_origem=setor_atual,
            departamento_destino=destino,
            observacao=(
                f"RETORNO DO ÓRGÃO EXTERNO: {setor_atual.nome} -> {destino.nome}. "
                f"Registrado por {request.user.username}."
            ),
            registrado_por=request.user,
            registrado_em=timezone.now(),
        )

        # ao voltar do externo, fica pendente de recebimento no destino interno:
        processo.recebido_em = None
        processo.recebido_por = None
        processo.responsavel_setor = None
        processo.save(update_fields=["recebido_em", "recebido_por", "responsavel_setor"])

        _aplicar_efeitos_movimentacao_no_processo(processo, mov)

    messages.success(request, f"Retorno registrado: {setor_atual.nome} → {destino.nome}.")
    return redirect("processo_detail", pk=processo.pk)


# =============================================================================
# ✅ Setores multiusuário - Pegar / Liberar
# =============================================================================

@require_POST
@login_required
def processo_pegar_setor(request, pk: int):
    """
    Atribui o processo ao usuário dentro do setor atual.
    Regras:
    - Só funciona em setor INTERNO.
    - Só pode pegar se NÃO estiver pendente de recebimento.
    - Só membro do setor (ou ADMIN).
    - Se já estiver atribuído a outro, só ADMIN pode trocar.
    """
    processo = get_object_or_404(
        Processo.objects.select_related("tipo_processo", "criado_por", "responsavel_setor")
        .prefetch_related("movimentacoes"),
        pk=pk,
    )

    if processo.status == Processo.Status.ARQUIVADO:
        messages.error(request, "Processo arquivado: não é possível atribuir.")
        return redirect("processo_detail", pk=processo.pk)

    pendente, setor_atual = setor_esta_pendente_de_recebimento(processo)
    if not setor_atual or setor_atual.tipo != Departamento.Tipo.INTERNO:
        messages.error(request, "Este processo não está em um setor interno.")
        return redirect("processo_detail", pk=processo.pk)

    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")

    if not eh_admin and not _usuario_tem_vinculo_com_setor(request.user, setor_atual):
        return HttpResponseForbidden("Você não tem permissão para pegar processos deste setor.")

    if pendente:
        messages.error(request, "Primeiro receba o processo no setor para depois atribuir.")
        return redirect("processo_detail", pk=processo.pk)

    atual_id = getattr(processo, "responsavel_setor_id", None)
    if atual_id and atual_id != request.user.id and not eh_admin:
        messages.error(request, "Este processo já está atribuído a outro servidor.")
        return redirect("processo_detail", pk=processo.pk)

    processo.responsavel_setor = request.user
    processo.save(update_fields=["responsavel_setor"])
    messages.success(request, "Processo atribuído a você.")
    return redirect("processo_detail", pk=processo.pk)


@require_POST
@login_required
def processo_liberar_setor(request, pk: int):
    """
    Remove a atribuição do processo (volta a ficar 'disponível' no setor).
    Regras:
    - Só responsável atual ou ADMIN pode liberar.
    """
    processo = get_object_or_404(
        Processo.objects.select_related("responsavel_setor")
        .prefetch_related("movimentacoes"),
        pk=pk,
    )

    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")

    atual_id = getattr(processo, "responsavel_setor_id", None)
    if not atual_id:
        messages.info(request, "Este processo já está sem responsável no setor.")
        return redirect("processo_detail", pk=processo.pk)

    if not eh_admin and atual_id != request.user.id:
        return HttpResponseForbidden("Somente o responsável (ou ADMIN) pode liberar este processo.")

    processo.responsavel_setor = None
    processo.save(update_fields=["responsavel_setor"])
    messages.success(request, "Atribuição removida. Processo disponível no setor.")
    return redirect("processo_detail", pk=processo.pk)


# =============================================================================
# Processo - Detail / View
# =============================================================================

@login_required
def processo_detail(request, pk: int):
    processo = get_object_or_404(
        Processo.objects.select_related("tipo_processo", "criado_por", "recebido_por", "responsavel_setor")
        .prefetch_related("interessados", "movimentacoes"),
        pk=pk,
    )

    pendente_recebimento, setor_atual = setor_esta_pendente_de_recebimento(processo)

    papel = _papel_usuario(request.user)
    eh_admin = (papel == "ADMIN")
    eh_protocolista = (papel == "PROTOCOLISTA")

    em_setor_externo = bool(setor_atual) and setor_atual.tipo == Departamento.Tipo.EXTERNO

    # pode receber (somente quando setor atual é INTERNO e está pendente)
    tem_vinculo = False
    if setor_atual and setor_atual.tipo == Departamento.Tipo.INTERNO:
        tem_vinculo = _usuario_tem_vinculo_com_setor(request.user, setor_atual)

    pode_receber = bool(setor_atual) and (setor_atual.tipo == Departamento.Tipo.INTERNO) and pendente_recebimento and (eh_admin or tem_vinculo)

    # lista de setores internos para o RETORNO EXTERNO
    setores_internos = Departamento.objects.filter(tipo=Departamento.Tipo.INTERNO, ativo=True).order_by("nome")

    movimentacoes = (
        processo.movimentacoes.select_related(
            "departamento_origem", "departamento_destino", "registrado_por"
        )
        .order_by("-registrado_em")
    )

    # ==========================
    # ✅ Setor multiusuário
    # ==========================
    responsavel_setor = getattr(processo, "responsavel_setor", None)
    bloqueado_por_atribuicao = bool(responsavel_setor) and (responsavel_setor.id != request.user.id) and (not eh_admin)

    pode_pegar = False
    pode_liberar = False

    if setor_atual and setor_atual.tipo == Departamento.Tipo.INTERNO and (eh_admin or tem_vinculo):
        if not pendente_recebimento and processo.status != Processo.Status.ARQUIVADO:
            if responsavel_setor is None:
                pode_pegar = True
            elif responsavel_setor.id == request.user.id:
                pode_liberar = True
            else:
                # atribuído a outro -> ADMIN pode tomar (via pegar)
                if eh_admin:
                    pode_pegar = True

    # ==========================
    # POST (tramitação via form)
    # ==========================
    if request.method == "POST":
        if processo.status == Processo.Status.ARQUIVADO:
            messages.error(request, "Processo arquivado: não é possível tramitar.")
            return redirect("processo_detail", pk=processo.pk)

        # externo: trava
        if em_setor_externo:
            messages.warning(
                request,
                f"Processo está em órgão EXTERNO ({setor_atual.nome}). "
                f"Utilize apenas a opção de RETORNO DO ÓRGÃO EXTERNO."
            )
            return redirect("processo_detail", pk=processo.pk)

        # trava enquanto pendente
        if pendente_recebimento:
            messages.error(request, "Aguardando recebimento do setor antes de tramitar.")
            return redirect("processo_detail", pk=processo.pk)

        # ✅ trava por atribuição (setor multiusuário)
        if bloqueado_por_atribuicao:
            messages.error(request, f"Tramitação bloqueada: processo atribuído a {responsavel_setor.username}.")
            return redirect("processo_detail", pk=processo.pk)

        # ✅ trava de protocolista fora do PG
        if eh_protocolista and setor_atual and (not getattr(setor_atual, "eh_protocolo_geral", False)):
            messages.error(request, "Protocolista só pode tramitar enquanto estiver no PROTOCOLO GERAL.")
            return redirect("processo_detail", pk=processo.pk)

        form = MovimentacaoForm(request.POST, processo=processo, user=request.user)
        if form.is_valid():
            with transaction.atomic():
                mov = form.save(commit=False)
                mov.processo = processo
                mov.registrado_por = request.user
                if not mov.registrado_em:
                    mov.registrado_em = timezone.now()

                # ==========================================================
                # ✅ CORREÇÃO PRINCIPAL: ORIGEM E REGRAS DO ARQUIVAMENTO
                # ==========================================================

                # garante origem = setor atual (sempre)
                if setor_atual and not mov.departamento_origem_id:
                    mov.departamento_origem = setor_atual

                # ✅ se o usuário tentar arquivar fora do ARQUIVO GERAL -> bloqueia
                if mov.acao == MovimentacaoProcesso.Acao.ARQUIVADO:
                    if not setor_atual or not getattr(setor_atual, "eh_arquivo_geral", False):
                        messages.error(request, "Só é possível arquivar quando o processo estiver no ARQUIVO GERAL.")
                        return redirect("processo_detail", pk=processo.pk)

                    # destino automático = ARQUIVO GERAL
                    mov.departamento_destino = setor_atual

                    # tipo interno (arquivamento sempre é interno)
                    mov.tipo_tramitacao = MovimentacaoProcesso.TipoTramitacao.INTERNA

                    if not mov.observacao:
                        mov.observacao = "Arquivado no ARQUIVO GERAL."

                mov.save()

                _aplicar_efeitos_movimentacao_no_processo(processo, mov)

            messages.success(request, "Tramitação registrada com sucesso.")
            return redirect("processo_detail", pk=processo.pk)

        messages.error(request, "Corrija os campos destacados.")
    else:
        form = MovimentacaoForm(processo=processo, user=request.user)

        # ==========================================================
        # ✅ CORREÇÃO: esconder 'ARQUIVADO' fora do ARQUIVO GERAL (GET)
        # ==========================================================
        if setor_atual and not getattr(setor_atual, "eh_arquivo_geral", False):
            if "acao" in form.fields:
                form.fields["acao"].choices = [
                    c for c in form.fields["acao"].choices
                    if c[0] != MovimentacaoProcesso.Acao.ARQUIVADO
                ]

        if em_setor_externo:
            for f in form.fields.values():
                f.disabled = True
            if "observacao" in form.fields:
                form.fields["observacao"].help_text = (
                    "Processo em órgão EXTERNO. Use o botão de RETORNO DO ÓRGÃO EXTERNO."
                )

    return render(
        request,
        "protocolos/processo_detail.html",
        {
            "processo": processo,
            "movimentacoes": movimentacoes,
            "form": form,
            "setor_atual": setor_atual,
            "pendente_recebimento": pendente_recebimento,
            "pode_receber": pode_receber,
            "em_setor_externo": em_setor_externo,
            "setores_internos": setores_internos,

            # ✅ Multiusuário
            "responsavel_setor": responsavel_setor,
            "pode_pegar": pode_pegar,
            "pode_liberar": pode_liberar,
            "bloqueado_por_atribuicao": bloqueado_por_atribuicao,
        },
    )


@login_required
def processo_view(request, pk: int):
    processo = get_object_or_404(
        Processo.objects.select_related("tipo_processo", "criado_por", "recebido_por", "responsavel_setor")
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
        setores = (
            Departamento.objects
            .filter(tipo=Departamento.Tipo.INTERNO, ativo=True)
            .filter(
                Q(responsavel_id=request.user.id)
                | Q(substituto_id=request.user.id)
                | Q(membros__user_id=request.user.id, membros__ativo=True)
            )
            .distinct()
            .order_by("nome")
        )

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

    qs = (
        _qs_processos_com_setor_atual()
        .prefetch_related("interessados")
        .order_by("-criado_em")
    )

    if not eh_admin:
        qs = qs.filter(setor_atual_id__in=setores_ids)

        # ✅ MOSTRA APENAS:
        # - processos sem responsável no setor (disponíveis)
        # - processos atribuídos a mim
        qs = qs.filter(Q(responsavel_setor__isnull=True) | Q(responsavel_setor_id=request.user.id))

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
# Processo - Create (PROTOCOLO GERAL)
# =============================================================================

@login_required
def processo_create(request):
    if not _somente_admin_ou_protocolista(request.user):
        return HttpResponseForbidden("Você não tem permissão para criar processos.")

    protocolo_geral = Departamento.objects.filter(
        eh_protocolo_geral=True,
        tipo=Departamento.Tipo.INTERNO,
        ativo=True,
    ).first()

    if not protocolo_geral:
        messages.error(request, 'Departamento marcado como "PROTOCOLO GERAL" não encontrado (INTERNO/ativo).')
        return redirect("home")

    pessoa = None
    pessoa_status = None

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
                processo.responsavel_setor = None
                processo.save(update_fields=["recebido_em", "recebido_por", "responsavel_setor"])

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
    ativo = (request.GET.get("ativo") or "").strip()

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


# =============================================================================
# Dashboards
# =============================================================================

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
    ultimos = list(qs.prefetch_related("interessados").order_by("-criado_em")[:8])

    processos = list(qs.order_by("-criado_em")[:300])
    for p in processos:
        pend, _setor = setor_esta_pendente_de_recebimento(p)
        if pend:
            pendentes += 1

    por_status = qs.values("status").annotate(qtd=Count("id")).order_by("status")
    por_prioridade = qs.values("prioridade").annotate(qtd=Count("id")).order_by("prioridade")

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
            "cards": {"total": total, "ativos": ativos, "arquivados": arquivados, "pendentes": pendentes},
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

    setores = (
        Departamento.objects
        .filter(tipo=Departamento.Tipo.INTERNO, ativo=True)
        .filter(
            Q(responsavel_id=request.user.id)
            | Q(substituto_id=request.user.id)
            | Q(membros__user_id=request.user.id, membros__ativo=True)
        )
        .distinct()
        .order_by("nome")
    )

    setores_ids = list(set(setores.values_list("id", flat=True)))

    if not eh_admin:
        qs = qs.filter(setor_atual_id__in=setores_ids)
        qs = qs.filter(Q(responsavel_setor__isnull=True) | Q(responsavel_setor_id=request.user.id))

    pendentes = []
    no_setor = []

    processos = list(qs.prefetch_related("interessados").order_by("-criado_em")[:300])

    for p in processos:
        pend, setor_atual = setor_esta_pendente_de_recebimento(p)
        if not setor_atual:
            continue
        p.pendente_recebimento = pend

        if pend:
            pendentes.append(p)
        else:
            no_setor.append(p)

    ultimos = list(qs.prefetch_related("interessados").order_by("-criado_em")[:8])

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
# CADASTROS (ADMIN)
# =============================================================================

@login_required
def tipos_list(request):
    if not _somente_admin(request.user):
        return HttpResponseForbidden("Somente ADMIN pode acessar cadastros.")

    q = (request.GET.get("q") or "").strip()
    ativo = (request.GET.get("ativo") or "").strip()

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


# =============================================================================
# AJAX destinos (para atualizar o select conforme tipo/ação)
# =============================================================================

@require_GET
@login_required
def destinos_departamento_lookup(request, pk: int):
    """
    Retorna destinos possíveis para o processo (pk),
    baseado em tipo_tramitacao + acao selecionados na tela.
    """
    processo = get_object_or_404(Processo.objects.prefetch_related("movimentacoes"), pk=pk)

    tipo = (request.GET.get("tipo") or "").strip()
    acao = (request.GET.get("acao") or "").strip()

    # ✅ se for ARQUIVADO: não existe destino para escolher (vai ser automático)
    if acao == MovimentacaoProcesso.Acao.ARQUIVADO:
        return JsonResponse({"results": []})

    last = (
        processo.movimentacoes
        .select_related("departamento_origem", "departamento_destino")
        .order_by("-registrado_em")
        .first()
    )
    origem = (last.departamento_destino or last.departamento_origem) if last else None

    if not origem:
        origem = Departamento.objects.filter(eh_protocolo_geral=True, tipo=Departamento.Tipo.INTERNO, ativo=True).first()

    if not origem:
        return JsonResponse({"results": []})

    if origem.tipo == Departamento.Tipo.EXTERNO:
        return JsonResponse({"results": []})

    qs = Departamento.objects.filter(ativo=True)

    if tipo == MovimentacaoProcesso.TipoTramitacao.INTERNA:
        qs = qs.filter(tipo=Departamento.Tipo.INTERNO)

    elif tipo == MovimentacaoProcesso.TipoTramitacao.EXTERNA:
        if acao == MovimentacaoProcesso.Acao.DEVOLVIDO:
            qs = qs.filter(tipo=Departamento.Tipo.INTERNO)
        else:
            qs = qs.filter(tipo=Departamento.Tipo.EXTERNO)
    else:
        qs = qs.filter(tipo=Departamento.Tipo.INTERNO)

    if not getattr(origem, "eh_protocolo_geral", False):
        qs = qs.exclude(eh_protocolo_geral=True)

    qs = qs.exclude(id=origem.id)

    results = [{"id": d.id, "nome": d.nome} for d in qs.order_by("nome")]
    return JsonResponse({"results": results})
