"""Registro de los intentos de ingreso y bloqueo temporal después de varias contraseñas equivocadas."""
import datetime
import ipaddress

from django.conf import settings
from django.utils import timezone

from .models import Ingreso


def ip_de(request):
    """Dirección IP de quien hace la petición.

    En el servidor publicado la petición llega a través de un intermediario (proxy), que pone la IP real en
    X-Real-IP o en X-Forwarded-For; en local se usa REMOTE_ADDR.
    """
    candidatas = [
        request.META.get('HTTP_X_REAL_IP', ''),
        request.META.get('HTTP_X_FORWARDED_FOR', '').split(',')[0],
        request.META.get('REMOTE_ADDR', ''),
    ]
    for candidata in candidatas:
        try:
            return str(ipaddress.ip_address(candidata.strip()))
        except ValueError:
            continue
    return None


def anotar(request, documento, resultado, usuario=None):
    Ingreso.objects.create(
        documento=documento[:150],
        usuario=usuario,
        ip=ip_de(request) if request else None,
        navegador=(request.META.get('HTTP_USER_AGENT', '') if request else '')[:255],
        resultado=resultado,
    )


def bloqueado(documento):
    """True si ese documento acumula los intentos fallidos máximos en los últimos minutos de bloqueo.

    Solo cuentan los fallos posteriores al último ingreso exitoso.
    """
    desde = timezone.now() - datetime.timedelta(minutes=settings.MINUTOS_BLOQUEO)
    ultimo_exito = (
        Ingreso.objects.filter(documento=documento, resultado=Ingreso.Resultado.EXITOSO, fecha__gte=desde)
        .values_list('fecha', flat=True).first()
    )
    fallidos = Ingreso.objects.filter(
        documento=documento, resultado=Ingreso.Resultado.FALLIDO, fecha__gte=ultimo_exito or desde,
    )
    return fallidos.count() >= settings.INTENTOS_FALLIDOS_MAXIMOS
