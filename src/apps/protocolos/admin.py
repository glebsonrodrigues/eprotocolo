from django.contrib import admin
from .models import Pessoa, TipoProcesso, Departamento


@admin.register(Pessoa)
class PessoaAdmin(admin.ModelAdmin):
    list_display = ("nome", "cpf_formatado", "telefone_formatado", "email", "ativo")
    search_fields = ("nome", "cpf", "telefone", "email")
    list_filter = ("ativo",)


@admin.register(TipoProcesso)
class TipoProcessoAdmin(admin.ModelAdmin):
    list_display = ("nome", "ativo", "criado_em")
    search_fields = ("nome", "descricao")
    list_filter = ("ativo",)


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = ("nome", "sigla", "tipo", "ativo", "criado_em")
    search_fields = ("nome", "sigla")
    list_filter = ("tipo", "ativo")
