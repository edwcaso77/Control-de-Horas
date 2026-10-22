import datetime
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.views.decorators.http import require_POST

from calendario.models import Festivo
from calendario.utils import contexto_mes
from funcionarios.models import Area, Cargo, Funcionario
from funcionarios.permisos import administrador_requerido

from .forms import TipoTurnoForm
from .agrupar import turnos_por_dia
from .models import TURNOS_POR_DIA, AsignacionTurno, TipoTurno, formato_horas


def _area_elegida(datos):
    area = datos.get('area', '')
    return Area.objects.filter(pk=area).first() if area.isdigit() else None


def _cargo_elegido(datos):
    cargo = datos.get('cargo', '')
    return Cargo.objects.filter(pk=cargo).first() if cargo.isdigit() else None


def _funcionarios_activos(area, cargo=None):
    funcionarios = Funcionario.objects.filter(usuario__is_active=True).select_related('cargo', 'area')
    if area:
        funcionarios = funcionarios.filter(area=area)
    if cargo:
        funcionarios = funcionarios.filter(cargo=cargo)
    return funcionarios


@administrador_requerido
def cuadro(request):
    """Calendario del mes en modo edición: cada día muestra quién tiene turno y cuál."""
    contexto = contexto_mes(request)
    area = _area_elegida(request.GET)

    dias = [dia for semana in contexto['semanas'] for dia in semana]
    asignaciones = (
        AsignacionTurno.objects
        .filter(fecha__range=(dias[0]['fecha'], dias[-1]['fecha']), funcionario__usuario__is_active=True)
        .filter(**({'funcionario__area': area} if area else {}))
        .select_related('funcionario', 'tipo_turno')
    )
    por_dia = turnos_por_dia(asignaciones)
    for dia in dias:
        dia['turnos'] = por_dia[dia['fecha']]

    contexto.update({
        'areas': Area.objects.filter(activo=True),
        'area': area,
        'parametros_extra': f'&area={area.pk}' if area else '',
        'tipos_activos': TipoTurno.objects.filter(activo=True),
        # Herramientas de prueba: solo en el computador de desarrollo, nunca en el sitio publicado.
        'modo_local': settings.DEBUG,
        'total_turnos': AsignacionTurno.objects.count() if settings.DEBUG else 0,
    })
    return render(request, 'turnos/cuadro.html', contexto)


@require_POST
@administrador_requerido
def borrar_agenda(request):
    """Elimina todos los turnos asignados. Solo existe en local (DEBUG=True), para hacer pruebas."""
    if not settings.DEBUG:
        raise Http404
    borrados, _ = AsignacionTurno.objects.all().delete()
    messages.success(request, f'Agenda eliminada: {borrados} turno{"s" if borrados != 1 else ""} borrado{"s" if borrados != 1 else ""}.')
    parametros = {k: v for k in ('anio', 'mes', 'area') if (v := request.POST.get(k, '')).isdigit()}
    return redirect(f"{reverse('turnos:cuadro')}?{urlencode(parametros)}" if parametros else reverse('turnos:cuadro'))


MAX_DIAS_SELECCIONADOS = 62


