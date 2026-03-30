from __future__ import annotations

from django.db.models import Q

from .models import Departamento, MovimentacaoProcesso, Processo


def get_ultima_movimentacao(processo: Processo) -> MovimentacaoProcesso | None:
    """
    Retorna a última movimentação do processo (independente de ter destino ou não).
    """
    return (
        processo.movimentacoes
        .select_related("departamento_origem", "departamento_destino")
        .order_by("-registrado_em")
        .first()
    )


def get_setor_atual_do_processo(processo: Processo) -> Departamento | None:
    """
    Setor atual = destino da última movimentação (se houver),
    senão (fallback) origem da última movimentação.
    - Isso cobre ARQUIVADO (destino=None), onde o setor atual fica sendo a origem.
    """
    ultima = get_ultima_movimentacao(processo)
    if not ultima:
        return None
    return ultima.departamento_destino or ultima.departamento_origem


def setor_esta_pendente_de_recebimento(processo: Processo) -> tuple[bool, Departamento | None]:
    """
    Regras:
    - Processo ARQUIVADO: nunca pendente.
    - Se setor atual for EXTERNO: NÃO existe recebimento -> nunca pendente.
    - Se setor atual for INTERNO:
        - identifica a última "chegada" ao setor (pode ser):
            a) INTERNA + ENCAMINHADO
            b) EXTERNA + DEVOLVIDO (retorno ao interno)
        - fica pendente se NÃO existir um RECEBIDO (INTERNA) depois dessa chegada.
    """
    setor_atual = get_setor_atual_do_processo(processo)
    if not setor_atual:
        return False, None

    # ✅ ARQUIVADO: não faz sentido ficar pendente
    if getattr(processo, "status", None) == Processo.Status.ARQUIVADO:
        return False, setor_atual

    # ✅ EXTERNO: nunca pendente (não existe recebimento para órgão externo)
    if setor_atual.tipo == Departamento.Tipo.EXTERNO:
        return False, setor_atual

    # ✅ Última chegada ao setor interno (encaminhado interno OU devolvido externo)
    ultima_chegada = (
        processo.movimentacoes
        .filter(departamento_destino_id=setor_atual.id)
        .filter(
            Q(
                tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.INTERNA,
                acao=MovimentacaoProcesso.Acao.ENCAMINHADO,
            )
            | Q(
                tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.EXTERNA,
                acao=MovimentacaoProcesso.Acao.DEVOLVIDO,
            )
        )
        .order_by("-registrado_em")
        .first()
    )

    # Se não houver "chegada" detectável, não bloqueia.
    # Ex.: processo criado no PROTOCOLO GERAL já com RECEBIDO no próprio setor.
    if not ultima_chegada:
        return False, setor_atual

    # ✅ Pendente se NÃO existe RECEBIDO depois da chegada (recebido é sempre INTERNO)
    recebido_depois = (
        processo.movimentacoes
        .filter(
            tipo_tramitacao=MovimentacaoProcesso.TipoTramitacao.INTERNA,
            acao=MovimentacaoProcesso.Acao.RECEBIDO,
            departamento_destino_id=setor_atual.id,
            registrado_em__gt=ultima_chegada.registrado_em,
        )
        .exists()
    )

    return (not recebido_depois), setor_atual
