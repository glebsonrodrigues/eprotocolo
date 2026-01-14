from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import EmailValidator
from django.db import models

from core.validators import only_digits, validate_cpf, format_cpf, format_br_phone


class TimeStampedModel(models.Model):
    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        abstract = True


class Pessoa(TimeStampedModel):
    nome = models.CharField(max_length=50)
    cpf = models.CharField(max_length=11, unique=True, help_text="Somente números (11 dígitos).")
    email = models.EmailField(max_length=254, blank=True, null=True)
    telefone = models.CharField(max_length=20, help_text="Somente números (DDD + número).")
    whatsapp = models.CharField(max_length=20, blank=True, null=True, help_text="Somente números (DDD + número).")
    ativo = models.BooleanField(default=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Pessoa"
        verbose_name_plural = "Pessoas"

    def __str__(self) -> str:
        return f"{self.nome} - {self.cpf_formatado}"

    @property
    def cpf_formatado(self) -> str:
        return format_cpf(self.cpf)

    @property
    def telefone_formatado(self) -> str:
        return format_br_phone(self.telefone)

    @property
    def whatsapp_formatado(self) -> str:
        return format_br_phone(self.whatsapp or "")

    def clean(self):
        if self.nome:
            self.nome = self.nome.strip().upper()

        self.cpf = validate_cpf(self.cpf)

        if self.email:
            EmailValidator()(self.email)

        self.telefone = only_digits(self.telefone)
        if len(self.telefone) < 10:
            raise ValidationError({"telefone": "Telefone inválido. Informe DDD + número."})

        if self.whatsapp:
            self.whatsapp = only_digits(self.whatsapp)
            if len(self.whatsapp) < 10:
                raise ValidationError({"whatsapp": "WhatsApp inválido. Informe DDD + número."})

    def save(self, *args, **kwargs):
        self.full_clean()
        return super().save(*args, **kwargs)


class TipoProcesso(models.Model):
    nome = models.CharField(max_length=120, unique=True)
    descricao = models.TextField()
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["nome"]
        verbose_name = "Tipo de Processo"
        verbose_name_plural = "Tipos de Processo"

    def __str__(self) -> str:
        return self.nome


class Departamento(models.Model):
    class Tipo(models.TextChoices):
        INTERNO = "INTERNO", "Interno"
        EXTERNO = "EXTERNO", "Externo"

    nome = models.CharField(max_length=150)
    sigla = models.CharField(max_length=20, blank=True, null=True)
    tipo = models.CharField(max_length=10, choices=Tipo.choices)
    ativo = models.BooleanField(default=True)

    # ✅ flags robustas (não depende de nome)
    eh_protocolo_geral = models.BooleanField(default=False)
    eh_arquivo_geral = models.BooleanField(default=False)

    # ✅ seus campos atuais (podem continuar existindo)
    responsavel = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="departamentos_responsavel",
        null=True,
        blank=True,
    )
    substituto = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="departamentos_substituto",
        null=True,
        blank=True,
    )

    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "nome"]
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"
        constraints = [
            models.UniqueConstraint(fields=["nome", "tipo"], name="uniq_departamento_nome_tipo"),
        ]

    def clean(self):
        # ✅ não pode ser PG e Arquivo Geral ao mesmo tempo
        if self.eh_protocolo_geral and self.eh_arquivo_geral:
            raise ValidationError("Um departamento não pode ser PROTOCOLO GERAL e ARQUIVO GERAL ao mesmo tempo.")

        # regra opcional: substituto não pode ser igual ao responsável
        if self.responsavel and self.substituto and self.responsavel_id == self.substituto_id:
            raise ValidationError({"substituto": "Substituto não pode ser o mesmo usuário do responsável."})

        # ✅ departamento ATIVO precisa ter alguém “responsável”
        # (aceita: responsavel OU ao menos 1 membro ativo)
        if self.ativo:
            tem_membro_ativo = False
            if self.pk:
                tem_membro_ativo = self.membros.filter(ativo=True).exists()

            if not self.responsavel and not tem_membro_ativo:
                raise ValidationError(
                    {"responsavel": "Departamento ativo deve ter um responsável OU ao menos 1 membro ativo."}
                )

        # ✅ PROTOCOLO GERAL deve ser INTERNO e ativo + único
        if self.eh_protocolo_geral:
            if self.tipo != self.Tipo.INTERNO:
                raise ValidationError({"eh_protocolo_geral": "PROTOCOLO GERAL deve ser do tipo INTERNO."})
            if not self.ativo:
                raise ValidationError({"eh_protocolo_geral": "PROTOCOLO GERAL deve estar ativo."})

            qs = Departamento.objects.filter(eh_protocolo_geral=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({"eh_protocolo_geral": "Já existe um PROTOCOLO GERAL cadastrado."})

        # ✅ ARQUIVO GERAL recomendado INTERNO + único
        if self.eh_arquivo_geral:
            if self.tipo != self.Tipo.INTERNO:
                raise ValidationError({"eh_arquivo_geral": "ARQUIVO GERAL deve ser do tipo INTERNO."})

            qs = Departamento.objects.filter(eh_arquivo_geral=True)
            if self.pk:
                qs = qs.exclude(pk=self.pk)
            if qs.exists():
                raise ValidationError({"eh_arquivo_geral": "Já existe um ARQUIVO GERAL cadastrado."})

    def __str__(self) -> str:
        return f"{self.nome} ({self.tipo})"


class DepartamentoMembro(models.Model):
    """
    ✅ Opção B: múltiplos membros por setor.
    Isso resolve “quem faz parte do setor” (inclusive ARQUIVO GERAL).
    """
    departamento = models.ForeignKey(
        Departamento,
        on_delete=models.CASCADE,
        related_name="membros",
    )
    user = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.CASCADE,
        related_name="setores",
    )
    ativo = models.BooleanField(default=True)
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Membro do Departamento"
        verbose_name_plural = "Membros do Departamento"
        constraints = [
            models.UniqueConstraint(fields=["departamento", "user"], name="uniq_departamento_membro"),
        ]

    def __str__(self) -> str:
        return f"{self.departamento.nome} <- {self.user.username}"
