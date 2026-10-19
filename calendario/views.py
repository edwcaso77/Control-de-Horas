import datetime

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from funcionarios.models import Area
from funcionarios.permisos import es_administrador
from turnos.franjas import agrupar_por_franja
from turnos.models import AsignacionTurno

from .utils import contexto_mes


@login_required
def calendario_mes(request):
    return render(request, 'calendario/mes.html', contexto_mes(request))


@login_required
def dia(request, anio, mes, dia):
    """Consulta de los turnos de un día, por franjas. El funcionario que no es administrador solo ve el suyo."""
    try:
        fecha = datetime.date(anio, mes, dia)
    except ValueError:
        raise Http404

    admin = es_administrador(request.user)
    asignaciones = (
        AsignacionTurno.objects
        .filter(fecha=fecha, funcionario__usuario__is_active=True)
        .select_related('funcionario__cargo', 'funcionario__area', 'tipo_turno')
    )
    area = None
    if admin:
        area_id = request.GET.get('area', '')
        area = Area.objects.filter(pk=area_id).first() if area_id.isdigit() else None
        if area:
            asignaciones = asignaciones.filter(funcionario__area=area)
    else:
        asignaciones = asignaciones.filter(funcionario__usuario=request.user)

    franjas = agrupar_por_franja(asignaciones)[fecha]
    return render(request, 'calendario/dia.html', {
        'fecha': fecha,
        'anterior': fecha - datetime.timedelta(days=1),
        'siguiente': fecha + datetime.timedelta(days=1),
        'franjas': [
            ('Mañana', 'manana', franjas['manana']),
            ('Tarde', 'tarde', franjas['tarde']),
            ('Otros', 'otros', franjas['otros']),
        ],
        'total': sum(len(lista) for lista in franjas.values()),
        'areas': Area.objects.filter(activo=True) if admin else [],
        'area': area,
    })
