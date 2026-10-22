from django.urls import path

from . import views

app_name = 'horas_extra'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('solicitar/', views.solicitar_sin_turno, name='solicitar_sin_turno'),
    path('solicitar/<int:turno_id>/', views.solicitar, name='solicitar'),
    path('<int:pk>/cancelar/', views.cancelar, name='cancelar'),
    path('<int:pk>/revisar/', views.revisar, name='revisar'),
]
