from django.contrib.auth import get_user_model
from django.db.models.signals import post_save
from django.dispatch import receiver

from .models import Perfil

User = get_user_model()


@receiver(post_save, sender=User)
def criar_ou_atualizar_perfil(sender, instance, created, **kwargs):
    perfil, _ = Perfil.objects.get_or_create(user=instance)

    if instance.is_superuser:
        perfil.papel = "ADMIN"
    else:
        perfil.papel = perfil.papel or "CONSULTA"

    perfil.save()
