from funcionarios.permisos import es_administrador

from .models import SolicitudHoraExtra


def pendientes(request):
    """Cantidad de solicitudes de hora extra que le toca revisar a este administrador, para el contador del menú."""
    if not es_administrador(request.user):
        return {}
    pendientes = SolicitudHoraExtra.visibles_para(request.user).filter(estado=SolicitudHoraExtra.Estado.PENDIENTE)
    return {'solicitudes_pendientes': pendientes.count()}
