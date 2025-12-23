from django import forms
from django.contrib.auth import get_user_model

from .models import Perfil

User = get_user_model()


class UsuarioCreateForm(forms.ModelForm):
    password1 = forms.CharField(label="Senha", widget=forms.PasswordInput)
    password2 = forms.CharField(label="Confirmar senha", widget=forms.PasswordInput)
    papel = forms.ChoiceField(choices=Perfil.Papel.choices)

    class Meta:
        model = User
        fields = ["username", "first_name", "last_name", "email"]

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


class UsuarioUpdateForm(forms.ModelForm):
    papel = forms.ChoiceField(choices=Perfil.Papel.choices)

    class Meta:
        model = User
        fields = ["first_name", "last_name", "email", "is_active"]

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        if self.instance:
            self.fields["papel"].initial = self.instance.perfil.papel

    def save(self, commit=True):
        user = super().save(commit)
        perfil = user.perfil
        perfil.papel = self.cleaned_data["papel"]
        perfil.save()
        return user
