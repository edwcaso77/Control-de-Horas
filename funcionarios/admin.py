from django.contrib import admin

from .models import Area, Cargo, Funcionario, Ingreso


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


@admin.register(Ingreso)
class IngresoAdmin(admin.ModelAdmin):
    list_display = ['fecha', 'documento', 'usuario', 'resultado', 'ip']
    list_filter = ['resultado']
    search_fields = ['documento', 'ip']

    # El registro es solo de consulta: nadie lo edita ni lo borra desde el administrador.
    def has_add_permission(self, request):
        return False

    def has_change_permission(self, request, obj=None):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
