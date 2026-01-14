# apps/protocolos/forms.py
from __future__ import annotations

import re
from django import forms
from django.apps import apps
from django.core.validators import EmailValidator
from django.core.exceptions import ValidationError

from core.validators import only_digits, validate_cpf
from .models import Departamento, DepartamentoMembro, MovimentacaoProcesso, Pessoa, Processo, TipoProcesso

PROTOCOLO_GERAL_NOME = "PROTOCOLO GERAL"

REGEX_NUMERO_PROCESSO = re.compile(r"^\d{4}/\d{2}$")


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _normalize_numero_processo(raw: str) -> str:
    """
    Aceita:
    - "0123/26"
    - "012326"
    - "0123-26"
    - " 0123 / 26 "
    - "014525"  -> "0145/25"
    Retorna sempre "0000/00" ou levanta ValidationError.
    """
    s = (raw or "").strip()
    if not s:
        raise ValidationError("Informe o número do processo.")

    digits = re.sub(r"\D+", "", s)

    # se o usuário digitou 6 dígitos (014525) => 0145/25
    if len(digits) == 6:
        s = f"{digits[:4]}/{digits[4:6]}"
    else:
        # tenta manter formato se veio com barra
        s = s.replace(" ", "")
        if "/" not in s and len(digits) == 6:
            s = f"{digits[:4]}/{digits[4:6]}"

    if not REGEX_NUMERO_PROCESSO.match(s):
        raise ValidationError("Número inválido. Use exatamente o formato 0000/00 (ex.: 0123/26).")

    return s


# -----------------------------------------------------------------------------
# PESSOAS
# -----------------------------------------------------------------------------
class PessoaForm(forms.ModelForm):
    class Meta:
        model = Pessoa
        fields = ["nome", "cpf", "email", "telefone", "whatsapp", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"placeholder": "Nome completo"}),
            "cpf": forms.TextInput(attrs={"placeholder": "Somente números (11 dígitos)"}),
            "email": forms.EmailInput(attrs={"placeholder": "email@exemplo.com"}),
            "telefone": forms.TextInput(attrs={"placeholder": "DDD + número (somente números)"}),
            "whatsapp": forms.TextInput(attrs={"placeholder": "DDD + número (somente números)"}),
        }

    def clean_nome(self):
        nome = (self.cleaned_data.get("nome") or "").strip()
        return nome.upper()

    def clean_cpf(self):
        cpf = self.cleaned_data.get("cpf") or ""
        cpf = only_digits(cpf)
        cpf = validate_cpf(cpf)

        qs = Pessoa.objects.filter(cpf=cpf)
        if self.instance and self.instance.pk:
            qs = qs.exclude(pk=self.instance.pk)
        if qs.exists():
            raise forms.ValidationError("Já existe uma pessoa cadastrada com este CPF.")
        return cpf

    def clean_email(self):
        email = self.cleaned_data.get("email")
        if email:
            EmailValidator()(email)
            email = email.strip().lower()
        return email

    def clean_telefone(self):
        telefone = only_digits(self.cleaned_data.get("telefone") or "")
        if len(telefone) < 10:
            raise forms.ValidationError("Telefone inválido. Informe DDD + número.")
        return telefone

    def clean_whatsapp(self):
        whatsapp = self.cleaned_data.get("whatsapp")
        if not whatsapp:
            return whatsapp
        whatsapp = only_digits(whatsapp)
        if len(whatsapp) < 10:
            raise forms.ValidationError("WhatsApp inválido. Informe DDD + número.")
        return whatsapp


