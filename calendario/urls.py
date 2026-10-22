from django.urls import path

from . import views

app_name = 'calendario'

urlpatterns = [
    path('', views.calendario_mes, name='mes'),
    path('dia/<int:anio>/<int:mes>/<int:dia>/', views.dia, name='dia'),
    path('festivos/', views.festivos, name='festivos'),
]
