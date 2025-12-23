from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse

from .forms import MovimentacaoForm
from .models import Processo, MovimentacaoProcesso


@login_required
def home(request):
    return render(request, "protocolos/home.html")


@login_required
def processos_list(request):
    qs = Processo.objects.all().select_related("tipo_processo", "criado_por").order_by("-criado_em")
    return render(request, "protocolos/processos_list.html", {"processos": qs})


@login_required
def processo_detail(request, pk: int):
    processo = get_object_or_404(
        Processo.objects.select_related("tipo_processo", "criado_por").prefetch_related("interessados", "movimentacoes"),
        pk=pk,
    )

    movimentacoes = processo.movimentacoes.select_related(
        "departamento_origem", "departamento_destino", "registrado_por"
    ).order_by("-registrado_em")

    if request.method == "POST":
        form = MovimentacaoForm(request.POST)
        if form.is_valid():
            mov = form.save(commit=False)
            mov.processo = processo
            mov.registrado_por = request.user
            mov.save()
            messages.success(request, "Tramitação registrada com sucesso.")
            return redirect("processo_detail", pk=processo.pk)
        else:
            messages.error(request, "Corrija os campos destacados.")
    else:
        form = MovimentacaoForm()

    return render(
        request,
        "protocolos/processo_detail.html",
        {"processo": processo, "movimentacoes": movimentacoes, "form": form},
    )
