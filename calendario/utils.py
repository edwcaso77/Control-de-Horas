import calendar

from django.utils import timezone

from .models import Festivo

MESES = [
    'Enero', 'Febrero', 'Marzo', 'Abril', 'Mayo', 'Junio',
    'Julio', 'Agosto', 'Septiembre', 'Octubre', 'Noviembre', 'Diciembre',
]
DIAS_SEMANA = ['Lunes', 'Martes', 'Miércoles', 'Jueves', 'Viernes', 'Sábado', 'Domingo']

ANIO_MIN = 2000
ANIO_MAX = 2100


def _entero(valor, por_defecto, minimo, maximo):
    """Convierte un parámetro de la URL a entero dentro de un rango; si no es válido usa el valor por defecto."""
    try:
        numero = int(valor)
    except (TypeError, ValueError):
        return por_defecto
    return numero if minimo <= numero <= maximo else por_defecto


def contexto_mes(request):
    """Datos para dibujar el calendario del mes pedido en ?anio=&mes= (por defecto, el mes actual)."""
    hoy = timezone.localdate()
    anio = _entero(request.GET.get('anio'), hoy.year, ANIO_MIN, ANIO_MAX)
    mes = _entero(request.GET.get('mes'), hoy.month, 1, 12)

    # Semanas completas de lunes a domingo, incluyendo días del mes anterior y siguiente.
    semanas = [
        [
            {
                'fecha': fecha,
                'otro_mes': fecha.month != mes,
                'es_hoy': fecha == hoy,
                'fin_de_semana': fecha.weekday() >= 5,
            }
            for fecha in semana
        ]
        for semana in calendar.Calendar(firstweekday=calendar.MONDAY).monthdatescalendar(anio, mes)
    ]

    # Festivos visibles en el mes (incluye los días del mes anterior y siguiente que se ven).
    primer_dia, ultimo_dia = semanas[0][0]['fecha'], semanas[-1][-1]['fecha']
    festivos = dict(Festivo.objects.filter(fecha__range=(primer_dia, ultimo_dia)).values_list('fecha', 'nombre'))
    for semana in semanas:
        for dia in semana:
            dia['festivo'] = festivos.get(dia['fecha'])

    anterior = (anio, mes - 1) if mes > 1 else (anio - 1, 12)
    siguiente = (anio, mes + 1) if mes < 12 else (anio + 1, 1)

    return {
        'anio': anio,
        'mes': mes,
        'nombre_mes': MESES[mes - 1],
        'meses': list(enumerate(MESES, start=1)),
        'anios': range(ANIO_MIN, ANIO_MAX + 1),
        'dias_semana': DIAS_SEMANA,
        'semanas': semanas,
        'hoy': hoy,
        'anterior': anterior if anterior[0] >= ANIO_MIN else None,
        'siguiente': siguiente if siguiente[0] <= ANIO_MAX else None,
    }