def _leer_celda(post, clave, tipos_por_id, errores, descripcion):
    """Lee los turnos de una celda del formulario: «clave_1» (principal), «clave_2» (adicional),
    para los turnos de horas variables «horas_clave_N» y, si piden hora de inicio, «inicio_clave_N».

    Devuelve [(tipo, horas, hora_inicio), …] sin repetir tipos, o None si la celda no vino en el formulario
    o tiene datos inválidos (en ese caso no se cambia nada de esa celda y se anota el error).
    """
    valores = [post.get(f'{clave}_{n}') for n in range(1, TURNOS_POR_DIA + 1)]
    if all(valor is None for valor in valores):
        return None
    elegidos = {}
    for n, valor in enumerate(valores, start=1):
        tipo = tipos_por_id.get(valor or '')
        if tipo is None:
            continue
        horas = inicio = None
        if tipo.pide_hora_inicio:
            try:
                inicio = datetime.time.fromisoformat(post.get(f'inicio_{clave}_{n}', '').strip())
            except ValueError:
                errores.append(f'{descripcion}: {tipo.abreviatura} necesita la hora de inicio. Esa celda no se guardó.')
                return None
        if tipo.horas_variables:
            try:
                horas = Decimal(post.get(f'horas_{clave}_{n}', '').replace(',', '.'))
            except InvalidOperation:
                horas = None
            if horas is None or not horas.is_finite() or not (tipo.horas_minimas <= horas <= tipo.horas_maximas):
                errores.append(
                    f'{descripcion}: {tipo.abreviatura} necesita entre {formato_horas(tipo.horas_minimas)} y '
                    f'{formato_horas(tipo.horas_maximas)} horas. Esa celda no se guardó.'
                )
                return None
        elegidos[tipo.pk] = (tipo, horas, inicio)
    return list(elegidos.values())


def _aplicar_turnos(funcionario, fechas, elegidos, usuario):
    """Deja en cada fecha exactamente los turnos elegidos para el funcionario. Devuelve cuántos cambios hubo."""
    cambios = 0
    nuevos = {tipo.pk for tipo, _, _ in elegidos}
    for fecha in fechas:
        actuales = {a.tipo_turno_id: a for a in AsignacionTurno.objects.filter(funcionario=funcionario, fecha=fecha)}
        for pk, asignacion in actuales.items():
            if pk not in nuevos:
                asignacion.delete()
                cambios += 1
        for tipo, horas, inicio in elegidos:
            actual = actuales.get(tipo.pk)
            if actual and actual.horas == horas and actual.hora_inicio == inicio:
                continue
            AsignacionTurno.objects.update_or_create(
                funcionario=funcionario, fecha=fecha, tipo_turno=tipo,
                defaults={'horas': horas, 'hora_inicio': inicio, 'asignado_por': usuario},
            )
            cambios += 1
    return cambios


def _turnos_por_funcionario_y_fecha(asignaciones):
    """{(funcionario_id, fecha): [turnos ordenados por tipo]} para llenar las celdas."""
    orden = {pk: i for i, pk in enumerate(TipoTurno.objects.values_list('pk', flat=True))}
    resultado = defaultdict(list)
    for asignacion in asignaciones:
        resultado[(asignacion.funcionario_id, asignacion.fecha)].append(asignacion)
    for lista in resultado.values():
        lista.sort(key=lambda a: orden[a.tipo_turno_id])
    return resultado


def _ranuras(turnos):
    """Los turnos de una celda repartidos en principal y adicional: [primero o None, segundo o None]."""
    return (list(turnos) + [None] * TURNOS_POR_DIA)[:TURNOS_POR_DIA]


def _tipos_elegibles(asignaciones):
    """Turnos que se pueden elegir: los activos y los que ya estén asignados aunque se hayan desactivado."""
    usados = {a.tipo_turno_id for a in asignaciones}
    return list(TipoTurno.objects.filter(Q(activo=True) | Q(pk__in=usados)))


