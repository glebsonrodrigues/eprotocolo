from django.contrib import admin
from .models import (
    Pessoa,
    TipoProcesso,
    Departamento,
    DepartamentoMembro,
    Processo,
    MovimentacaoProcesso,
    Comprovante,
)


@admin.register(Pessoa)
class PessoaAdmin(admin.ModelAdmin):
    search_fields = ("nome", "cpf")
    list_display = ("nome", "cpf", "ativo")
    list_filter = ("ativo",)


@admin.register(TipoProcesso)
class TipoProcessoAdmin(admin.ModelAdmin):
    search_fields = ("nome",)
    list_display = ("nome", "ativo")
    list_filter = ("ativo",)


class DepartamentoMembroInline(admin.TabularInline):
    model = DepartamentoMembro
    extra = 1
    autocomplete_fields = ("user",)
    fields = ("user", "ativo", "criado_em")
    readonly_fields = ("criado_em",)


@admin.register(Departamento)
class DepartamentoAdmin(admin.ModelAdmin):
    list_display = (
        "nome",
        "sigla",
        "tipo",
        "ativo",
        "eh_protocolo_geral",
        "eh_arquivo_geral",
        "responsavel",
        "substituto",
    )
    list_filter = ("tipo", "ativo", "eh_protocolo_geral", "eh_arquivo_geral")
    search_fields = (
        "nome",
        "sigla",
        "responsavel__username",
        "responsavel__first_name",
        "responsavel__last_name",
        "substituto__username",
    )
    autocomplete_fields = ("responsavel", "substituto")
    ordering = ("tipo", "nome")
    inlines = (DepartamentoMembroInline,)

    def save_model(self, request, obj, form, change):
        obj.full_clean()
        super().save_model(request, obj, form, change)


@admin.register(DepartamentoMembro)
class DepartamentoMembroAdmin(admin.ModelAdmin):
    list_display = ("departamento", "user", "ativo", "criado_em")
    list_filter = ("ativo", "departamento")
    search_fields = ("departamento__nome", "user__username", "user__first_name", "user__last_name")
    autocomplete_fields = ("departamento", "user")
    ordering = ("-criado_em",)


@admin.register(Processo)
class ProcessoAdmin(admin.ModelAdmin):
    list_display = (
        "numero_formatado",
        "tipo_processo",
        "assunto",
        "status",
        "prioridade",
        "criado_em",
        "criado_por",
    )
    list_filter = ("status", "prioridade", "tipo_processo")
    search_fields = ("numero_formatado", "assunto", "descricao", "criado_por__username")
    ordering = ("-criado_em",)


@admin.register(MovimentacaoProcesso)
class MovimentacaoProcessoAdmin(admin.ModelAdmin):
    list_display = ("processo", "acao", "tipo_tramitacao", "departamento_origem", "departamento_destino", "registrado_por", "registrado_em")
    list_filter = ("acao", "tipo_tramitacao", "departamento_origem", "departamento_destino")
    search_fields = ("processo__numero_formatado", "observacao", "registrado_por__username")
    ordering = ("-registrado_em",)


@admin.register(Comprovante)
class ComprovanteAdmin(admin.ModelAdmin):
    list_display = ("tipo", "emitido_em", "emitido_por", "processo", "codigo_autenticacao")
    list_filter = ("tipo", "emitido_em")
    search_fields = ("codigo_autenticacao", "processo__id", "processo__numero_formatado")
    ordering = ("-emitido_em",)
    readonly_fields = ("codigo_autenticacao", "emitido_em", "emitido_por")
