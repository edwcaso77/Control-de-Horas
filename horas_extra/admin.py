from django.contrib import admin

from .models import SolicitudHoraExtra


@admin.register(SolicitudHoraExtra)
class SolicitudHoraExtraAdmin(admin.ModelAdmin):
    list_display = ['fecha', 'funcionario', 'hora_inicio', 'hora_fin', 'estado', 'revisado_por']
    list_filter = ['estado', 'funcionario__area']
    date_hierarchy = 'fecha'
    search_fields = ['funcionario__nombres', 'funcionario__apellidos', 'funcionario__numero_documento']
