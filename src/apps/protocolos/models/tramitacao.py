from django.conf import settings
from django.core.exceptions import ValidationError
from django.db import models, transaction
from django.utils import timezone

from .cadastros import Departamento
from .processos import Processo


def origem_id_equals_destino(origem: Departamento, destino: Departamento) -> bool:
    return bool(origem and destino and origem.pk and destino.pk and origem.pk == destino.pk)


class MovimentacaoProcesso(models.Model):
    class TipoTramitacao(models.TextChoices):
        INTERNA = "INTERNA", "Interna"
        EXTERNA = "EXTERNA", "Externa"

    class Acao(models.TextChoices):
        ENCAMINHADO = "ENCAMINHADO", "Encaminhado"
        RECEBIDO = "RECEBIDO", "Recebido"
        DEVOLVIDO = "DEVOLVIDO", "Devolvido"
        ARQUIVADO = "ARQUIVADO", "Arquivado"

    processo = models.ForeignKey(Processo, on_delete=models.CASCADE, related_name="movimentacoes")
    tipo_tramitacao = models.CharField(max_length=10, choices=TipoTramitacao.choices)
    acao = models.CharField(max_length=12, choices=Acao.choices)

    departamento_origem = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="movimentacoes_origem",
    )
    departamento_destino = models.ForeignKey(
        Departamento,
        on_delete=models.PROTECT,
        related_name="movimentacoes_destino",
        blank=True,
        null=True,
    )

    observacao = models.TextField(blank=True, null=True)
    registrado_em = models.DateTimeField(default=timezone.now)
    registrado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL,
        on_delete=models.PROTECT,
        related_name="movimentacoes_registradas",
    )

    class Meta:
        ordering = ["-registrado_em"]
        verbose_name = "Movimentação do Processo"
        verbose_name_plural = "Movimentações do Processo"

    def __str__(self) -> str:
        return f"{self.processo.numero_formatado} - {self.acao} ({self.tipo_tramitacao})"

    def clean(self):
        """
        ATENÇÃO:
        - Regras que dependem do usuário logado (protocolista/arquivo geral/admin)
          DEVEM ficar no Form, porque no form.is_valid() o registrado_por ainda não está setado.
        - Aqui ficam apenas regras de consistência do dado (model-level).
        """
        errors = {}

        origem = self.departamento_origem
        destino = self.departamento_destino
        acao = self.acao
        tipo = self.tipo_tramitacao

        # ------------------------------------------------------------
        # REGRA: Processo ARQUIVADO não aceita novas tramitações
        # (bloqueia tudo, inclusive tentar arquivar novamente)
        # ------------------------------------------------------------
        if self.processo_id and getattr(self.processo, "status", None) == Processo.Status.ARQUIVADO:
            errors["acao"] = "Este processo já está ARQUIVADO e não pode mais ser tramitado."

        # ------------------------------------------------------------
        # Se ARQUIVADO: destino deve ser vazio e não valida regras de destino/tipo
        # (permissão de arquivar = Form)
        # ------------------------------------------------------------
        if acao == self.Acao.ARQUIVADO:
            self.departamento_destino = None
            if errors:
                raise ValidationError(errors)
            return

        # ------------------------------------------------------------
        # REGRA 1: Origem sempre INTERNO
        # ------------------------------------------------------------
        if origem and origem.tipo != Departamento.Tipo.INTERNO:
            errors["departamento_origem"] = "A origem deve ser um departamento INTERNO."

        # ------------------------------------------------------------
        # REGRA 2: ENCAMINHADO exige destino
        # ------------------------------------------------------------
        if acao == self.Acao.ENCAMINHADO and not destino:
            errors["departamento_destino"] = "Destino é obrigatório para ENCAMINHAR."

        # 2.1) ENCAMINHADO não pode mandar para o mesmo setor
        if acao == self.Acao.ENCAMINHADO and origem and destino and origem_id_equals_destino(origem, destino):
            errors["departamento_destino"] = "O destino não pode ser o mesmo da origem."

        # ------------------------------------------------------------
        # REGRA 3: valida destino conforme tipo_tramitacao (se houver destino)
        # ------------------------------------------------------------
        if destino:
            if tipo == self.TipoTramitacao.INTERNA and destino.tipo != Departamento.Tipo.INTERNO:
                errors["departamento_destino"] = "Destino deve ser INTERNO para tramitação INTERNA."
            elif tipo == self.TipoTramitacao.EXTERNA and destino.tipo != Departamento.Tipo.EXTERNO:
                errors["departamento_destino"] = "Destino deve ser EXTERNO para tramitação EXTERNA."

        # ------------------------------------------------------------
        # REGRA 4: Depois que sai do PROTOCOLO GERAL, não volta
        # - Se destino é PG, a origem precisa ser PG.
        # ------------------------------------------------------------
        if destino and getattr(destino, "eh_protocolo_geral", False):
            if not (origem and getattr(origem, "eh_protocolo_geral", False)):
                errors["departamento_destino"] = "Não é permitido encaminhar para o PROTOCOLO GERAL."

        if errors:
            raise ValidationError(errors)

    def save(self, *args, **kwargs):
        """
        Garante consistência:
        - valida (full_clean)
        - salva a movimentação
        - se ARQUIVADO, atualiza o processo na mesma transação
        """
        with transaction.atomic():
            self.full_clean()
            super().save(*args, **kwargs)

            # ------------------------------------------------------------
            # Ao arquivar: muda status do processo + registra dados do arquivamento
            # ------------------------------------------------------------
            if self.acao == self.Acao.ARQUIVADO:
                update_fields = []

                if self.processo.status != Processo.Status.ARQUIVADO:
                    self.processo.status = Processo.Status.ARQUIVADO
                    update_fields.append("status")

                # Se existir no model Processo:
                if hasattr(self.processo, "arquivado_em") and not self.processo.arquivado_em:
                    self.processo.arquivado_em = timezone.now()
                    update_fields.append("arquivado_em")

                if hasattr(self.processo, "arquivado_por") and not self.processo.arquivado_por_id:
                    self.processo.arquivado_por = self.registrado_por
                    update_fields.append("arquivado_por")

                if update_fields:
                    self.processo.save(update_fields=update_fields)