def _avisar_errores(request, errores):
    for error in errores:
        messages.warning(request, error)


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
    """Asigna los turnos (principal y adicional) de cada funcionario en un día, o en toda su semana."""
    try:
        fecha = datetime.date(anio, mes, dia)
    except ValueError:
        raise Http404
    area = _area_elegida(request.POST if request.method == 'POST' else request.GET)
    funcionarios = list(_funcionarios_activos(area))

    lunes = fecha - datetime.timedelta(days=fecha.weekday())
    semana = [lunes + datetime.timedelta(days=i) for i in range(7)]
    asignaciones = list(
        AsignacionTurno.objects.filter(funcionario__in=funcionarios, fecha__in=semana).select_related('tipo_turno')
    )
    celdas = _turnos_por_funcionario_y_fecha(asignaciones)
    tipos = _tipos_elegibles([a for a in asignaciones if a.fecha == fecha])

    if request.method == 'POST':
        tipos_por_id = {str(t.pk): t for t in tipos}
        fechas = semana if request.POST.get('alcance') == 'semana' else [fecha]
        errores = []
        with transaction.atomic():
            for funcionario in funcionarios:
                elegidos = _leer_celda(request.POST, f'turno_{funcionario.pk}', tipos_por_id, errores, funcionario.nombre_completo)
                if elegidos is not None:
                    _aplicar_turnos(funcionario, fechas, elegidos, request.user)
        _avisar_errores(request, errores)
        if len(fechas) == 1:
            messages.success(request, f'Turnos del {fecha:%d/%m/%Y} guardados.')
        else:
            messages.success(request, f'Turnos de la semana del {semana[0]:%d/%m} al {semana[-1]:%d/%m/%Y} guardados.')
        return _volver_al_cuadro(fecha, area)

    filas = [
        {
            'funcionario': f,
            'clave': f'turno_{f.pk}',
            'ranuras': _ranuras(celdas[(f.pk, fecha)]),
            'semana': [celdas[(f.pk, d)] for d in semana],
        }
        for f in funcionarios
    ]
    return render(request, 'turnos/dia.html', {
        'fecha': fecha,
        'festivo': Festivo.objects.filter(fecha=fecha).first(),
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
    """Asigna turnos en varios días elegidos en el cuadro del mes (?fechas=AAAA-MM-DD,AAAA-MM-DD…).

    Muestra una columna por día: cada celda es el turno principal y el adicional de un funcionario en ese día.
    """
    datos = request.POST if request.method == 'POST' else request.GET
    fechas = _fechas_elegidas(datos.get('fechas', ''))
    area = _area_elegida(datos)
    cargo = _cargo_elegido(datos)
    if not fechas:
        messages.error(request, 'Seleccione al menos un día en el cuadro.')
        return redirect('turnos:cuadro')
    funcionarios = list(_funcionarios_activos(area, cargo))

    asignaciones = list(
        AsignacionTurno.objects.filter(funcionario__in=funcionarios, fecha__in=fechas).select_related('tipo_turno')
    )
    celdas = _turnos_por_funcionario_y_fecha(asignaciones)
    tipos = _tipos_elegibles(asignaciones)

    if request.method == 'POST':
        tipos_por_id = {str(t.pk): t for t in tipos}
        cambios = 0
        errores = []
        with transaction.atomic():
            for funcionario in funcionarios:
                for fecha in fechas:
                    descripcion = f'{funcionario.nombre_completo} el {fecha:%d/%m}'
                    elegidos = _leer_celda(
                        request.POST, f'turno_{funcionario.pk}_{fecha.isoformat()}', tipos_por_id, errores, descripcion,
                    )
                    if elegidos is not None:
                        cambios += _aplicar_turnos(funcionario, [fecha], elegidos, request.user)
        _avisar_errores(request, errores)
        messages.success(request, f'Turnos guardados ({cambios} cambio{"s" if cambios != 1 else ""}).')
        return _volver_al_cuadro(fechas[0], area)

    filas = [
        {
            'funcionario': f,
            'celdas': [
                {
                    'fecha': d,
                    'clave': f'turno_{f.pk}_{d.isoformat()}',
                    'etiqueta': f'{f.nombre_completo}, {d:%d/%m}',
                    'ranuras': _ranuras(celdas[(f.pk, d)]),
                }
                for d in fechas
            ],
        }
        for f in funcionarios
    ]
    return render(request, 'turnos/varios.html', {
        'fechas': fechas,
        'fechas_texto': ','.join(d.isoformat() for d in fechas),
        'filas': filas,
        'tipos': tipos,
        'area': area,
        'cargo': cargo,
        'cargos': Cargo.objects.filter(activo=True),
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
