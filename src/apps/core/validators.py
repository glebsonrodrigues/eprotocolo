import re
from django.core.exceptions import ValidationError


_RE_DIGITS = re.compile(r"\D+")


def only_digits(value) -> str:
    """Remove tudo que não for número."""
    if value is None:
        return ""
    return _RE_DIGITS.sub("", str(value))


def validate_cpf(value) -> str:
    """
    Valida CPF (com ou sem máscara).
    Retorna CPF normalizado (11 dígitos) ou levanta ValidationError.
    """
    cpf = only_digits(value)

    if len(cpf) != 11:
        raise ValidationError("CPF deve conter 11 dígitos.")

    # Rejeita CPFs com todos os dígitos iguais
    if cpf == cpf[0] * 11:
        raise ValidationError("CPF inválido.")

    # 1º DV
    soma = 0
    for i in range(9):
        soma += int(cpf[i]) * (10 - i)
    dv1 = (soma * 10) % 11
    dv1 = 0 if dv1 == 10 else dv1

    # 2º DV
    soma = 0
    for i in range(10):
        soma += int(cpf[i]) * (11 - i)
    dv2 = (soma * 10) % 11
    dv2 = 0 if dv2 == 10 else dv2

    if dv1 != int(cpf[9]) or dv2 != int(cpf[10]):
        raise ValidationError("CPF inválido.")

    return cpf


def format_cpf(cpf_value) -> str:
    """Formata CPF (11 dígitos) para 000.000.000-00."""
    cpf = only_digits(cpf_value)
    if len(cpf) != 11:
        return str(cpf_value) if cpf_value is not None else ""
    return f"{cpf[0:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:11]}"


def normalize_br_phone(value, *, required: bool = False, field_name: str = "telefone") -> str:
    """
    Normaliza telefone BR para somente dígitos (DDD + número).
    Aceita entrada com máscara.
    - Celular: 11 dígitos (DD + 9 + 8 dígitos)
    - Fixo: 10 dígitos (DD + 8 dígitos)
    """
    digits = only_digits(value)

    if required and len(digits) == 0:
        raise ValidationError({field_name: "Informe o telefone."})

    if len(digits) == 0:
        return ""

    if len(digits) not in (10, 11):
        raise ValidationError({field_name: "Telefone inválido. Informe DDD + número."})

    return digits


def format_br_phone(phone_value) -> str:
    """
    Formata telefone BR:
    10 dígitos -> (DD) NNNN-NNNN
    11 dígitos -> (DD) 9 NNNN-NNNN
    """
    n = only_digits(phone_value)
    if len(n) == 10:
        ddd = n[:2]
        rest = n[2:]
        return f"({ddd}) {rest[:4]}-{rest[4:]}"
    if len(n) == 11:
        ddd = n[:2]
        rest = n[2:]
        return f"({ddd}) {rest[0]} {rest[1:5]}-{rest[5:]}"
    return str(phone_value) if phone_value is not None else ""
