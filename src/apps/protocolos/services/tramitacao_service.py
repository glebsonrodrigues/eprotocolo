from django.db import transaction
from django.core.exceptions import ValidationError

from protocolos.models import (
    Processo,
    MovimentacaoProcesso,
    Comprovante,
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
    """

    if processo.status == Processo.Status.ARQUIVADO:
        raise ValidationError("Processo arquivado não pode ser tramitado.")

    movimentacao = MovimentacaoProcesso.objects.create(
        processo=processo,
        tipo_tramitacao=tipo_tramitacao,
        acao=acao,
        departamento_origem=departamento_origem,
        departamento_destino=departamento_destino,
        observacao=observacao,
        registrado_por=usuario,
    )

    # Atualiza status do processo se necessário
    if acao == MovimentacaoProcesso.Acao.ARQUIVADO:
        processo.status = Processo.Status.ARQUIVADO
        processo.save(update_fields=["status"])

    # Gera comprovante automaticamente
    Comprovante.objects.create(
        processo=processo,
        movimentacao=movimentacao,
        tipo=Comprovante.Tipo.MOVIMENTACAO,
        emitido_por=usuario,
    )

    return movimentacao