# -----------------------------------------------------------------------------
# MOVIMENTAÇÃO
# -----------------------------------------------------------------------------
class MovimentacaoForm(forms.ModelForm):
    class Meta:
        model = MovimentacaoProcesso
        fields = ["tipo_tramitacao", "acao", "departamento_origem", "departamento_destino", "observacao"]
        widgets = {"observacao": forms.Textarea(attrs={"rows": 3})}

    def __init__(self, *args, **kwargs):
        self.processo = kwargs.pop("processo", None)
        self.user = kwargs.pop("user", None)
        super().__init__(*args, **kwargs)

        self.fields["departamento_origem"].widget = forms.HiddenInput()
        self.fields["departamento_origem"].required = False
        self.fields["departamento_destino"].required = False

        origem = self._inferir_origem()

        tipo = (
            self.data.get("tipo_tramitacao")
            or getattr(self.instance, "tipo_tramitacao", None)
            or self.initial.get("tipo_tramitacao")
        )
        acao = (
            self.data.get("acao")
            or getattr(self.instance, "acao", None)
            or self.initial.get("acao")
        )

        if self.processo and getattr(self.processo, "status", None) == Processo.Status.ARQUIVADO:
            for f in self.fields.values():
                f.disabled = True
            self.fields["observacao"].help_text = "Processo arquivado: não é possível tramitar."
            return

        if tipo == MovimentacaoProcesso.TipoTramitacao.INTERNA:
            destinos_qs = Departamento.objects.filter(tipo=Departamento.Tipo.INTERNO, ativo=True)
        elif tipo == MovimentacaoProcesso.TipoTramitacao.EXTERNA:
            destinos_qs = Departamento.objects.filter(tipo=Departamento.Tipo.EXTERNO, ativo=True)
        else:
            destinos_qs = Departamento.objects.filter(ativo=True)

        if origem and not getattr(origem, "eh_protocolo_geral", False):
            destinos_qs = destinos_qs.exclude(eh_protocolo_geral=True)

        self.fields["departamento_destino"].queryset = destinos_qs.order_by("tipo", "nome")

        if self.user and self.user.is_authenticated:
            eh_admin = getattr(getattr(self.user, "perfil", None), "papel", None) == "ADMIN"
            eh_arquivo = self._user_is_membro_arquivo_geral(self.user.id)
            if not (eh_admin or eh_arquivo):
                self.fields["acao"].choices = [
                    c for c in self.fields["acao"].choices
                    if c[0] != MovimentacaoProcesso.Acao.ARQUIVADO
                ]

        papel = getattr(getattr(self.user, "perfil", None), "papel", None) if self.user else None
        if papel == "PROTOCOLISTA":
            if origem and not getattr(origem, "eh_protocolo_geral", False):
                for f in self.fields.values():
                    f.disabled = True
                self.fields["observacao"].help_text = (
                    "Protocolista só pode tramitar enquanto o processo estiver no PROTOCOLO GERAL."
                )
                return

        if acao == MovimentacaoProcesso.Acao.ARQUIVADO:
            self.fields["departamento_destino"].disabled = True
            self.fields["departamento_destino"].help_text = "Ao arquivar, o destino não é necessário."
        else:
            self.fields["departamento_destino"].disabled = False
            self.fields["departamento_destino"].help_text = ""

    def _inferir_origem(self):
        if self.processo:
            last = self.processo.movimentacoes.first()
            if last:
                return last.departamento_destino or last.departamento_origem

        pg = Departamento.objects.filter(
            tipo=Departamento.Tipo.INTERNO,
            ativo=True,
            eh_protocolo_geral=True,
        ).first()
        if pg:
            return pg

        return Departamento.objects.filter(
            tipo=Departamento.Tipo.INTERNO,
            ativo=True,
            nome__iexact=PROTOCOLO_GERAL_NOME,
        ).first()

    def _user_is_membro_arquivo_geral(self, user_id: int) -> bool:
        DepartamentoMembroModel = apps.get_model("protocolos", "DepartamentoMembro")
        return DepartamentoMembroModel.objects.filter(
            user_id=user_id,
            ativo=True,
            departamento__eh_arquivo_geral=True,
            departamento__ativo=True,
        ).exists()

    def clean(self):
        cleaned = super().clean()

        if self.processo and getattr(self.processo, "status", None) == Processo.Status.ARQUIVADO:
            raise forms.ValidationError("Este processo já está ARQUIVADO e não pode ser tramitado.")

        tipo = cleaned.get("tipo_tramitacao")
        acao = cleaned.get("acao")
        destino = cleaned.get("departamento_destino")

        origem = self._inferir_origem()
        if not origem:
            raise forms.ValidationError(
                f'Não foi possível definir a origem. Marque "{PROTOCOLO_GERAL_NOME}" como '
                f'eh_protocolo_geral=True (INTERNO/ativo) ou garanta que o processo já tenha movimentações.'
            )

        cleaned["departamento_origem"] = origem

        papel = getattr(getattr(self.user, "perfil", None), "papel", None) if self.user else None
        eh_admin = papel == "ADMIN"

        if papel == "PROTOCOLISTA" and not getattr(origem, "eh_protocolo_geral", False):
            raise forms.ValidationError("Protocolista só pode tramitar enquanto o processo estiver no PROTOCOLO GERAL.")

        if origem.tipo != Departamento.Tipo.INTERNO:
            self.add_error("departamento_origem", "A origem deve ser um departamento INTERNO.")

        if acao == MovimentacaoProcesso.Acao.ARQUIVADO:
            eh_arquivo = self.user and self.user.is_authenticated and self._user_is_membro_arquivo_geral(self.user.id)
            if not (eh_admin or eh_arquivo):
                raise forms.ValidationError("Somente ADMIN ou membros do ARQUIVO GERAL podem arquivar processos.")
            cleaned["departamento_destino"] = None
            return cleaned

        if acao == MovimentacaoProcesso.Acao.ENCAMINHADO and not destino:
            self.add_error("departamento_destino", "Destino é obrigatório para ENCAMINHAR.")

        if destino and origem and destino.pk == origem.pk:
            self.add_error("departamento_destino", "O destino não pode ser o mesmo da origem.")

        if destino:
            if tipo == MovimentacaoProcesso.TipoTramitacao.INTERNA and destino.tipo != Departamento.Tipo.INTERNO:
                self.add_error("departamento_destino", "Destino deve ser INTERNO para tramitação INTERNA.")
            if tipo == MovimentacaoProcesso.TipoTramitacao.EXTERNA and destino.tipo != Departamento.Tipo.EXTERNO:
                self.add_error("departamento_destino", "Destino deve ser EXTERNO para tramitação EXTERNA.")
            if getattr(destino, "eh_protocolo_geral", False) and not getattr(origem, "eh_protocolo_geral", False):
                self.add_error("departamento_destino", "Não é permitido encaminhar para o PROTOCOLO GERAL.")

        return cleaned

    def save(self, commit=True):
        obj = super().save(commit=False)
        obj.departamento_origem = self.cleaned_data["departamento_origem"]
        obj.departamento_destino = self.cleaned_data.get("departamento_destino")

        if self.processo and hasattr(obj, "processo_id") and not getattr(obj, "processo_id", None):
            obj.processo = self.processo

        if commit:
            obj.save()
        return obj


