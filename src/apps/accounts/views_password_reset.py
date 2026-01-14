from django.contrib.auth import views as auth_views
from django.urls import reverse_lazy


class PasswordResetView(auth_views.PasswordResetView):
    template_name = "accounts/password_reset_form.html"
    email_template_name = "accounts/password_reset_email.txt"
    subject_template_name = "accounts/password_reset_subject.txt"
    success_url = reverse_lazy("password_reset_done")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["email"].widget.attrs.update({"class": "form-control", "placeholder": "email@exemplo.com"})
        return form


class PasswordResetDoneView(auth_views.PasswordResetDoneView):
    template_name = "accounts/password_reset_done.html"


class PasswordResetConfirmView(auth_views.PasswordResetConfirmView):
    template_name = "accounts/password_reset_confirm.html"
    success_url = reverse_lazy("password_reset_complete")

    def get_form(self, form_class=None):
        form = super().get_form(form_class)
        form.fields["new_password1"].widget.attrs.update({"class": "form-control"})
        form.fields["new_password2"].widget.attrs.update({"class": "form-control"})
        return form


class PasswordResetCompleteView(auth_views.PasswordResetCompleteView):
    template_name = "accounts/password_reset_complete.html"
