# Control de Horas

Sistema web para gestionar el cuadro de turnos y calcular las horas extra para la nómina.

## Estado actual

- Calendario mensual con selector de mes y año.

## Requisitos

- Python 3.12 o superior

## Instalación local

```bash
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py runserver
```

Luego abrir http://localhost:8000

## Pruebas

```bash
.venv\Scripts\python.exe manage.py test
```

## Producción

Definir estas variables de entorno:

- `DJANGO_SECRET_KEY`: clave secreta propia y larga.
- `DJANGO_DEBUG=False`
