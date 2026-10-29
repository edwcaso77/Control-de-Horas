"""Conteo de horas por semana para la nómina, con las columnas del formato de la institución."""
import datetime
from collections import defaultdict

from calendario.models import Festivo
from horas_extra.models import SolicitudHoraExtra
from turnos.models import AsignacionTurno

from .clasificacion import DIURNA, DIURNA_FESTIVA, NOCTURNA, NOCTURNA_FESTIVA, clasificar, intervalo, intervalos_de_turno

# (clave, encabezado) en el orden del formato.
COLUMNAS_HORAS = [
    ('extra_diurna', 'HORA EXTRA DIURNAS'),
    ('extra_nocturna', 'HORA EXTRA NOCTURNA'),
    ('extra_diurna_festiva', 'HORA EXTRA DIURNA FESTIVAS'),
    ('extra_nocturna_festiva', 'HORA EXTRA NOCTURNA FESTIVAS'),
    ('recargo_nocturno', 'RECARGO NOCTURNO'),
    ('diurna_festivo', 'DIURNA FESTIVO'),
    ('nocturna_festiva', 'NOCTURNAS FESTIVAS'),
    ('recargo_nocturno_festivo', 'RECARGO NOCTURNO FESTIVO'),
    ('total_horas', 'TOTAL HORAS'),
]
CLAVES = [clave for clave, _ in COLUMNAS_HORAS]


def semana_de(fecha):
    """Lunes y domingo de la semana de la fecha."""
    lunes = fecha - datetime.timedelta(days=fecha.weekday())
    return lunes, lunes + datetime.timedelta(days=6)


def conteo_semana(lunes, area=None, cargo=None):
    """Filas del conteo de una semana: una por funcionario y día trabajado.

    - Horas extra: de las solicitudes aprobadas (tiempo aprobado).
    - Recargo nocturno: horas de los turnos asignados que caen de noche en día ordinario.
    - Diurna festivo: horas de los turnos asignados en domingo o festivo, de día.
    - Nocturnas festivas y recargo nocturno festivo: horas de los turnos asignados en domingo o festivo, de noche.
    - Total horas: horas de los turnos asignados más las horas extra aprobadas.
    Devuelve (filas, totales_por_funcionario, total_general).
    """
    domingo = lunes + datetime.timedelta(days=6)
    # Festivos de la semana y del día siguiente (turnos que pasan la medianoche del domingo).
    festivos = set(Festivo.objects.filter(fecha__range=(lunes, domingo + datetime.timedelta(days=1)))
                   .values_list('fecha', flat=True))

    turnos = AsignacionTurno.objects.filter(fecha__range=(lunes, domingo)).select_related(
        'funcionario__area', 'funcionario__cargo', 'tipo_turno',
    )
    extras = SolicitudHoraExtra.objects.filter(
        fecha__range=(lunes, domingo), estado=SolicitudHoraExtra.Estado.APROBADA,
    ).select_related('funcionario__area', 'funcionario__cargo')
    if area:
        turnos = turnos.filter(funcionario__area=area)
        extras = extras.filter(funcionario__area=area)
    if cargo:
        turnos = turnos.filter(funcionario__cargo=cargo)
        extras = extras.filter(funcionario__cargo=cargo)

    filas = defaultdict(lambda: {'horas': dict.fromkeys(CLAVES, 0.0), 'turnos': [], 'motivos': []})

    for asignacion in turnos:
        fila = filas[(asignacion.funcionario, asignacion.fecha)]
        fila['turnos'].append(asignacion.etiqueta)
        fila['horas']['total_horas'] += asignacion.horas_trabajadas
        for desde, hasta in intervalos_de_turno(asignacion):
            horas = clasificar(desde, hasta, festivos)
            fila['horas']['recargo_nocturno'] += horas[NOCTURNA]
            fila['horas']['diurna_festivo'] += horas[DIURNA_FESTIVA]
            fila['horas']['nocturna_festiva'] += horas[NOCTURNA_FESTIVA]
            fila['horas']['recargo_nocturno_festivo'] += horas[NOCTURNA_FESTIVA]

    for solicitud in extras:
        fila = filas[(solicitud.funcionario, solicitud.fecha)]
        fila['motivos'].append(solicitud.motivo)
        fila['horas']['total_horas'] += solicitud.horas
        horas = clasificar(*intervalo(solicitud.fecha, solicitud.hora_inicio, solicitud.hora_fin), festivos)
        fila['horas']['extra_diurna'] += horas[DIURNA]
        fila['horas']['extra_nocturna'] += horas[NOCTURNA]
        fila['horas']['extra_diurna_festiva'] += horas[DIURNA_FESTIVA]
        fila['horas']['extra_nocturna_festiva'] += horas[NOCTURNA_FESTIVA]

    resultado = []
    for (funcionario, fecha), datos in filas.items():
        horas = {clave: round(valor, 2) for clave, valor in datos['horas'].items()}
        actividad = ' + '.join(sorted(datos['turnos']))
        if datos['motivos']:
            actividad = f'{actividad} · Hora extra: {"; ".join(datos["motivos"])}' if actividad else f'Hora extra: {"; ".join(datos["motivos"])}'
        resultado.append({
            'fecha': fecha,
            'funcionario': funcionario,
            'seccion': funcionario.area.nombre if funcionario.area else '',
            'actividad': actividad,
            'horas': horas,
        })
    resultado.sort(key=lambda f: (f['funcionario'].apellidos, f['funcionario'].nombres, f['fecha']))

    totales = defaultdict(lambda: dict.fromkeys(CLAVES, 0.0))
    for fila in resultado:
        for clave in CLAVES:
            totales[fila['funcionario']][clave] += fila['horas'][clave]
    total_general = {clave: round(sum(t[clave] for t in totales.values()), 2) for clave in CLAVES}
    totales = {f: {c: round(v, 2) for c, v in t.items()} for f, t in totales.items()}
    return resultado, totales, total_general
