"""Clasificación de horas para la nómina: diurnas, nocturnas, festivas.

Reglas (Colombia, Ley 2466 de 2025):
- Trabajo nocturno: de 19:00 a 06:00. El resto es diurno.
- Festivo: los días de la tabla de festivos y todos los domingos (dominical).
- Si un tramo pasa la medianoche, cada parte se clasifica según el día en que realmente cae.
"""
import datetime

INICIO_NOCHE = datetime.time(19, 0)
FIN_NOCHE = datetime.time(6, 0)
DOMINGO_ES_FESTIVO = True

DIURNA = 'diurna'
NOCTURNA = 'nocturna'
DIURNA_FESTIVA = 'diurna_festiva'
NOCTURNA_FESTIVA = 'nocturna_festiva'
CATEGORIAS = (DIURNA, NOCTURNA, DIURNA_FESTIVA, NOCTURNA_FESTIVA)


def es_festivo(fecha, festivos):
    return fecha in festivos or (DOMINGO_ES_FESTIVO and fecha.weekday() == 6)


def es_nocturna(hora):
    return hora >= INICIO_NOCHE or hora < FIN_NOCHE


def intervalo(fecha, inicio, fin):
    """(desde, hasta) como fechas y horas. Si fin es menor o igual a inicio, termina al día siguiente."""
    desde = datetime.datetime.combine(fecha, inicio)
    hasta = datetime.datetime.combine(fecha, fin)
    if hasta <= desde:
        hasta += datetime.timedelta(days=1)
    return desde, hasta


def clasificar(desde, hasta, festivos):
    """Reparte el intervalo [desde, hasta) en horas por categoría. Devuelve {categoría: horas}."""
    totales = dict.fromkeys(CATEGORIAS, 0.0)
    # Cortes: medianoche, inicio y fin de la noche de cada día que toca el intervalo.
    cortes = {desde, hasta}
    dia = desde.date()
    while datetime.datetime.combine(dia, datetime.time.min) < hasta:
        for hora in (datetime.time.min, FIN_NOCHE, INICIO_NOCHE):
            momento = datetime.datetime.combine(dia, hora)
            if desde < momento < hasta:
                cortes.add(momento)
        dia += datetime.timedelta(days=1)
    puntos = sorted(cortes)
    for inicio, fin in zip(puntos, puntos[1:]):
        festivo = es_festivo(inicio.date(), festivos)
        nocturna = es_nocturna(inicio.time())
        if festivo:
            categoria = NOCTURNA_FESTIVA if nocturna else DIURNA_FESTIVA
        else:
            categoria = NOCTURNA if nocturna else DIURNA
        totales[categoria] += (fin - inicio).total_seconds() / 3600
    return totales


def intervalos_de_turno(asignacion):
    """Intervalos de trabajo de un turno asignado. Los de horas variables sin hora de inicio (HC) no tienen."""
    tipo = asignacion.tipo_turno
    if tipo.horas_variables:
        if asignacion.hora_inicio is None or asignacion.horas is None:
            return []
        desde = datetime.datetime.combine(asignacion.fecha, asignacion.hora_inicio)
        return [(desde, desde + datetime.timedelta(hours=float(asignacion.horas)))]
    return [intervalo(asignacion.fecha, inicio, fin) for inicio, fin in tipo.bloques]