# -----------------------------------------------------------------------------
# CRIAÇÃO DE PROCESSO (PROTOCOLO GERAL) - MANUAL 0000/00
# -----------------------------------------------------------------------------
class ProcessoCreateForm(forms.Form):
    numero_processo = forms.CharField(
        label="Número do processo",
        max_length=7,
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "0000/00",
                "autocomplete": "off",
                "inputmode": "numeric",
            }
        ),
        help_text="Formato obrigatório: 0000/00 (ex.: 0123/26).",
    )

    cpf = forms.CharField(
        label="CPF do requerente",
        max_length=14,
        help_text="Digite somente números (11 dígitos).",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Somente números (11 dígitos)",
                "inputmode": "numeric",
            }
        ),
    )

    tipo_processo = forms.ModelChoiceField(
        label="Tipo de processo",
        queryset=TipoProcesso.objects.filter(ativo=True).order_by("nome"),
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    assunto = forms.CharField(
        label="Assunto",
        max_length=255,
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    descricao = forms.CharField(
        label="Descrição (opcional)",
        required=False,
        widget=forms.Textarea(attrs={"class": "form-control", "rows": 4}),
    )

    prioridade = forms.ChoiceField(
        label="Prioridade",
        choices=Processo.Prioridade.choices,
        initial=Processo.Prioridade.NORMAL,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.pessoa_encontrada = None
        self.numero_int = None
        self.ano_int = None

    def clean_numero_processo(self):
        raw = self.cleaned_data.get("numero_processo") or ""
        normal = _normalize_numero_processo(raw)  # "0000/00"

        numero4, ano2 = normal.split("/")
        self.numero_int = int(numero4)  # 0..9999
        self.ano_int = int(ano2)        # 0..99

        # ✅ duplicidade REAL (ano + numero_manual)
        if Processo.objects.filter(ano=self.ano_int, numero_manual=self.numero_int).exists():
            raise ValidationError(f"Já existe um processo com o número {normal}.")

        # reforço pelo numero_formatado (unique=True no model)
        if Processo.objects.filter(numero_formatado=normal).exists():
            raise ValidationError(f"Já existe um processo com o número {normal}.")

        return normal

    def clean_cpf(self):
        cpf = self.cleaned_data.get("cpf", "")
        cpf = only_digits(cpf)
        cpf = validate_cpf(cpf)
        self.pessoa_encontrada = Pessoa.objects.filter(cpf=cpf, ativo=True).first()
        return cpf

    def clean_assunto(self):
        return (self.cleaned_data.get("assunto") or "").strip().upper()

    def clean_descricao(self):
        return (self.cleaned_data.get("descricao") or "").strip().upper()


# =============================================================================
# CADASTROS (ADMIN) - NOVOS FORMS
# =============================================================================
class TipoProcessoForm(forms.ModelForm):
    class Meta:
        model = TipoProcesso
        fields = ["nome", "descricao", "ativo"]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "descricao": forms.Textarea(attrs={"class": "form-control", "rows": 4}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }

    def clean_nome(self):
        return (self.cleaned_data.get("nome") or "").strip().upper()


class DepartamentoForm(forms.ModelForm):
    class Meta:
        model = Departamento
        fields = [
            "nome", "sigla", "tipo", "ativo",
            "eh_protocolo_geral", "eh_arquivo_geral",
            "responsavel", "substituto",
        ]
        widgets = {
            "nome": forms.TextInput(attrs={"class": "form-control"}),
            "sigla": forms.TextInput(attrs={"class": "form-control"}),
            "tipo": forms.Select(attrs={"class": "form-select"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "eh_protocolo_geral": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "eh_arquivo_geral": forms.CheckboxInput(attrs={"class": "form-check-input"}),
            "responsavel": forms.Select(attrs={"class": "form-select"}),
            "substituto": forms.Select(attrs={"class": "form-select"}),
        }

    def clean_nome(self):
        return (self.cleaned_data.get("nome") or "").strip().upper()

    def clean_sigla(self):
        sigla = (self.cleaned_data.get("sigla") or "").strip()
        return sigla.upper() if sigla else sigla


class DepartamentoMembroForm(forms.ModelForm):
    class Meta:
        model = DepartamentoMembro
        fields = ["user", "ativo"]
        widgets = {
            "user": forms.Select(attrs={"class": "form-select"}),
            "ativo": forms.CheckboxInput(attrs={"class": "form-check-input"}),
        }
