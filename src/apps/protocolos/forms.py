from django import forms

from .models import Departamento, MovimentacaoProcesso


class MovimentacaoForm(forms.ModelForm):
    class Meta:
        model = MovimentacaoProcesso
        fields = ["tipo_tramitacao", "acao", "departamento_origem", "departamento_destino", "observacao"]
        widgets = {
            "observacao": forms.Textarea(attrs={"rows": 3}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)

        # Origem sempre interno
        self.fields["departamento_origem"].queryset = Departamento.objects.filter(
            tipo=Departamento.Tipo.INTERNO, ativo=True
        ).order_by("nome")

        # Destino depende do tipo_tramitacao (se tiver valor)
        tipo = None
        if self.data.get("tipo_tramitacao"):
            tipo = self.data.get("tipo_tramitacao")
        elif self.instance and self.instance.tipo_tramitacao:
            tipo = self.instance.tipo_tramitacao

        if tipo == MovimentacaoProcesso.TipoTramitacao.INTERNA:
            self.fields["departamento_destino"].queryset = Departamento.objects.filter(
                tipo=Departamento.Tipo.INTERNO, ativo=True
            ).order_by("nome")
        elif tipo == MovimentacaoProcesso.TipoTramitacao.EXTERNA:
            self.fields["departamento_destino"].queryset = Departamento.objects.filter(
                tipo=Departamento.Tipo.EXTERNO, ativo=True
            ).order_by("nome")
        else:
            self.fields["departamento_destino"].queryset = Departamento.objects.filter(ativo=True).order_by("nome")
