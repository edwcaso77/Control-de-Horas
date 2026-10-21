import datetime

from django.conf import settings
from django.db import models
from django.db.models import Q

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
    # Lo que pidió el funcionario. No cambia aunque el administrador corrija el tiempo.
    hora_inicio_solicitada = models.TimeField('desde (solicitado)', null=True, blank=True)
    hora_fin_solicitada = models.TimeField('hasta (solicitado)', null=True, blank=True)
    # El tiempo vigente: al crearse es el solicitado; el administrador lo puede editar al revisar (tiempo aprobado).
    hora_inicio = models.TimeField('desde')
    hora_fin = models.TimeField('hasta', help_text='Si termina después de medianoche, escriba la hora tal cual (por ejemplo 01:00).')
    motivo = models.TextField('motivo', max_length=500)
    # Administrador que autoriza: solo él ve y revisa la solicitud.
    administrador = models.ForeignKey(
        Funcionario, on_delete=models.PROTECT, null=True, blank=True,
        related_name='horas_extra_por_autorizar', verbose_name='administrador que autoriza',
        limit_choices_to={'es_administrador': True},
    )
    # Solicitudes antiguas: el nombre de quien autorizó escrito a mano (las ven todos los administradores).
    autorizado_por = models.CharField('autorizado por (texto)', max_length=120, blank=True)
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

    def save(self, *args, **kwargs):
        # Al crearse, lo solicitado queda guardado tal como lo pidió el funcionario.
        if self.hora_inicio_solicitada is None:
            self.hora_inicio_solicitada = self.hora_inicio
        if self.hora_fin_solicitada is None:
            self.hora_fin_solicitada = self.hora_fin
        super().save(*args, **kwargs)

    @staticmethod
    def _horas_entre(inicio, fin):
        """Si «hasta» es menor o igual a «desde», termina al día siguiente."""
        desde = datetime.datetime.combine(datetime.date.min, inicio)
        hasta = datetime.datetime.combine(datetime.date.min, fin)
        if hasta <= desde:
            hasta += datetime.timedelta(days=1)
        return (hasta - desde).total_seconds() / 3600

    @property
    def horas(self):
        """Horas vigentes (las aprobadas, si el administrador las corrigió)."""
        return self._horas_entre(self.hora_inicio, self.hora_fin)

    @property
    def horas_texto(self):
        return f'{formato_horas(round(self.horas, 2))} h'

    @property
    def horario(self):
        return f'{self.hora_inicio:%H:%M} – {self.hora_fin:%H:%M}'

    @property
    def horas_solicitadas(self):
        return self._horas_entre(self.hora_inicio_solicitada or self.hora_inicio, self.hora_fin_solicitada or self.hora_fin)

    @property
    def horas_solicitadas_texto(self):
        return f'{formato_horas(round(self.horas_solicitadas, 2))} h'

    @property
    def horario_solicitado(self):
        inicio = self.hora_inicio_solicitada or self.hora_inicio
        fin = self.hora_fin_solicitada or self.hora_fin
        return f'{inicio:%H:%M} – {fin:%H:%M}'

    @property
    def tiempo_modificado(self):
        """True si el administrador cambió el tiempo respecto a lo solicitado."""
        return self.horario != self.horario_solicitado

    @property
    def pendiente(self):
        return self.estado == self.Estado.PENDIENTE

    @property
    def autorizador(self):
        """Nombre de quien autoriza, para mostrar."""
        return self.administrador.nombre_completo if self.administrador else self.autorizado_por

    @classmethod
    def visibles_para(cls, usuario):
        """Solicitudes que puede ver y revisar un administrador: las dirigidas a él y las antiguas sin administrador.
        El superusuario ve todas."""
        if usuario.is_superuser:
            return cls.objects.all()
        return cls.objects.filter(Q(administrador__usuario=usuario) | Q(administrador__isnull=True))
