from funcionarios.permisos import es_administrador

from .models import SolicitudHoraExtra


def pendientes(request):
    """Cantidad de solicitudes de hora extra por revisar, para el contador del menú del administrador."""
    if not es_administrador(request.user):
        return {}
    return {'solicitudes_pendientes': SolicitudHoraExtra.objects.filter(estado=SolicitudHoraExtra.Estado.PENDIENTE).count()}
