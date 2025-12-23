from django.conf import settings
from django.db import models, transaction
from django.utils import timezone

from .cadastros import Pessoa, TipoProcesso


class SequenciaProcesso(models.Model):
    ano = models.PositiveIntegerField(unique=True)
    ultimo_numero = models.PositiveIntegerField(default=0)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Sequência de Processo"
        verbose_name_plural = "Sequências de Processo"

    def __str__(self) -> str:
        return f"{self.ano} -> {self.ultimo_numero}"


class Processo(models.Model):
    class Prioridade(models.TextChoices):
        NORMAL = "NORMAL", "Normal"
        URGENTE = "URGENTE", "Urgente"

    class Status(models.TextChoices):
        ATIVO = "ATIVO", "Ativo"
        ARQUIVADO = "ARQUIVADO", "Arquivado"

    ano = models.PositiveIntegerField()
    numero_sequencial = models.PositiveIntegerField()
    numero_formatado = models.CharField(max_length=12, db_index=True)

    tipo_processo = models.ForeignKey(TipoProcesso, on_delete=models.PROTECT, related_name="processos")
    assunto = models.CharField(max_length=255)
    descricao = models.TextField(blank=True, null=True)

    prioridade = models.CharField(max_length=10, choices=Prioridade.choices, default=Prioridade.NORMAL)
    status = models.CharField(max_length=10, choices=Status.choices, default=Status.ATIVO)

    interessados = models.ManyToManyField(Pessoa, through="ProcessoInteressado", related_name="processos")

    criado_em = models.DateTimeField(auto_now_add=True)
    criado_por = models.ForeignKey(settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name="processos_criados")

    class Meta:
        constraints = [
            models.UniqueConstraint(fields=["ano", "numero_sequencial"], name="uniq_processo_ano_numero"),
        ]
        ordering = ["-criado_em"]
        verbose_name = "Processo"
        verbose_name_plural = "Processos"

    def __str__(self) -> str:
        return self.numero_formatado

    @staticmethod
    def format_numero(numero: int, ano: int) -> str:
        return f"{numero:05d}/{ano}"

    @classmethod
    def criar_com_sequencia(
        cls,
        *,
        tipo_processo: TipoProcesso,
        assunto: str,
        descricao: str | None,
        criado_por,
        interessados: list[Pessoa],
        prioridade: str = Prioridade.NORMAL,
    ) -> "Processo":
        if not interessados:
            raise ValueError("O processo deve ter pelo menos 1 interessado.")

        ano = timezone.now().year

        with transaction.atomic():
            seq, _ = SequenciaProcesso.objects.select_for_update().get_or_create(ano=ano)
            seq.ultimo_numero += 1
            seq.save(update_fields=["ultimo_numero", "atualizado_em"])

            numero = seq.ultimo_numero
            numero_formatado = cls.format_numero(numero, ano)

            processo = cls.objects.create(
                ano=ano,
                numero_sequencial=numero,
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
