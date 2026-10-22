import datetime

from django import forms
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone

from funcionarios.models import Area
from funcionarios.permisos import administrador_requerido, es_administrador
from horas_extra.models import SolicitudHoraExtra
from turnos.agrupar import turnos_por_dia
from turnos.models import AsignacionTurno

from .models import Festivo
from .utils import ANIO_MAX, ANIO_MIN, _entero, contexto_mes


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
    mis_solicitudes = list(
        SolicitudHoraExtra.objects.filter(funcionario__usuario=request.user, fecha=fecha).select_related('turno__tipo_turno')
    )
    # Turnos propios que ya tienen hora extra solicitada: solo se puede pedir una vez por turno.
    turnos_con_solicitud = {s.turno_id for s in mis_solicitudes}
    return render(request, 'calendario/dia.html', {
        'fecha': fecha,
        'festivo': Festivo.objects.filter(fecha=fecha).first(),
        'anterior': fecha - datetime.timedelta(days=1),
        'siguiente': fecha + datetime.timedelta(days=1),
        'turnos': turnos,
        # La hora extra se solicita después de trabajarla: hoy o días anteriores.
        'puede_solicitar': fecha <= timezone.localdate(),
        'mis_solicitudes': mis_solicitudes,
        'turnos_con_solicitud': turnos_con_solicitud,
        'areas': Area.objects.filter(activo=True) if admin else [],
        'area': area,
    })


class FestivoForm(forms.ModelForm):
    class Meta:
        model = Festivo
        fields = ['fecha', 'nombre']
        widgets = {'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}


@administrador_requerido
def festivos(request):
    """Festivos de un año: se ven, se cargan los de Colombia, se agregan manuales o se quitan."""
    hoy = timezone.localdate()
    anio = _entero(request.GET.get('anio') or request.POST.get('anio'), hoy.year, ANIO_MIN, ANIO_MAX)
    form = FestivoForm(request.POST if request.POST.get('accion') == 'agregar' else None)

    if request.method == 'POST':
        accion = request.POST.get('accion')
        if accion == 'cargar':
            creados = Festivo.cargar_colombia(anio)
            messages.success(request, f'Festivos de Colombia {anio} cargados ({creados} nuevo{"s" if creados != 1 else ""}).')
            return redirect(f"{reverse('calendario:festivos')}?anio={anio}")
        if accion == 'agregar' and form.is_valid():
            festivo = form.save()
            messages.success(request, f'Festivo agregado: {festivo}.')
            return redirect(f"{reverse('calendario:festivos')}?anio={festivo.fecha.year}")
        if accion == 'quitar':
            festivo = get_object_or_404(Festivo, pk=request.POST.get('pk'))
            festivo.delete()
            messages.success(request, f'Festivo quitado: {festivo.fecha:%d/%m/%Y} · {festivo.nombre}.')
            return redirect(f"{reverse('calendario:festivos')}?anio={anio}")

    return render(request, 'calendario/festivos.html', {
        'anio': anio,
        'anios': range(ANIO_MIN, ANIO_MAX + 1),
        'festivos': Festivo.objects.filter(fecha__year=anio),
        'form': form,
    })
