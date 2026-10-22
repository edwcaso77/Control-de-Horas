from django.urls import path

from . import views

app_name = 'reportes'

urlpatterns = [
    path('conteo-de-horas/', views.conteo, name='conteo'),
    path('conteo-de-horas/excel/', views.conteo_excel, name='conteo_excel'),
]
