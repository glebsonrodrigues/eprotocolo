from django.core.management.base import BaseCommand
from django.contrib.auth.models import Group, Permission
from django.contrib.contenttypes.models import ContentType

from protocolos.models import Pessoa, Departamento, TipoProcesso


class Command(BaseCommand):
    help = "Cria grupos (roles) e atribui permissões padrão do Eprotocolo."

    def handle(self, *args, **options):
        # content types
        ct_pessoa = ContentType.objects.get_for_model(Pessoa)
        ct_depto = ContentType.objects.get_for_model(Departamento)
        ct_tipo = ContentType.objects.get_for_model(TipoProcesso)

        def perms(ct):
            return Permission.objects.filter(content_type=ct)

        # grupos
        admin_group, _ = Group.objects.get_or_create(name="ADMIN")
        protocolista_group, _ = Group.objects.get_or_create(name="PROTOCOLISTA")
        tramitador_group, _ = Group.objects.get_or_create(name="TRAMITADOR")
        consulta_group, _ = Group.objects.get_or_create(name="CONSULTA")

        # ADMIN: tudo
        admin_group.permissions.set(list(perms(ct_pessoa)) + list(perms(ct_depto)) + list(perms(ct_tipo)))

        # PROTOCOLISTA: pode cadastrar/editar tudo (cadastros)
        protocolista_group.permissions.set(list(perms(ct_pessoa)) + list(perms(ct_depto)) + list(perms(ct_tipo)))

        # TRAMITADOR: por enquanto só leitura nos cadastros (vai ganhar perms de tramitação quando criarmos o módulo)
        tramitador_group.permissions.set([
            *Permission.objects.filter(content_type=ct_pessoa, codename__startswith="view_"),
            *Permission.objects.filter(content_type=ct_depto, codename__startswith="view_"),
            *Permission.objects.filter(content_type=ct_tipo, codename__startswith="view_"),
        ])

        # CONSULTA: apenas view
        consulta_group.permissions.set([
            *Permission.objects.filter(content_type=ct_pessoa, codename__startswith="view_"),
            *Permission.objects.filter(content_type=ct_depto, codename__startswith="view_"),
            *Permission.objects.filter(content_type=ct_tipo, codename__startswith="view_"),
        ])

        self.stdout.write(self.style.SUCCESS("Grupos e permissões criados/atualizados com sucesso."))
