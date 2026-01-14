from .models import MovimentacaoProcesso, Processo

def get_setor_atual_do_processo(processo: Processo):
    ultima = (
        processo.movimentacoes
        .exclude(departamento_destino__isnull=True)
        .select_related("departamento_destino")
        .order_by("-registrado_em")
        .first()
    )
    return ultima.departamento_destino if ultima else None


def setor_esta_pendente_de_recebimento(processo: Processo):
    setor_atual = get_setor_atual_do_processo(processo)
    if not setor_atual:
        return False, None  # não está em setor (ainda no protocolo)

    # Última chegada ao setor atual
    ultima_chegada = (
        processo.movimentacoes
        .filter(
            acao=MovimentacaoProcesso.Acao.ENCAMINHADO,
            departamento_destino_id=setor_atual.id,
        )
        .order_by("-registrado_em")
        .first()
    )

    if not ultima_chegada:
        # se por algum motivo não houver "chegada", não bloqueia
        return False, setor_atual

    # Existe RECEBIDO depois da chegada?
    recebido_depois = processo.movimentacoes.filter(
        acao=MovimentacaoProcesso.Acao.RECEBIDO,
        departamento_destino_id=setor_atual.id,  # recebido "no setor"
        registrado_em__gt=ultima_chegada.registrado_em,
    ).exists()

    pendente = not recebido_depois
    return pendente, setor_atual
