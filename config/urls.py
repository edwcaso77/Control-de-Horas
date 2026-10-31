from django.contrib import admin
from django.contrib.auth import views as auth_views
from django.urls import include, path

from funcionarios.forms import IngresoAdminForm, IngresoForm

admin.site.login_form = IngresoAdminForm

urlpatterns = [
    path('admin/', admin.site.urls),
    path(
        'ingresar/',
        auth_views.LoginView.as_view(authentication_form=IngresoForm, redirect_authenticated_user=True),
        name='ingresar',
    ),
    path('salir/', auth_views.LogoutView.as_view(), name='salir'),
    path('funcionarios/', include('funcionarios.urls')),
    path('cuadro-de-turno/', include('turnos.urls')),
    path('horas-extra/', include('horas_extra.urls')),
    path('reportes/', include('reportes.urls')),
    path('', include('calendario.urls')),
]
