from functools import wraps

from django.contrib.auth.decorators import login_required
from django.core.exceptions import PermissionDenied


def es_administrador(usuario):
    if not usuario.is_authenticated:
        return False
    if usuario.is_superuser:
        return True
    funcionario = getattr(usuario, 'funcionario', None)
    return bool(funcionario and funcionario.es_administrador)


def administrador_requerido(vista):
    """Exige haber iniciado sesión y ser administrador."""

    @wraps(vista)
    @login_required
    def envoltura(request, *args, **kwargs):
        if not es_administrador(request.user):
            raise PermissionDenied
        return vista(request, *args, **kwargs)

    return envoltura
