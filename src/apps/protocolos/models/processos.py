from __future__ import annotations
from django.conf import settings
from django.db import models, transaction
from .cadastros import Pessoa, TipoProcesso


class Processo(models.Model):
    class Prioridade(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        URGENTE = "URGENTE", "Urgente"

    class Status(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        ARQUIVADO = "ARQUIVADO", "Arquivado"

    # ✅ MANUAL: 0000/00
    ano = models.PositiveIntegerField()  # 0..99 (dois dígitos)
    numero_manual = models.PositiveIntegerField()  # 0..9999 (quatro dígitos)
    numero_formatado = models.CharField(max_length=7, db_index=True, unique=True)

    tipo_processo = models.ForeignKey(TipoProcesso, on_delete=models.PROTECT, related_name="processos")
    assunto = models.CharField(max_length=255)
    descricao = models.TextField(blank=True, null=True)

    prioridade = models.CharField(max_length=10, choices=Prioridade.choices, default=Prioridade.NORMAL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ATIVO)

    interessados = models.ManyToManyField(Pessoa, through="ProcessoInteressado", related_name="processos")

    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="processos_criados",
    )

    recebido_em = models.DateTimeField(null=True, blank=True)
    recebido_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="processos_recebidos",
    )

    arquivado_em = models.DateTimeField(null=True, blank=True)
    arquivado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        null=True,
        blank=True,
        related_name="processos_arquivados",
    )

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ano", "numero_manual"], name="uniq_processo_ano_numero_manual"),
        ]
        ordering = ["-criado_em"]
        verbose_name = "Processo"
        verbose_name_plural = "Processos"

    def __str__(self) -> str:
        return self.numero_formatado

    @staticmethod
    def format_numero(numero_manual: int, ano_2d: int) -> str:
        # 4 dígitos / 2 dígitos
        return f"{numero_manual:04d}/{ano_2d:02d}"

    @classmethod
    def criar_manual(
        cls,
        *,
        numero_manual: int,
        ano_2d: int,
        tipo_processo: TipoProcesso,
        assunto: str,
        descricao: str | None,
        criado_por,
        interessados: list[Pessoa],
        prioridade: str = Prioridade.NORMAL,
    ) -> "Processo":
        if not interessados:
            raise ValueError("O processo deve ter pelo menos 1 interessado.")

        numero_formatado = cls.format_numero(numero_manual, ano_2d)

        with transaction.atomic():
            # garante duplicidade (server-side)
            if cls.objects.select_for_update().filter(numero_formatado__iexact=numero_formatado).exists():
                raise ValueError(f"Já existe um processo com o número {numero_formatado}.")

            processo = cls.objects.create(
                ano=ano_2d,
                numero_manual=numero_manual,
                numero_formatado=numero_formatado,
                tipo_processo=tipo_processo,
                assunto=assunto,
                descricao=descricao,
                prioridade=prioridade,
                criado_por=criado_por,
            )

            ProcessoInteressado.objects.bulk_create(
                [ProcessoInteressado(processo=processo, pessoa=p) for p in interessados]
            )

        return processo


class ProcessoInteressado(models.Model):
    processo = models.ForeignKey(Processo, on_delete=models.CASCADE)
    pessoa = models.ForeignKey(Pessoa, on_delete=models.PROTECT)
    papel = models.CharField(max_length=50, blank=True, null=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["processo", "pessoa"], name="uniq_processo_interessado"),
        ]
        verbose_name = "Interessado do Processo"
        verbose_name_plural = "Interessados do Processo"

    def __str__(self) -> str:
        return f"{self.processo.numero_formatado} -> {self.pessoa.nome}"
