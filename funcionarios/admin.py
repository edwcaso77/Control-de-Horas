from django.contrib import admin

from .models import Area, Cargo, Funcionario


@admin.register(Area, Cargo)
class CatalogoAdmin(admin.ModelAdmin):
    list_display = ['nombre', 'activo']
    list_filter = ['activo']
    search_fields = ['nombre']


@admin.register(Funcionario)
class FuncionarioAdmin(admin.ModelAdmin):
    list_display = ['numero_documento', 'apellidos', 'nombres', 'cargo', 'area', 'es_administrador']
    list_filter = ['area', 'cargo', 'es_administrador']
    search_fields = ['numero_documento', 'nombres', 'apellidos']
