from django.contrib import admin

from .models import AsignacionTurno, TipoTurno


@admin.register(TipoTurno)
class TipoTurnoAdmin(admin.ModelAdmin):
    list_display = ['abreviatura', 'nombre', 'hora_inicio', 'hora_fin', 'activo']
    list_filter = ['activo']


@admin.register(AsignacionTurno)
class AsignacionTurnoAdmin(admin.ModelAdmin):
    list_display = ['fecha', 'funcionario', 'tipo_turno', 'asignado_por']
    list_filter = ['tipo_turno', 'funcionario__area']
    date_hierarchy = 'fecha'
    search_fields = ['funcionario__nombres', 'funcionario__apellidos', 'funcionario__numero_documento']
