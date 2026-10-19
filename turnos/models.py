import datetime

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import RegexValidator
from django.db import models
from django.db.models import F

from funcionarios.models import Funcionario


class TipoTurno(models.Model):
    """Turno que el administrador define: Mañana, Tarde, Noche, Descanso…"""

    nombre = models.CharField('nombre', max_length=50, unique=True)
    abreviatura = models.CharField('abreviatura', max_length=4, unique=True, help_text='Letra corta, por ejemplo M, T, N o D.')
    hora_inicio = models.TimeField('hora de inicio', null=True, blank=True)
    hora_fin = models.TimeField('hora de fin', null=True, blank=True)
    color = models.CharField(
        'color', max_length=7, default='#0770B8',
        validators=[RegexValidator(r'^#[0-9A-Fa-f]{6}$', 'Use un color en formato #RRGGBB.')],
    )
    activo = models.BooleanField('activo', default=True)

    class Meta:
        ordering = [F('hora_inicio').asc(nulls_last=True), 'nombre']
        verbose_name = 'tipo de turno'
        verbose_name_plural = 'tipos de turno'

    def __str__(self):
        return f'{self.abreviatura} · {self.nombre}'

    def clean(self):
        if (self.hora_inicio is None) != (self.hora_fin is None):
            raise ValidationError('Indique la hora de inicio y la de fin, o deje ambas vacías (por ejemplo, para Descanso).')

    @property
    def horario(self):
        if self.hora_inicio is None:
            return 'Sin horario'
        return f'{self.hora_inicio:%H:%M} – {self.hora_fin:%H:%M}'

    @property
    def duracion_horas(self):
        """Horas del turno. Si termina al día siguiente (por ejemplo 19:00 – 07:00) se cuenta hasta el otro día."""
        if self.hora_inicio is None:
            return 0
        inicio = datetime.datetime.combine(datetime.date.min, self.hora_inicio)
        fin = datetime.datetime.combine(datetime.date.min, self.hora_fin)
        if fin <= inicio:
            fin += datetime.timedelta(days=1)
        return (fin - inicio).total_seconds() / 3600

    @property
    def color_texto(self):
        """Blanco o gris oscuro, según qué se lea mejor sobre el color del turno."""
        r, g, b = (int(self.color[i:i + 2], 16) for i in (1, 3, 5))
        luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return '#333333' if luminancia > 0.6 else '#FFFFFF'


class AsignacionTurno(models.Model):
    """Turno de un funcionario en un día del cuadro."""

    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='turnos', verbose_name='funcionario')
    fecha = models.DateField('fecha')
    tipo_turno = models.ForeignKey(TipoTurno, on_delete=models.PROTECT, related_name='asignaciones', verbose_name='turno')
    asignado_por = models.ForeignKey(
        settings.AUTH_USER_MODEL, on_delete=models.SET_NULL, null=True, blank=True,
        related_name='+', verbose_name='asignado por',
    )
    modificado = models.DateTimeField('modificado', auto_now=True)

    class Meta:
        ordering = ['fecha']
        verbose_name = 'turno asignado'
        verbose_name_plural = 'turnos asignados'
        constraints = [
            models.UniqueConstraint(fields=['funcionario', 'fecha'], name='un_turno_por_funcionario_y_dia'),
        ]

    def __str__(self):
        return f'{self.funcionario} · {self.fecha:%d/%m/%Y} · {self.tipo_turno.abreviatura}'
