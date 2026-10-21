import datetime

from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import render
from django.utils import timezone

from funcionarios.models import Area
from funcionarios.permisos import es_administrador
from horas_extra.models import SolicitudHoraExtra
from turnos.agrupar import turnos_por_dia
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
    por_dia = turnos_por_dia(_turnos_visibles(request, fecha__range=(dias[0]['fecha'], dias[-1]['fecha'])))
    for dia in dias:
        dia['turnos'] = por_dia[dia['fecha']]
    return render(request, 'calendario/mes.html', contexto)


@login_required
def dia(request, anio, mes, dia):
    """Consulta de los turnos de un día. El funcionario que no es administrador solo ve el suyo."""
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

    turnos = turnos_por_dia(asignaciones)[fecha]
    return render(request, 'calendario/dia.html', {
        'fecha': fecha,
        'anterior': fecha - datetime.timedelta(days=1),
        'siguiente': fecha + datetime.timedelta(days=1),
        'turnos': turnos,
        # La hora extra se solicita después de trabajarla: hoy o días anteriores.
        'puede_solicitar': fecha <= timezone.localdate(),
        'mis_solicitudes': SolicitudHoraExtra.objects.filter(funcionario__usuario=request.user, fecha=fecha)
                                                     .select_related('turno__tipo_turno'),
        'areas': Area.objects.filter(activo=True) if admin else [],
        'area': area,
    })
