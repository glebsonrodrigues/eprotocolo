from django.contrib import admin
from .models import Pessoa, TipoProcesso, Departamento, Processo, MovimentacaoProcesso, Comprovante

admin.site.register(Pessoa)
admin.site.register(TipoProcesso)
admin.site.register(Departamento)
admin.site.register(Processo)
admin.site.register(MovimentacaoProcesso)
admin.site.register(Comprovante)

