import datetime
from decimal import Decimal

from django.conf import settings
from django.core.exceptions import ValidationError
from django.core.validators import MaxValueValidator, MinValueValidator, RegexValidator
from django.db import models
from django.db.models import F

from funcionarios.models import Funcionario

# Máximo de turnos distintos que un funcionario puede tener el mismo día (por ejemplo C1 + HC).
TURNOS_POR_DIA = 2


def formato_horas(horas):
    """Horas sin ceros de sobra: 3 → «3», 3.0 → «3», 2.5 → «2.5», 10 → «10»."""
    return f'{Decimal(horas).normalize():f}'


def _horas_entre(inicio, fin):
    """Horas entre dos horas del día. Si fin es menor o igual a inicio, se cuenta hasta el día siguiente."""
    desde = datetime.datetime.combine(datetime.date.min, inicio)
    hasta = datetime.datetime.combine(datetime.date.min, fin)
    if hasta <= desde:
        hasta += datetime.timedelta(days=1)
    return (hasta - desde).total_seconds() / 3600


class TipoTurno(models.Model):
    """Turno que el administrador define.

    Hay tres clases:
    - Horario fijo: hora de inicio y de fin (C1 05:00–14:00).
    - Horario partido: además, un segundo bloque (A 08:00–12:00 y 14:00–18:00).
    - Horas variables: sin horario; las horas se escriben al asignarlo, entre un mínimo y un máximo (HC, extramural).
      Si pide hora de inicio, al asignarlo también se escribe a qué hora empieza (extramural).
    Un turno sin horario y sin horas variables sirve para marcas como Descanso.
    """

    nombre = models.CharField('nombre', max_length=50, unique=True)
    abreviatura = models.CharField('abreviatura', max_length=4, unique=True, help_text='Código corto, por ejemplo C1, X2, A o HC.')
    hora_inicio = models.TimeField('hora de inicio', null=True, blank=True)
    hora_fin = models.TimeField('hora de fin', null=True, blank=True)
    hora_inicio_2 = models.TimeField('inicio del segundo bloque', null=True, blank=True)
    hora_fin_2 = models.TimeField('fin del segundo bloque', null=True, blank=True)
    horas_variables = models.BooleanField(
        'horas variables', default=False,
        help_text='No tiene horario fijo: las horas se escriben al asignar el turno.',
    )
    horas_minimas = models.DecimalField(
        'horas mínimas', max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.5')), MaxValueValidator(Decimal('24'))],
    )
    horas_maximas = models.DecimalField(
        'horas máximas', max_digits=4, decimal_places=1, null=True, blank=True,
        validators=[MinValueValidator(Decimal('0.5')), MaxValueValidator(Decimal('24'))],
    )
    pide_hora_inicio = models.BooleanField(
        'pide hora de inicio al asignar', default=False,
        help_text='Para turnos de horas variables cuya hora de inicio cambia cada vez (por ejemplo, extramural).',
    )
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
        errores = {}
        if self.horas_variables:
            if any(h is not None for h in (self.hora_inicio, self.hora_fin, self.hora_inicio_2, self.hora_fin_2)):
                errores['horas_variables'] = 'Un turno de horas variables no lleva horario: deje las horas de inicio y fin vacías.'
            if self.horas_minimas is None or self.horas_maximas is None:
                errores['horas_minimas'] = 'Indique las horas mínimas y máximas que se pueden asignar.'
            elif self.horas_minimas > self.horas_maximas:
                errores['horas_maximas'] = 'Las horas máximas deben ser iguales o mayores que las mínimas.'
        else:
            if (self.hora_inicio is None) != (self.hora_fin is None):
                errores['hora_fin'] = 'Indique la hora de inicio y la de fin, o deje ambas vacías (por ejemplo, para Descanso).'
            if (self.hora_inicio_2 is None) != (self.hora_fin_2 is None):
                errores['hora_fin_2'] = 'Indique el inicio y el fin del segundo bloque, o deje ambos vacíos.'
            elif self.hora_inicio_2 is not None and self.hora_inicio is None:
                errores['hora_inicio_2'] = 'Para usar un segundo bloque, primero indique el horario del primero.'
            # Los rangos de horas y la hora de inicio al asignar solo aplican a turnos de horas variables.
            self.horas_minimas = self.horas_maximas = None
            self.pide_hora_inicio = False
        if errores:
            raise ValidationError(errores)

    @property
    def tiene_segundo_bloque(self):
        return self.hora_inicio_2 is not None

    @property
    def horario(self):
        if self.horas_variables:
            return f'Horas variables ({formato_horas(self.horas_minimas)}–{formato_horas(self.horas_maximas)} h)'
        if self.hora_inicio is None:
            return 'Sin horario'
        texto = f'{self.hora_inicio:%H:%M} – {self.hora_fin:%H:%M}'
        if self.tiene_segundo_bloque:
            texto += f' / {self.hora_inicio_2:%H:%M} – {self.hora_fin_2:%H:%M}'
        return texto

    @property
    def duracion_horas(self):
        """Horas del turno según su horario (suma ambos bloques). Los de horas variables dependen de cada asignación."""
        if self.horas_variables or self.hora_inicio is None:
            return 0
        horas = _horas_entre(self.hora_inicio, self.hora_fin)
        if self.tiene_segundo_bloque:
            horas += _horas_entre(self.hora_inicio_2, self.hora_fin_2)
        return horas

    @property
    def color_texto(self):
        """Blanco o gris oscuro, según qué se lea mejor sobre el color del turno."""
        r, g, b = (int(self.color[i:i + 2], 16) for i in (1, 3, 5))
        luminancia = (0.299 * r + 0.587 * g + 0.114 * b) / 255
        return '#333333' if luminancia > 0.6 else '#FFFFFF'


