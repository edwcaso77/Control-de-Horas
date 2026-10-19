import datetime
from collections import defaultdict
from urllib.parse import urlencode

from django.contrib import messages
from django.db import transaction
from django.db.models import Count, Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from calendario.utils import contexto_mes
from funcionarios.models import Area, Funcionario
from funcionarios.permisos import administrador_requerido

from .forms import TipoTurnoForm
from .models import AsignacionTurno, TipoTurno


def _area_elegida(datos):
    area = datos.get('area', '')
    return Area.objects.filter(pk=area).first() if area.isdigit() else None


def _funcionarios_activos(area):
    funcionarios = Funcionario.objects.filter(usuario__is_active=True).select_related('cargo', 'area')
    return funcionarios.filter(area=area) if area else funcionarios


@administrador_requerido
def cuadro(request):
    """Calendario del mes en modo edición: cada día muestra cuántos funcionarios hay en cada turno."""
    contexto = contexto_mes(request)
    area = _area_elegida(request.GET)

    dias = [dia for semana in contexto['semanas'] for dia in semana]
    conteos = (
        AsignacionTurno.objects
        .filter(fecha__range=(dias[0]['fecha'], dias[-1]['fecha']), funcionario__usuario__is_active=True)
        .filter(**({'funcionario__area': area} if area else {}))
        .values('fecha', 'tipo_turno')
        .annotate(total=Count('id'))
    )
    tipos = {t.pk: t for t in TipoTurno.objects.all()}
    resumen = defaultdict(list)
    for fila in conteos:
        resumen[fila['fecha']].append({'tipo': tipos[fila['tipo_turno']], 'total': fila['total']})
    orden = list(tipos)
    for dia in dias:
        dia['resumen'] = sorted(resumen[dia['fecha']], key=lambda item: orden.index(item['tipo'].pk))

    contexto.update({
        'areas': Area.objects.filter(activo=True),
        'area': area,
        'parametros_extra': f'&area={area.pk}' if area else '',
        'tipos_activos': TipoTurno.objects.filter(activo=True),
    })
    return render(request, 'turnos/cuadro.html', contexto)


NO_CAMBIAR = '-'
MAX_DIAS_SELECCIONADOS = 62


def _guardar_turnos(request, funcionarios, fechas, tipos):
    """Aplica el turno elegido para cada funcionario en todas las fechas.

    Valor vacío: quita el turno. NO_CAMBIAR: deja lo que haya. Un turno desconocido se ignora.
    """
    tipos_por_id = {str(t.pk): t for t in tipos}
    with transaction.atomic():
        for funcionario in funcionarios:
            valor = request.POST.get(f'turno_{funcionario.pk}', NO_CAMBIAR)
            if valor == '':
                AsignacionTurno.objects.filter(funcionario=funcionario, fecha__in=fechas).delete()
            elif valor in tipos_por_id:
                for un_dia in fechas:
                    AsignacionTurno.objects.update_or_create(
                        funcionario=funcionario, fecha=un_dia,
                        defaults={'tipo_turno': tipos_por_id[valor], 'asignado_por': request.user},
                    )


def _volver_al_cuadro(fecha, area):
    parametros = {'anio': fecha.year, 'mes': fecha.month}
    if area:
        parametros['area'] = area.pk
    return redirect(f"{reverse('turnos:cuadro')}?{urlencode(parametros)}")


def _fechas_elegidas(texto):
    """Convierte '2026-10-20,2026-10-22' en una lista ordenada de fechas válidas, sin repetir."""
    fechas = set()
    for parte in texto.split(','):
        try:
            fechas.add(datetime.date.fromisoformat(parte.strip()))
        except ValueError:
            continue
    return sorted(fechas)[:MAX_DIAS_SELECCIONADOS]


