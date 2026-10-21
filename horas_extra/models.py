import datetime

from django.conf import settings
from django.db import models

from funcionarios.models import Funcionario
from turnos.models import AsignacionTurno, formato_horas


class SolicitudHoraExtra(models.Model):
    """Tiempo adicional que un funcionario trabajó en su turno y reporta después para la nómina."""

    class Estado(models.TextChoices):
        PENDIENTE = 'pendiente', 'Pendiente'
        APROBADA = 'aprobada', 'Aprobada'
        RECHAZADA = 'rechazada', 'Rechazada'

    funcionario = models.ForeignKey(
        Funcionario, on_delete=models.PROTECT, related_name='solicitudes_hora_extra', verbose_name='funcionario',
    )
    fecha = models.DateField('fecha')
    turno = models.ForeignKey(
        AsignacionTurno, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='solicitudes_hora_extra', verbose_name='turno',
    )
    hora_inicio = models.TimeField('desde')
    hora_fin = models.TimeField('hasta', help_text='Si termina después de medianoche, escriba la hora tal cual (por ejemplo 01:00).')
    motivo = models.TextField('motivo', max_length=500)
    autorizado_por = models.CharField('autorizado por', max_length=120, help_text='Nombre de quien autorizó la hora extra.')
    estado = models.CharField('estado', max_length=10, choices=Estado.choices, default=Estado.PENDIENTE)
    comentario = models.TextField('comentario del administrador', max_length=500, blank=True)
    revisado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='revisado por',
    )
    revisado_en = models.DateTimeField('revisado en', null=True, blank=True)
    creado = models.DateTimeField('solicitado en', auto_now_add=True)

    class Meta:
        ordering = ['-fecha', '-creado']
        verbose_name = 'solicitud de hora extra'
        verbose_name_plural = 'solicitudes de hora extra'

    def __str__(self):
        return f'{self.funcionario} · {self.fecha:%d/%m/%Y} · {self.horario}'

    @property
    def horas(self):
        """Horas solicitadas. Si «hasta» es menor o igual a «desde», termina al día siguiente."""
        inicio = datetime.datetime.combine(datetime.date.min, self.hora_inicio)
        fin = datetime.datetime.combine(datetime.date.min, self.hora_fin)
        if fin <= inicio:
            fin += datetime.timedelta(days=1)
        return (fin - inicio).total_seconds() / 3600

    @property
    def horas_texto(self):
        return f'{formato_horas(round(self.horas, 2))} h'

    @property
    def horario(self):
        return f'{self.hora_inicio:%H:%M} – {self.hora_fin:%H:%M}'

    @property
    def pendiente(self):
        return self.estado == self.Estado.PENDIENTE
