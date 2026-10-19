from collections import defaultdict

from .models import TipoTurno


def agrupar_por_franja(asignaciones):
    """Agrupa turnos asignados por fecha y franja: {fecha: {'manana': [...], 'tarde': [...], 'otros': [...]}}.

    Dentro de cada franja quedan en el orden de los tipos de turno y luego por apellido.
    Las asignaciones deben venir con select_related('funcionario', 'tipo_turno').
    """
    orden_tipos = {pk: i for i, pk in enumerate(TipoTurno.objects.values_list('pk', flat=True))}
    por_fecha = defaultdict(lambda: {'manana': [], 'tarde': [], 'otros': []})
    for asignacion in asignaciones:
        por_fecha[asignacion.fecha][asignacion.tipo_turno.franja].append(asignacion)
    for franjas in por_fecha.values():
        for lista in franjas.values():
            lista.sort(key=lambda a: (orden_tipos[a.tipo_turno_id], a.funcionario.apellidos, a.funcionario.nombres))
    return por_fecha