@administrador_requerido
def dia(request, anio, mes, dia):
    """Asigna el turno de cada funcionario en un día, o en toda su semana."""
    try:
        fecha = datetime.date(anio, mes, dia)
    except ValueError:
        raise Http404
    area = _area_elegida(request.POST if request.method == 'POST' else request.GET)
    funcionarios = list(_funcionarios_activos(area))

    lunes = fecha - datetime.timedelta(days=fecha.weekday())
    semana = [lunes + datetime.timedelta(days=i) for i in range(7)]
    asignaciones = AsignacionTurno.objects.filter(funcionario__in=funcionarios, fecha__in=semana).select_related('tipo_turno')
    por_funcionario = defaultdict(dict)
    for asignacion in asignaciones:
        por_funcionario[asignacion.funcionario_id][asignacion.fecha] = asignacion.tipo_turno

    # Turnos que se pueden elegir: los activos y los que ya estén asignados ese día aunque se hayan desactivado.
    usados_hoy = {t.pk for turnos in por_funcionario.values() for f, t in turnos.items() if f == fecha}
    tipos = list(TipoTurno.objects.filter(Q(activo=True) | Q(pk__in=usados_hoy)))

    if request.method == 'POST':
        fechas = semana if request.POST.get('alcance') == 'semana' else [fecha]
        _guardar_turnos(request, funcionarios, fechas, tipos)
        if len(fechas) == 1:
            messages.success(request, f'Turnos del {fecha:%d/%m/%Y} guardados.')
        else:
            messages.success(request, f'Turnos de la semana del {semana[0]:%d/%m} al {semana[-1]:%d/%m/%Y} guardados.')
        return _volver_al_cuadro(fecha, area)

    filas = [
        {
            'funcionario': f,
            'turno': por_funcionario[f.pk].get(fecha),
            'semana': [por_funcionario[f.pk].get(d) for d in semana],
        }
        for f in funcionarios
    ]
    return render(request, 'turnos/dia.html', {
        'fecha': fecha,
        'anterior': fecha - datetime.timedelta(days=1),
        'siguiente': fecha + datetime.timedelta(days=1),
        'semana': semana,
        'filas': filas,
        'tipos': tipos,
        'areas': Area.objects.filter(activo=True),
        'area': area,
    })


@administrador_requerido
def varios(request):
    """Asigna turnos en varios días elegidos en el cuadro del mes (?fechas=AAAA-MM-DD,AAAA-MM-DD…)."""
    datos = request.POST if request.method == 'POST' else request.GET
    fechas = _fechas_elegidas(datos.get('fechas', ''))
    area = _area_elegida(datos)
    if not fechas:
        messages.error(request, 'Seleccione al menos un día en el cuadro.')
        return redirect('turnos:cuadro')
    funcionarios = list(_funcionarios_activos(area))

    asignaciones = AsignacionTurno.objects.filter(funcionario__in=funcionarios, fecha__in=fechas).select_related('tipo_turno')
    por_funcionario = defaultdict(dict)
    for asignacion in asignaciones:
        por_funcionario[asignacion.funcionario_id][asignacion.fecha] = asignacion.tipo_turno

    usados = {asignacion.tipo_turno_id for asignacion in asignaciones}
    tipos = list(TipoTurno.objects.filter(Q(activo=True) | Q(pk__in=usados)))

    if request.method == 'POST':
        _guardar_turnos(request, funcionarios, fechas, tipos)
        messages.success(request, f'Turnos guardados en {len(fechas)} día{"s" if len(fechas) != 1 else ""}.')
        return _volver_al_cuadro(fechas[0], area)

    filas = []
    for f in funcionarios:
        turnos = [por_funcionario[f.pk].get(d) for d in fechas]
        distintos = {t.pk if t else None for t in turnos}
        # Si tiene el mismo turno en todos los días elegidos, ese aparece seleccionado; si no, "No cambiar".
        comun = turnos[0] if len(distintos) == 1 and turnos[0] else None
        filas.append({'funcionario': f, 'turnos': turnos, 'comun': comun})

    return render(request, 'turnos/varios.html', {
        'fechas': fechas,
        'fechas_texto': ','.join(d.isoformat() for d in fechas),
        'filas': filas,
        'tipos': tipos,
        'area': area,
        'no_cambiar': NO_CAMBIAR,
    })


@administrador_requerido
def tipos(request):
    return render(request, 'turnos/tipos.html', {'tipos': TipoTurno.objects.all()})


@administrador_requerido
def tipo_crear(request):
    form = TipoTurnoForm(request.POST or None)
    if form.is_valid():
        tipo = form.save()
        messages.success(request, f'Turno «{tipo.nombre}» creado.')
        return redirect('turnos:tipos')
    return render(request, 'turnos/tipo_formulario.html', {'form': form, 'titulo': 'Nuevo tipo de turno'})


@administrador_requerido
def tipo_editar(request, pk):
    tipo = get_object_or_404(TipoTurno, pk=pk)
    form = TipoTurnoForm(request.POST or None, instance=tipo)
    if form.is_valid():
        form.save()
        messages.success(request, f'Turno «{tipo.nombre}» actualizado.')
        return redirect('turnos:tipos')
    return render(request, 'turnos/tipo_formulario.html', {'form': form, 'titulo': f'Editar turno: {tipo.nombre}'})


@require_POST
@administrador_requerido
def tipo_estado(request, pk):
    tipo = get_object_or_404(TipoTurno, pk=pk)
    tipo.activo = not tipo.activo
    tipo.save(update_fields=['activo'])
    messages.success(request, f'Turno «{tipo.nombre}» {"activado" if tipo.activo else "desactivado"}.')
    return redirect('turnos:tipos')
