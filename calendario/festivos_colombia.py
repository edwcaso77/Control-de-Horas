"""Festivos de Colombia (Ley 51 de 1983, «Ley Emiliani»)."""
import datetime

# Festivos que siempre caen en su fecha.
FIJOS = [
    (1, 1, 'Año Nuevo'),
    (5, 1, 'Día del Trabajo'),
    (7, 20, 'Día de la Independencia'),
    (8, 7, 'Batalla de Boyacá'),
    (12, 8, 'Inmaculada Concepción'),
    (12, 25, 'Navidad'),
]

# Festivos que se corren al lunes siguiente si no caen en lunes.
TRASLADABLES = [
    (1, 6, 'Día de los Reyes Magos'),
    (3, 19, 'Día de San José'),
    (6, 29, 'San Pedro y San Pablo'),
    (8, 15, 'Asunción de la Virgen'),
    (10, 12, 'Día de la Raza'),
    (11, 1, 'Día de Todos los Santos'),
    (11, 11, 'Independencia de Cartagena'),
]


def domingo_de_pascua(anio):
    """Fecha del Domingo de Pascua (algoritmo de Meeus/Jones/Butcher para el calendario gregoriano)."""
    a = anio % 19
    b, c = divmod(anio, 100)
    d, e = divmod(b, 4)
    f = (b + 8) // 25
    g = (b - f + 1) // 3
    h = (19 * a + b - d - g + 15) % 30
    i, k = divmod(c, 4)
    l = (32 + 2 * e + 2 * i - h - k) % 7
    m = (a + 11 * h + 22 * l) // 451
    mes, dia = divmod(h + l - 7 * m + 114, 31)
    return datetime.date(anio, mes, dia + 1)


def _siguiente_lunes(fecha):
    return fecha + datetime.timedelta(days=(7 - fecha.weekday()) % 7)


def festivos(anio):
    """Lista ordenada de (fecha, nombre) con los festivos de Colombia del año."""
    pascua = domingo_de_pascua(anio)
    dias = [(datetime.date(anio, mes, dia), nombre) for mes, dia, nombre in FIJOS]
    dias += [(_siguiente_lunes(datetime.date(anio, mes, dia)), nombre) for mes, dia, nombre in TRASLADABLES]
    dias += [
        (pascua - datetime.timedelta(days=3), 'Jueves Santo'),
        (pascua - datetime.timedelta(days=2), 'Viernes Santo'),
        (_siguiente_lunes(pascua + datetime.timedelta(days=39)), 'Ascensión del Señor'),
        (_siguiente_lunes(pascua + datetime.timedelta(days=60)), 'Corpus Christi'),
        (_siguiente_lunes(pascua + datetime.timedelta(days=68)), 'Sagrado Corazón'),
    ]
    return sorted(dias)
