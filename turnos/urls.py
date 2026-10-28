from django.urls import path

from . import views

app_name = 'turnos'

urlpatterns = [
    path('', views.cuadro, name='cuadro'),
    path('dia/<int:anio>/<int:mes>/<int:dia>/', views.dia, name='dia'),
    path('varios-dias/', views.varios, name='varios'),
    path('subir-excel/', views.subir_excel, name='subir_excel'),
    path('subir-excel/cargar/', views.cargar_excel, name='cargar_excel'),
    path('borrar-agenda/', views.borrar_agenda, name='borrar_agenda'),
    path('tipos/', views.tipos, name='tipos'),
    path('tipos/nuevo/', views.tipo_crear, name='tipo_crear'),
    path('tipos/<int:pk>/editar/', views.tipo_editar, name='tipo_editar'),
    path('tipos/<int:pk>/estado/', views.tipo_estado, name='tipo_estado'),
]