class AsignacionTurno(models.Model):
    """Turno de un funcionario en un día del cuadro. Puede tener hasta TURNOS_POR_DIA turnos distintos por día."""

    funcionario = models.ForeignKey(Funcionario, on_delete=models.PROTECT, related_name='turnos', verbose_name='funcionario')
    fecha = models.DateField('fecha')
    tipo_turno = models.ForeignKey(TipoTurno, on_delete=models.PROTECT, related_name='asignaciones', verbose_name='turno')
    horas = models.DecimalField(
        'horas', max_digits=4, decimal_places=1, null=True, blank=True,
        help_text='Solo para turnos de horas variables (HC, extramural).',
    )
    hora_inicio = models.TimeField(
        'hora de inicio', null=True, blank=True,
        help_text='Solo para turnos que piden la hora de inicio al asignarlos (extramural).',
    )
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
            models.UniqueConstraint(fields=['funcionario', 'fecha', 'tipo_turno'], name='un_tipo_de_turno_por_funcionario_y_dia'),
        ]

    def __str__(self):
        return f'{self.funcionario} · {self.fecha:%d/%m/%Y} · {self.tipo_turno.abreviatura}'

    @property
    def horas_trabajadas(self):
        if self.tipo_turno.horas_variables:
            return float(self.horas or 0)
        return self.tipo_turno.duracion_horas

    @property
    def etiqueta(self):
        """Abreviatura para las listas: «C1», o «HC 3h» si es de horas variables."""
        if self.tipo_turno.horas_variables and self.horas is not None:
            return f'{self.tipo_turno.abreviatura} {formato_horas(self.horas)}h'
        return self.tipo_turno.abreviatura

    @property
    def hora_fin(self):
        """Hora en que termina, calculada con la hora de inicio y las horas asignadas."""
        if self.hora_inicio is None or self.horas is None:
            return None
        inicio = datetime.datetime.combine(datetime.date.min, self.hora_inicio)
        return (inicio + datetime.timedelta(hours=float(self.horas))).time()

    @property
    def horario(self):
        """Horario de este turno: el del tipo o, si es de horas variables, las horas (y la hora de inicio si la tiene)."""
        if self.tipo_turno.horas_variables:
            if self.horas is None:
                return 'Sin horas'
            if self.hora_inicio is not None:
                return f'{self.hora_inicio:%H:%M} – {self.hora_fin:%H:%M} ({formato_horas(self.horas)} h)'
            return f'{formato_horas(self.horas)} h'
        return self.tipo_turno.horario
