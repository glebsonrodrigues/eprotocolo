import uuid
from django.conf import settings
from django.db import models

from .processos import Processo
from .tramitacao import MovimentacaoProcesso


class Comprovante(models.Model):
    class Tipo(models.TextChoices):
        ABERTURA = "ABERTURA", "Abertura"
        MOVIMENTACAO = "MOVIMENTACAO", "Movimentação"

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="comprovantes")
    movimentacao = models.ForeignKey(MovimentacaoProcesso, on_delete=models.SET_NULL, blank=True, null=True)
    tipo = models.CharField(max_length=12, choices=Tipo.choices)

    codigo_autenticacao = models.CharField(max_length=64, unique=True, editable=False)
    emitido_em = models.DateTimeField(auto_now_add=True)
    emitido_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="comprovantes_emitidos")

    class Meta:
        ordering = ["-emitido_em"]
        verbose_name = "Comprovante"
        verbose_name_plural = "Comprovantes"

    def __str__(self) -> str:
        return f"{self.tipo} - {self.codigo_autenticacao}"

    def save(self, *args, **kwargs):
        if not self.codigo_autenticacao:
            self.codigo_autenticacao = uuid.uuid4().hex  # 32 chars
        return super().save(*args, **kwargs)
