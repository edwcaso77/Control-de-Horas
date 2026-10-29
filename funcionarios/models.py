from django.conf import settings
from django.db import models


class Catalogo(models.Model):
    """Lista que maneja el administrador (cargos, áreas). Se desactiva en lugar de borrarse."""

    nombre = models.CharField('nombre', max_length=100, unique=True)
    activo = models.BooleanField('activo', default=True)

    class Meta:
        abstract = True
        ordering = ['nombre']

    def __str__(self):
        return self.nombre


class Area(Catalogo):
    class Meta(Catalogo.Meta):
        verbose_name = 'área'
        verbose_name_plural = 'áreas'


class Cargo(Catalogo):
    class Meta(Catalogo.Meta):
        verbose_name = 'cargo'
        verbose_name_plural = 'cargos'


class Funcionario(models.Model):
    class TipoDocumento(models.TextChoices):
        CC = 'CC', 'Cédula de ciudadanía'
        CE = 'CE', 'Cédula de extranjería'
        TI = 'TI', 'Tarjeta de identidad'
        PA = 'PA', 'Pasaporte'
        PPT = 'PPT', 'Permiso por protección temporal'

    # El usuario para entrar al sistema es el número de documento.
    # El estado activo/inactivo se guarda en usuario.is_active, así un funcionario inactivo no puede entrar.
    usuario = models.OneToOneField(
        settings.AUTH_USER_MODEL, on_delete=models.PROTECT, related_name='funcionario', verbose_name='usuario',
    )
    tipo_documento = models.CharField(
        'tipo de documento', max_length=3, choices=TipoDocumento.choices, default=TipoDocumento.CC,
    )
    numero_documento = models.CharField('número de documento', max_length=20, unique=True)
    nombres = models.CharField('nombres', max_length=100)
    apellidos = models.CharField('apellidos', max_length=100)
    cargo = models.ForeignKey(Cargo, on_delete=models.PROTECT, null=True, blank=True, verbose_name='cargo')
    area = models.ForeignKey(Area, on_delete=models.PROTECT, null=True, blank=True, verbose_name='área')
    correo = models.EmailField('correo', blank=True)
    telefono = models.CharField('teléfono', max_length=20, blank=True)
    fecha_ingreso = models.DateField('fecha de ingreso', null=True, blank=True)
    fecha_retiro = models.DateField(
        'fecha de retiro', null=True, blank=True,
        help_text='Último día que trabaja. Desde el día siguiente ya no se programa en el cuadro de turno.',
    )
    es_administrador = models.BooleanField('es administrador', default=False)

    class Meta:
        ordering = ['apellidos', 'nombres']
        verbose_name = 'funcionario'
        verbose_name_plural = 'funcionarios'

    def __str__(self):
        return self.nombre_completo

    @property
    def nombre_completo(self):
        return f'{self.nombres} {self.apellidos}'

    @property
    def nombre_corto(self):
        """Primer nombre y primer apellido, para mostrar en espacios pequeños como el calendario."""
        return f'{self.nombres.split()[0]} {self.apellidos.split()[0]}'

    @property
    def activo(self):
        return self.usuario.is_active
