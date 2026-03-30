from __future__ import annotations

from django.core.exceptions import ValidationError
from django.db import transaction
from django.utils import timezone

from protocolos.models import (
    Processo,
    MovimentacaoProcesso,
    TramitacaoExterna,
    Comprovante,
)


def _obter_tramitacao_externa_ativa(*, processo: Processo) -> TramitacaoExterna | None:
    return (
        TramitacaoExterna.objects
        .filter(processo=processo, status=TramitacaoExterna.Status.AGUARDANDO)
        .order_by("-enviado_em")
        .first()
    )


@transaction.atomic
def tramitar_processo(
    *,
    processo: Processo,
    tipo_tramitacao: str,
    acao: str,
    departamento_origem,
    departamento_destino,
    usuario,
    observacao: str | None = None,
):
    """
    Registra uma movimentação de processo de forma segura e consistente.

    Regras:
    - Processo ARQUIVADO não pode tramitar
    - Se existir tramitação EXTERNA ativa, bloqueia tramitação INTERNA
    - Ao salvar movimentação, gera Comprovante automaticamente
    """

    if processo.status == Processo.Status.ARQUIVADO:
        raise ValidationError("Processo arquivado não pode ser tramitado.")

    # ✅ Controle real: se existe tramitação externa ativa, bloqueia tramitação INTERNA
    externa_ativa = _obter_tramitacao_externa_ativa(processo=processo)
    if externa_ativa and tipo_tramitacao == MovimentacaoProcesso.TipoTramitacao.INTERNA:
        raise ValidationError(
            "Este processo está em tramitação EXTERNA e aguarda retorno. "
            "Registre o retorno externo antes de tramitar internamente."
        )

    movimentacao = MovimentacaoProcesso.objects.create(
        processo=processo,
        tipo_tramitacao=tipo_tramitacao,
        acao=acao,
        departamento_origem=departamento_origem,
        departamento_destino=departamento_destino,
        observacao=observacao,
        registrado_por=usuario,
    )

    # ✅ Se arquivou, atualiza status do processo
    # (OBS: seu model MovimentacaoProcesso.save() também faz isso,
    # mas aqui mantém robustez caso você altere o model no futuro)
    if acao == MovimentacaoProcesso.Acao.ARQUIVADO:
        if processo.status != Processo.Status.ARQUIVADO:
            processo.status = Processo.Status.ARQUIVADO
            processo.save(update_fields=["status"])

    # ✅ Gera comprovante automaticamente
    Comprovante.objects.create(
        processo=processo,
        movimentacao=movimentacao,
        tipo=Comprovante.Tipo.MOVIMENTACAO,
        emitido_por=usuario,
    )

    return movimentacao


@transaction.atomic
def encaminhar_processo_externo(
    *,
    processo_id: int,
    departamento_origem,
    departamento_destino_externo,
    usuario,
    orgao_externo: str,
    meio_envio: str = TramitacaoExterna.MeioEnvio.OFICIO,
    protocolo_envio: str = "",
    prazo_retorno_em=None,
    contato_nome: str = "",
    contato_email: str = "",
    contato_telefone: str = "",
    observacoes_envio: str = "",
    anexo_envio=None,
) -> TramitacaoExterna:
    """
    Encaminha processo para órgão externo com controle robusto (MySQL):
    - trava o Processo no banco (select_for_update)
    - garante que só existe 1 Tramitação Externa AGUARDANDO por vez (regra aplicada por query)
    - cria TramitacaoExterna (controle)
    - registra MovimentacaoProcesso EXTERNA/ENCAMINHADO (histórico) + Comprovante
    """

    # 🔒 trava o registro do processo para evitar condição de corrida
    processo = Processo.objects.select_for_update().get(pk=processo_id)

    if processo.status == Processo.Status.ARQUIVADO:
        raise ValidationError("Processo arquivado não pode ser tramitado.")

    # ✅ garante 1 externa ativa por vez (robusto em MySQL)
    if TramitacaoExterna.objects.filter(
        processo=processo,
        status=TramitacaoExterna.Status.AGUARDANDO
    ).exists():
        raise ValidationError("Já existe uma tramitação externa AGUARDANDO retorno para este processo.")

    # 1) cria o controle externo
    tr_ext = TramitacaoExterna(
        processo=processo,
        orgao_externo=orgao_externo,
        contato_nome=contato_nome,
        contato_email=contato_email,
        contato_telefone=contato_telefone,
        meio_envio=meio_envio,
        protocolo_envio=protocolo_envio,
        enviado_em=timezone.now(),
        prazo_retorno_em=prazo_retorno_em,
        status=TramitacaoExterna.Status.AGUARDANDO,
        observacoes_envio=observacoes_envio,
    )

    # ✅ FileField: só setar se vier arquivo (não usar "")
    if anexo_envio:
        tr_ext.anexo_envio = anexo_envio

    tr_ext.full_clean()
    tr_ext.save()

    # 2) registra no histórico (movimentação externa) + comprovante via função padrão
    tramitar_processo(
        processo=processo,
        tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.EXTERNA,
        acao=MovimentacaoProcesso.Acao.ENCAMINHADO,
        departamento_origem=departamento_origem,
        departamento_destino=departamento_destino_externo,
        usuario=usuario,
        observacao=observacoes_envio,
    )

    return tr_ext


