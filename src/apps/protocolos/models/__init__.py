# Exporta os models para permitir: from protocolos.models import Pessoa, Processo, etc.

from .cadastros import Pessoa, TipoProcesso, Departamento, DepartamentoMembro
from .processos import Processo, ProcessoInteressado
from .tramitacao import MovimentacaoProcesso
from .comprovantes import Comprovante

__all__ = [
    "Pessoa",
    "TipoProcesso",
    "Departamento",
    "DepartamentoMembro",
    "Processo",
    "ProcessoInteressado",
    "MovimentacaoProcesso",
    "Comprovante",
]
