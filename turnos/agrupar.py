from collections import defaultdict

from .models import TipoTurno


def turnos_por_dia(asignaciones):
    """Agrupa turnos asignados por fecha: {fecha: [turnos…]}.

    En cada día quedan en el orden de los tipos de turno (por hora de inicio) y luego por apellido.
    Las asignaciones deben venir con select_related('funcionario', 'tipo_turno').
    """
    orden_tipos = {pk: i for i, pk in enumerate(TipoTurno.objects.values_list('pk', flat=True))}
    por_fecha = defaultdict(list)
    for asignacion in asignaciones:
        por_fecha[asignacion.fecha].append(asignacion)
    for lista in por_fecha.values():
        lista.sort(key=lambda a: (orden_tipos[a.tipo_turno_id], a.funcionario.apellidos, a.funcionario.nombres))
    return por_fecha
