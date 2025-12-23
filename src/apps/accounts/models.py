from django.conf import settings
from django.db import models


class Perfil(models.Model):
    class Papel(models.TextChoices):
        ADMIN = "ADMIN", "Administrador"
        PROTOCOLISTA = "PROTOCOLISTA", "Protocolista"
        TRAMITADOR = "TRAMITADOR", "Tramitador"
        CONSULTA = "CONSULTA", "Consulta (somente leitura)"

    user = models.OneToOneField(settings.AUTH_USER_MODEL, on_delete=models.CASCADE, related_name="perfil")
    papel = models.CharField(max_length=20, choices=Papel.choices, default=Papel.CONSULTA)

    # Opcional: vincular usuário a um depto (se quiser restringir trâmite por setor depois)
    # Só habilite se você quiser usar isso já:
    # departamento = models.ForeignKey("protocolos.Departamento", on_delete=models.SET_NULL, null=True, blank=True)

    criado_em = models.DateTimeField(auto_now_add=True)
    atualizado_em = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Perfil"
        verbose_name_plural = "Perfis"

    def __str__(self) -> str:
        return f"{self.user.username} ({self.papel})"
