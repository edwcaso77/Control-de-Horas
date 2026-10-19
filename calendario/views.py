from django.contrib.auth.decorators import login_required
from django.shortcuts import render

from .utils import contexto_mes


@login_required
def calendario_mes(request):
    return render(request, 'calendario/mes.html', contexto_mes(request))
