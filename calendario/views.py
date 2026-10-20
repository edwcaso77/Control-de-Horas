import datetime

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render

from funcionarios.models import Area
from funcionarios.permisos import es_administrador
from turnos.franjas import agrupar_por_franja
from turnos.models import AsignacionTurno

from .utils import contexto_mes


def _turnos_visibles(request, **filtros):
    """Turnos que puede consultar quien inició sesión: el administrador ve todos; el funcionario, solo los suyos."""
    asignaciones = (
        AsignacionTurno.objects
        .filter(funcionario__usuario__is_active=True, **filtros)
        .select_related('funcionario__cargo', 'funcionario__area', 'tipo_turno')
    )
    if es_administrador(request.user):
        return asignaciones
    return asignaciones.filter(funcionario__usuario=request.user)


@login_required
def calendario_mes(request):
    contexto = contexto_mes(request)
    dias = [dia for semana in contexto['semanas'] for dia in semana]
    # Para la lista que aparece al pasar el mouse sobre cada día.
    por_dia = agrupar_por_franja(_turnos_visibles(request, fecha__range=(dias[0]['fecha'], dias[-1]['fecha'])))
    for dia in dias:
        franjas = por_dia[dia['fecha']]
        dia['franjas'] = _franjas_en_orden(franjas)
        dia['total'] = sum(len(lista) for lista in franjas.values())
    return render(request, 'calendario/mes.html', contexto)


def _franjas_en_orden(franjas):
    """[(título, clave, turnos), …] para mostrar Mañana, Tarde y Otros en ese orden."""
    return [
        ('Mañana', 'manana', franjas['manana']),
        ('Tarde', 'tarde', franjas['tarde']),
        ('Otros', 'otros', franjas['otros']),
    ]


@login_required
def dia(request, anio, mes, dia):
    """Consulta de los turnos de un día, por franjas. El funcionario que no es administrador solo ve el suyo."""
    try:
        fecha = datetime.date(anio, mes, dia)
    except ValueError:
        raise Http404

    admin = es_administrador(request.user)
    asignaciones = _turnos_visibles(request, fecha=fecha)
    area = None
    if admin:
        area_id = request.GET.get('area', '')
        area = Area.objects.filter(pk=area_id).first() if area_id.isdigit() else None
        if area:
            asignaciones = asignaciones.filter(funcionario__area=area)

    franjas = agrupar_por_franja(asignaciones)[fecha]
    return render(request, 'calendario/dia.html', {
        'fecha': fecha,
        'anterior': fecha - datetime.timedelta(days=1),
        'siguiente': fecha + datetime.timedelta(days=1),
        'franjas': _franjas_en_orden(franjas),
        'total': sum(len(lista) for lista in franjas.values()),
        'areas': Area.objects.filter(activo=True) if admin else [],
        'area': area,
    })
