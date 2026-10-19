from django.urls import path

from . import views

app_name = 'funcionarios'

urlpatterns = [
    path('', views.lista, name='lista'),
    path('nuevo/', views.crear, name='crear'),
    path('<int:pk>/editar/', views.editar, name='editar'),
    path('<int:pk>/estado/', views.cambiar_estado, name='estado'),
    path('configuracion/<slug:tipo>/', views.catalogo, name='catalogo'),
    path('configuracion/<slug:tipo>/<int:pk>/editar/', views.catalogo_editar, name='catalogo_editar'),
    path('configuracion/<slug:tipo>/<int:pk>/estado/', views.catalogo_estado, name='catalogo_estado'),
]
