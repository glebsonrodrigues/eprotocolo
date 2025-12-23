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
    criado_em = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ["tipo", "nome"]
        verbose_name = "Departamento"
        verbose_name_plural = "Departamentos"
        constraints = [
            models.UniqueConstraint(fields=["nome", "tipo"], name="uniq_departamento_nome_tipo"),
        ]

    def __str__(self) -> str:
        return f"{self.nome} ({self.tipo})"
