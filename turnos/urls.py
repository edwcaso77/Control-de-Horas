from django.urls import path

from . import views

app_name = 'turnos'

urlpatterns = [
    path('', views.cuadro, name='cuadro'),
    path('dia/<int:anio>/<int:mes>/<int:dia>/', views.dia, name='dia'),
    path('tipos/', views.tipos, name='tipos'),
    path('tipos/nuevo/', views.tipo_crear, name='tipo_crear'),
    path('tipos/<int:pk>/editar/', views.tipo_editar, name='tipo_editar'),
    path('tipos/<int:pk>/estado/', views.tipo_estado, name='tipo_estado'),
]
