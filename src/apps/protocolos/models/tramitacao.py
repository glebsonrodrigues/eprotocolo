from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models
from django.utils import timezone

from .processos import Processo
from .cadastros import Departamento


class MovimentacaoProcesso(models.Model):
    class TipoTramitacao(models.TextChoices):
        INTERNA = "INTERNA", "Interna"
        EXTERNA = "EXTERNA", "Externa"

    class Acao(models.TextChoices):
        ENCAMINHADO = "ENCAMINHADO", "Encaminhado"
        RECEBIDO = "RECEBIDO", "Recebido"
        DEVOLVIDO = "DEVOLVIDO", "Devolvido"
        ARQUIVADO = "ARQUIVADO", "Arquivado"

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="movimentacoes")
    tipo_tramitacao = models.CharField(max_length=10, choices=TipoTramitacao.choices)
    acao = models.CharField(max_length=12, choices=Acao.choices)

    departamento_origem = models.ForeignKey(
        Departamento, on_delete=models.PROTECT, related_name="movimentacoes_origem"
    )
    departamento_destino = models.ForeignKey(
        Departamento, on_delete=models.PROTECT, related_name="movimentacoes_destino",
        blank=True, null=True
    )

    observacao = models.TextField(blank=True, null=True)
    registrado_em = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="movimentacoes_registradas"
    )

    class Meta:
        ordering = ["-registrado_em"]
        verbose_name = "Movimentação do Processo"
        verbose_name_plural = "Movimentações do Processo"

    def __str__(self) -> str:
        return f"{self.processo.numero_formatado} - {self.acao} ({self.tipo_tramitacao})"

    def clean(self):
        # Origem sempre INTERNO (pela regra do seu ER)
        if self.departamento_origem and self.departamento_origem.tipo != Departamento.Tipo.INTERNO:
            raise ValidationError({"departamento_origem": "A origem deve ser um departamento INTERNO."})

        # ENCAMINHADO exige destino
        if self.acao == self.Acao.ENCAMINHADO and not self.departamento_destino:
            raise ValidationError({"departamento_destino": "Destino é obrigatório para ENCAMINHAR."})

        # Regras por tipo de tramitação
        if self.departamento_destino:
            if self.tipo_tramitacao == self.TipoTramitacao.INTERNA:
                if self.departamento_destino.tipo != Departamento.Tipo.INTERNO:
                    raise ValidationError({"departamento_destino": "Destino deve ser INTERNO para tramitação INTERNA."})
            elif self.tipo_tramitacao == self.TipoTramitacao.EXTERNA:
                if self.departamento_destino.tipo != Departamento.Tipo.EXTERNO:
                    raise ValidationError({"departamento_destino": "Destino deve ser EXTERNO para tramitação EXTERNA."})

        # Se ARQUIVADO, destino pode ficar vazio (ok)

    def save(self, *args, **kwargs):
        self.full_clean()
        super().save(*args, **kwargs)

        # Se arquivar, muda status do processo
        if self.acao == self.Acao.ARQUIVADO and self.processo.status != Processo.Status.ARQUIVADO:
            self.processo.status = Processo.Status.ARQUIVADO
            self.processo.save(update_fields=["status"])
