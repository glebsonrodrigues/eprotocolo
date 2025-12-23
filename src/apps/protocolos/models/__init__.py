# Exporta os models para permitir: from protocolos.models import Pessoa, Processo, etc.

from .cadastros import Pessoa, TipoProcesso, Departamento
from .processos import SequenciaProcesso, Processo, ProcessoInteressado
from .tramitacao import MovimentacaoProcesso
from .comprovantes import Comprovante

__all__ = [
    "Pessoa",
    "TipoProcesso",
    "Departamento",
    "SequenciaProcesso",
    "Processo",
    "ProcessoInteressado",
    "MovimentacaoProcesso",
    "Comprovante",
]
