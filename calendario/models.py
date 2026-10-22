from django.db import models

from . import festivos_colombia


class Festivo(models.Model):
    """Día festivo. Los de Colombia se cargan automáticamente; el administrador puede agregar o quitar."""

    fecha = models.DateField('fecha', unique=True)
    nombre = models.CharField('nombre', max_length=80)

    class Meta:
        ordering = ['fecha']
        verbose_name = 'festivo'
        verbose_name_plural = 'festivos'

    def __str__(self):
        return f'{self.fecha:%d/%m/%Y} · {self.nombre}'

    @classmethod
    def cargar_colombia(cls, anio):
        """Crea los festivos de Colombia del año que falten. Devuelve cuántos se crearon."""
        creados = 0
        for fecha, nombre in festivos_colombia.festivos(anio):
            _, nuevo = cls.objects.get_or_create(fecha=fecha, defaults={'nombre': nombre})
            creados += nuevo
        return creados
