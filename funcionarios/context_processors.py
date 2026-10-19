from .permisos import es_administrador


def permisos(request):
    return {'es_admin': es_administrador(request.user)}
