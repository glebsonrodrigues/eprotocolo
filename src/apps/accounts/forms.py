from django import forms
from django.contrib.auth import get_user_model
from django.core.validators import EmailValidator

from .models import Perfil

User = get_user_model()


# -----------------------------------------------------------------------------
# Helpers
# -----------------------------------------------------------------------------
def _add_bootstrap_class(field: forms.Field, css: str) -> None:
    """Adiciona classes bootstrap sem apagar classes existentes."""
    existing = field.widget.attrs.get("class", "")
    field.widget.attrs["class"] = (existing + " " + css).strip()


# -----------------------------------------------------------------------------
# CREATE
# -----------------------------------------------------------------------------
class UsuarioCreateForm(forms.ModelForm):
    password1 = forms.CharField(
        label="Senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control no-uppercase",
                "placeholder": "Digite a senha",
                "autocomplete": "new-password",
            }
        ),
    )
    password2 = forms.CharField(
        label="Confirmar senha",
        widget=forms.PasswordInput(
            attrs={
                "class": "form-control no-uppercase",
                "placeholder": "Repita a senha",
                "autocomplete": "new-password",
            }
        ),
    )
    papel = forms.ChoiceField(
        label="Papel",
        choices=Perfil.Papel.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]
        widgets = {
            "username": forms.TextInput(
                attrs={
                    "class": "form-control no-uppercase",
                    "placeholder": "Usuário (login)",
                    "autocomplete": "off",
                }
            ),
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Nome"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Sobrenome"}
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control no-uppercase",
                    "placeholder": "email@exemplo.com",
                    "autocomplete": "off",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Garante Bootstrap em todos os campos
        for name, field in self.fields.items():
            if isinstance(field.widget, forms.CheckboxInput):
                _add_bootstrap_class(field, "form-check-input")
            elif isinstance(field.widget, forms.Select):
                _add_bootstrap_class(field, "form-select")
            else:
                _add_bootstrap_class(field, "form-control")

        # Email opcional
        self.fields["email"].required = False

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if email:
            EmailValidator()(email)
            return email.lower()
        return ""

    def clean(self):
        cleaned = super().clean()
        if cleaned.get("password1") != cleaned.get("password2"):
            self.add_error("password2", "As senhas não conferem.")
        return cleaned

    def save(self, commit=True):
        user = super().save(commit=False)
        user.set_password(self.cleaned_data["password1"])

        if commit:
            user.save()
            perfil = user.perfil
            perfil.papel = self.cleaned_data["papel"]
            perfil.save()

        return user


# -----------------------------------------------------------------------------
# UPDATE
# -----------------------------------------------------------------------------
class UsuarioUpdateForm(forms.ModelForm):
    papel = forms.ChoiceField(
        label="Papel",
        choices=Perfil.Papel.choices,
        widget=forms.Select(attrs={"class": "form-select"}),
    )

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_active"]
        widgets = {
            "first_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Nome"}
            ),
            "last_name": forms.TextInput(
                attrs={"class": "form-control", "placeholder": "Sobrenome"}
            ),
            "email": forms.EmailInput(
                attrs={
                    "class": "form-control no-uppercase",
                    "placeholder": "email@exemplo.com",
                }
            ),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Checkbox bootstrap
        if "is_active" in self.fields:
            _add_bootstrap_class(self.fields["is_active"], "form-check-input")

        # Email opcional
        self.fields["email"].required = False

        # Papel inicial
        if self.instance:
            self.fields["papel"].initial = getattr(self.instance.perfil, "papel", None)

    def clean_email(self):
        email = (self.cleaned_data.get("email") or "").strip()
        if email:
            EmailValidator()(email)
            return email.lower()
        return ""

    def save(self, commit=True):
        user = super().save(commit=commit)
        perfil = user.perfil
        perfil.papel = self.cleaned_data["papel"]
        perfil.save()
        return user
