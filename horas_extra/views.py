from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.utils import timezone
from django.views.decorators.http import require_POST

from funcionarios.permisos import administrador_requerido
from turnos.models import AsignacionTurno

from .forms import RevisionForm, SolicitudForm
from .models import SolicitudHoraExtra


def _volver_al_dia(fecha):
    return redirect('calendario:dia', anio=fecha.year, mes=fecha.month, dia=fecha.day)


@login_required
def solicitar(request, turno_id):
    """El funcionario solicita hora extra sobre uno de sus turnos ya trabajados (hoy o días anteriores)."""
    turno = get_object_or_404(
        AsignacionTurno.objects.select_related('tipo_turno', 'funcionario'),
        pk=turno_id, funcionario__usuario=request.user,
    )
    if turno.fecha > timezone.localdate():
        messages.error(request, 'La hora extra se solicita después de trabajarla: este día todavía no ha llegado.')
        return _volver_al_dia(turno.fecha)
    if turno.solicitudes_hora_extra.exists():
        messages.error(request, 'Ya solicitó hora extra para este turno. Solo se puede solicitar una vez.')
        return _volver_al_dia(turno.fecha)

    # Se propone que la hora extra empiece cuando termina el turno.
    fin_turno = turno.hora_fin or turno.tipo_turno.hora_fin_2 or turno.tipo_turno.hora_fin
    form = SolicitudForm(request.POST or None, initial={'hora_inicio': fin_turno}, funcionario=turno.funcionario)
    if form.is_valid():
        solicitud = form.save(commit=False)
        solicitud.funcionario = turno.funcionario
        solicitud.fecha = turno.fecha
        solicitud.turno = turno
        solicitud.save()
        messages.success(request, f'Solicitud de hora extra enviada ({solicitud.horas_texto}). El administrador la revisará.')
        return _volver_al_dia(turno.fecha)
    return render(request, 'horas_extra/solicitar.html', {'form': form, 'turno': turno})


@require_POST
@login_required
def cancelar(request, pk):
    """El funcionario cancela una solicitud suya que todavía no se ha revisado."""
    solicitud = get_object_or_404(SolicitudHoraExtra, pk=pk, funcionario__usuario=request.user)
    if not solicitud.pendiente:
        messages.error(request, 'Esa solicitud ya fue revisada y no se puede cancelar.')
    else:
        solicitud.delete()
        messages.success(request, 'Solicitud cancelada.')
    return _volver_al_dia(solicitud.fecha)


ESTADOS_FILTRO = {
    'pendientes': SolicitudHoraExtra.Estado.PENDIENTE,
    'aprobadas': SolicitudHoraExtra.Estado.APROBADA,
    'rechazadas': SolicitudHoraExtra.Estado.RECHAZADA,
}


@administrador_requerido
def lista(request):
    estado = request.GET.get('estado', 'pendientes')
    solicitudes = SolicitudHoraExtra.visibles_para(request.user).select_related(
        'funcionario__cargo', 'funcionario__area', 'turno__tipo_turno', 'revisado_por', 'administrador',
    )
    if estado in ESTADOS_FILTRO:
        solicitudes = solicitudes.filter(estado=ESTADOS_FILTRO[estado])
    else:
        estado = 'todas'
    return render(request, 'horas_extra/lista.html', {'solicitudes': solicitudes, 'estado': estado})


@administrador_requerido
def revisar(request, pk):
    """El administrador corrige el horario si hace falta, comenta y aprueba o rechaza."""
    # Cada administrador solo abre las solicitudes dirigidas a él (y las antiguas sin administrador).
    solicitud = get_object_or_404(
        SolicitudHoraExtra.visibles_para(request.user)
        .select_related('funcionario__cargo', 'funcionario__area', 'turno__tipo_turno', 'administrador'),
        pk=pk,
    )
    form = RevisionForm(request.POST or None, instance=solicitud)
    if request.method == 'POST':
        decision = request.POST.get('decision')
        if decision not in (SolicitudHoraExtra.Estado.APROBADA, SolicitudHoraExtra.Estado.RECHAZADA):
            raise Http404
        if form.is_valid():
            solicitud = form.save(commit=False)
            solicitud.estado = decision
            solicitud.revisado_por = request.user
            solicitud.revisado_en = timezone.now()
            solicitud.save()
            messages.success(
                request, f'Hora extra de {solicitud.funcionario} {solicitud.get_estado_display().lower()} ({solicitud.horas_texto}).',
            )
            return redirect('horas_extra:lista')
    return render(request, 'horas_extra/revisar.html', {'form': form, 'solicitud': solicitud})
