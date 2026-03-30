from __future__ import annotations

from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .cadastros import Departamento
from .processos import Processo


def origem_id_equals_destino(origem: Departamento, destino: Departamento) -> bool:
    return bool(origem and destino and origem.pk and destino.pk and origem.pk == destino.pk)


class MovimentacaoProcesso(models.Model):
    class TipoTramitacao(models.TextChoices):
        INTERNA = "INTERNA", "Interna"
        EXTERNA = "EXTERNA", "Externa"

    class Acao(models.TextChoices):
        ENCAMINHADO = "ENCAMINHADO", "Encaminhado"
        RECEBIDO = "RECEBIDO", "Recebido"
        DEVOLVIDO = "DEVOLVIDO", "Devolvido"   # ✅ retorno do externo
        ARQUIVADO = "ARQUIVADO", "Arquivado"

        # ✅ registro histórico (não libera tramitação)
        RECEBIDO_EXTERNO = "RECEBIDO_EXTERNO", "Recebido Externo"

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="movimentacoes")
    tipo_tramitacao = models.CharField(max_length=10, choices=TipoTramitacao.choices)
    acao = models.CharField(max_length=20, choices=Acao.choices)

    departamento_origem = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="movimentacoes_origem",
    )
    departamento_destino = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="movimentacoes_destino",
        blank=True,
        null=True,
    )

    observacao = models.TextField(blank=True, null=True)
    registrado_em = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimentacoes_registradas",
    )

    class Meta:
        ordering = ["-registrado_em"]
        verbose_name = "Movimentação do Processo"
        verbose_name_plural = "Movimentações do Processo"

    def __str__(self) -> str:
        return f"{self.processo.numero_formatado} - {self.acao} ({self.tipo_tramitacao})"

    def clean(self):
        """
        Regras do MODEL (consistência do dado).
        Regras de permissão (admin/protocolista/membros do setor) ficam no FORM/VIEW/SERVICE.
        """
        errors: dict[str, str] = {}

        origem = self.departamento_origem
        destino = self.departamento_destino
        acao = self.acao
        tipo = self.tipo_tramitacao

        # ------------------------------------------------------------
        # Processo ARQUIVADO não aceita novas tramitações
        # ------------------------------------------------------------
        if self.processo_id and getattr(self.processo, "status", None) == Processo.Status.ARQUIVADO:
            errors["acao"] = "Este processo já está ARQUIVADO e não pode mais ser tramitado."

        # ------------------------------------------------------------
        # Se ARQUIVADO: destino deve ser vazio
        # ------------------------------------------------------------
        if acao == self.Acao.ARQUIVADO:
            self.departamento_destino = None
            if errors:
                raise ValidationError(errors)
            return

        # ------------------------------------------------------------
        # ENCAMINHADO / DEVOLVIDO exigem destino
        # ------------------------------------------------------------
        if acao in (self.Acao.ENCAMINHADO, self.Acao.DEVOLVIDO) and not destino:
            errors["departamento_destino"] = "Destino é obrigatório para esta ação."

        # RECEBIDO_EXTERNO normalmente terá destino (o órgão externo atual)
        if acao == self.Acao.RECEBIDO_EXTERNO and not destino:
            errors["departamento_destino"] = "Destino é obrigatório para RECEBIDO EXTERNO."

        # ------------------------------------------------------------
        # origem == destino
        # - Proibido para ENCAMINHADO/DEVOLVIDO/RECEBIDO_EXTERNO
        # - Permitido para RECEBIDO (evento no próprio setor)
        # ------------------------------------------------------------
        if origem and destino and origem_id_equals_destino(origem, destino):
            if acao in (self.Acao.ENCAMINHADO, self.Acao.DEVOLVIDO, self.Acao.RECEBIDO_EXTERNO):
                errors["departamento_destino"] = "O destino não pode ser o mesmo da origem."

        # ------------------------------------------------------------
        # REGRAS POR TIPO
        # ------------------------------------------------------------
        if tipo == self.TipoTramitacao.INTERNA:
            if origem and origem.tipo != Departamento.Tipo.INTERNO:
                errors["departamento_origem"] = "A origem deve ser um departamento INTERNO."

            if destino and destino.tipo != Departamento.Tipo.INTERNO:
                errors["departamento_destino"] = "Destino deve ser INTERNO para tramitação INTERNA."

            if acao not in (self.Acao.ENCAMINHADO, self.Acao.RECEBIDO, self.Acao.ARQUIVADO):
                errors["acao"] = "Ação não é permitida na tramitação INTERNA."

        elif tipo == self.TipoTramitacao.EXTERNA:
            if acao not in (self.Acao.ENCAMINHADO, self.Acao.DEVOLVIDO, self.Acao.RECEBIDO_EXTERNO):
                if acao == self.Acao.RECEBIDO:
                    errors["acao"] = "Ação RECEBIDO não é permitida na tramitação EXTERNA."
                else:
                    errors["acao"] = "Ação não é permitida na tramitação EXTERNA."

            # ENCAMINHADO EXTERNO: origem INTERNO -> destino EXTERNO
            if acao == self.Acao.ENCAMINHADO:
                if origem and origem.tipo != Departamento.Tipo.INTERNO:
                    errors["departamento_origem"] = "Para ENCAMINHAR EXTERNO, a origem deve ser INTERNA."
                if destino and destino.tipo != Departamento.Tipo.EXTERNO:
                    errors["departamento_destino"] = "Para ENCAMINHAR EXTERNO, o destino deve ser EXTERNO."

            # DEVOLVIDO (RETORNO): origem EXTERNO -> destino INTERNO
            elif acao == self.Acao.DEVOLVIDO:
                if origem and origem.tipo != Departamento.Tipo.EXTERNO:
                    errors["departamento_origem"] = "Para DEVOLVER (retorno), a origem deve ser EXTERNA."
                if destino and destino.tipo != Departamento.Tipo.INTERNO:
                    errors["departamento_destino"] = "Para DEVOLVER (retorno), o destino deve ser INTERNO."

            # RECEBIDO_EXTERNO (histórico)
            elif acao == self.Acao.RECEBIDO_EXTERNO:
                if origem and origem.tipo != Departamento.Tipo.INTERNO:
                    errors["departamento_origem"] = "Para RECEBIDO EXTERNO, a origem deve ser INTERNA."
                if destino and destino.tipo != Departamento.Tipo.EXTERNO:
                    errors["departamento_destino"] = "Para RECEBIDO EXTERNO, o destino deve ser EXTERNO."

        # ------------------------------------------------------------
        # Regra: depois que sai do PROTOCOLO GERAL, não volta
        # ------------------------------------------------------------
        if destino and getattr(destino, "eh_protocolo_geral", False):
            if not (origem and getattr(origem, "eh_protocolo_geral", False)):
                errors["departamento_destino"] = "Não é permitido encaminhar para o PROTOCOLO GERAL."

        if errors:
            raise ValidationError(errors)
