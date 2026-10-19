from django.urls import path

from . import views

app_name = 'calendario'

urlpatterns = [
    path('', views.calendario_mes, name='mes'),
]