@transaction.atomic
def registrar_retorno_externo(
    *,
    processo_id: int,
    departamento_destino_interno,
    usuario,
    orgao_que_respondeu: str | None = None,
    acao_retorno: str = MovimentacaoProcesso.Acao.RECEBIDO,  # ou DEVOLVIDO
    observacoes_retorno: str = "",
    anexo_retorno=None,
    recebido_em=None,
) -> TramitacaoExterna:
    """
    Registra retorno do órgão externo:
    - trava o Processo no banco (select_for_update)
    - fecha a Tramitação Externa ativa (RESPONDIDO)
    - cria MovimentacaoProcesso INTERNA (RECEBIDO/DEVOLVIDO) + Comprovante
    - permite retorno por órgão diferente do envio (orgao_que_respondeu)
    """

    # 🔒 trava o registro do processo (consistência)
    processo = Processo.objects.select_for_update().get(pk=processo_id)

    if processo.status == Processo.Status.ARQUIVADO:
        raise ValidationError("Processo arquivado não pode receber retorno externo.")

    tr_ext = (
        TramitacaoExterna.objects
        .filter(processo=processo, status=TramitacaoExterna.Status.AGUARDANDO)
        .order_by("-enviado_em")
        .first()
    )
    if not tr_ext:
        raise ValidationError("Não existe tramitação externa AGUARDANDO retorno para este processo.")

    if acao_retorno not in (MovimentacaoProcesso.Acao.RECEBIDO, MovimentacaoProcesso.Acao.DEVOLVIDO):
        raise ValidationError("Ação de retorno inválida. Use RECEBIDO ou DEVOLVIDO.")

    # 1) fecha o controle externo
    tr_ext.status = TramitacaoExterna.Status.RESPONDIDO
    tr_ext.recebido_em = recebido_em or timezone.now()
    tr_ext.observacoes_retorno = observacoes_retorno

    # A foi, C respondeu -> registra C aqui
    if orgao_que_respondeu:
        tr_ext.orgao_externo = orgao_que_respondeu

    # ✅ FileField: só setar se vier arquivo
    if anexo_retorno:
        tr_ext.anexo_retorno = anexo_retorno

    tr_ext.full_clean()
    tr_ext.save()

    # 2) define origem do retorno (o último destino externo encaminhado)
    ultima_mov_externa = (
        MovimentacaoProcesso.objects
        .filter(
            processo=processo,
            tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.EXTERNA,
            acao=MovimentacaoProcesso.Acao.ENCAMINHADO,
        )
        .order_by("-registrado_em")
        .first()
    )

    departamento_origem = (
        ultima_mov_externa.departamento_destino
        if ultima_mov_externa and ultima_mov_externa.departamento_destino
        else departamento_destino_interno
    )

    # 3) movimentação interna de retorno + comprovante
    tramitar_processo(
        processo=processo,
        tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.INTERNA,
        acao=acao_retorno,
        departamento_origem=departamento_origem,
        departamento_destino=departamento_destino_interno,
        usuario=usuario,
        observacao=observacoes_retorno,
    )

    return tr_ext


@transaction.atomic
def cancelar_tramitacao_externa(
    *,
    processo_id: int,
    usuario,
    motivo: str = "",
) -> TramitacaoExterna:
    """
    Cancela a tramitação externa ativa (se enviado por engano).
    """
    processo = Processo.objects.select_for_update().get(pk=processo_id)

    tr_ext = (
        TramitacaoExterna.objects
        .filter(processo=processo, status=TramitacaoExterna.Status.AGUARDANDO)
        .order_by("-enviado_em")
        .first()
    )
    if not tr_ext:
        raise ValidationError("Não existe tramitação externa ativa para cancelar.")

    tr_ext.status = TramitacaoExterna.Status.CANCELADO
    tr_ext.recebido_em = timezone.now()
    tr_ext.observacoes_retorno = motivo

    tr_ext.full_clean()
    tr_ext.save()

    return tr_ext
