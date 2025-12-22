import re
from django.core.exceptions import ValidationError


def only_digits(value: str) -> str:
    if value is None:
        return ""
    return re.sub(r"\D", "", str(value))


def validate_cpf(value: str) -> str:
    """
    Valida CPF.
    Aceita com máscara ou só números.
    Retorna o CPF normalizado (11 dígitos) ou levanta ValidationError.
    """
    cpf = only_digits(value)

    if len(cpf) != 11:
        raise ValidationError("CPF deve conter 11 dígitos.")

    # Rejeita CPFs com todos os dígitos iguais (ex.: 11111111111)
    if cpf == cpf[0] * 11:
        raise ValidationError("CPF inválido.")

    # Cálculo do 1º dígito verificador
    soma = sum(int(cpf[i]) * (10 - i) for i in range(9))
    dv1 = (soma * 10) % 11
    dv1 = 0 if dv1 == 10 else dv1

    # Cálculo do 2º dígito verificador
    soma = sum(int(cpf[i]) * (11 - i) for i in range(10))
    dv2 = (soma * 10) % 11
    dv2 = 0 if dv2 == 10 else dv2

    if dv1 != int(cpf[9]) or dv2 != int(cpf[10]):
        raise ValidationError("CPF inválido.")

    return cpf


def format_cpf(cpf_digits: str) -> str:
    cpf = only_digits(cpf_digits)
    if len(cpf) != 11:
        return cpf_digits
    return f"{cpf[0:3]}.{cpf[3:6]}.{cpf[6:9]}-{cpf[9:11]}"


def format_br_phone(phone_digits: str) -> str:
    """
    Formata número BR (DDD + 8/9 dígitos).
    Ex.: 81988886666 -> (81) 9 8888-6666
    """
    n = only_digits(phone_digits)
    if len(n) < 10:
        return phone_digits

    ddd = n[0:2]
    rest = n[2:]

    # Celular 9 dígitos
    if len(rest) == 9:
        return f"({ddd}) {rest[0]} {rest[1:5]}-{rest[5:9]}"

    # Fixo 8 dígitos
    if len(rest) == 8:
        return f"({ddd}) {rest[0:4]}-{rest[4:8]}"

    return phone_digits
