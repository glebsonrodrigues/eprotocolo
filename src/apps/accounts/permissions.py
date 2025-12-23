from django.contrib.auth.decorators import user_passes_test


def has_role(*roles):
    roles = set(roles)

    def check(user):
        if not user.is_authenticated:
            return False
        perfil = getattr(user, "perfil", None)
        if not perfil:
            return False
        return perfil.papel in roles

    return user_passes_test(check)


# exemplos prontos
only_admin = has_role("ADMIN")
admin_or_protocolista = has_role("ADMIN", "PROTOCOLISTA")
admin_or_tramitador = has_role("ADMIN", "TRAMITADOR")
