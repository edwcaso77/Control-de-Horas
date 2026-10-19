# Control de Horas

Sistema web para gestionar el cuadro de turnos y calcular las horas extra para la nómina.

## Estado actual

- Inicio de sesión con número de documento y contraseña.
- Menú lateral con opciones según el rol (administrador o funcionario).
- Calendario mensual con selector de mes y año.
- Registro de funcionarios: crear, editar, activar y desactivar, con su usuario y contraseña.
- Listas de cargos y áreas que maneja el administrador.
- Cuadro de turno (administrador): tipos de turno con horario y color, y asignación
  de turnos por día, por semana o en varios días seleccionados desde el calendario,
  con filtro por área.

## Requisitos

- Python 3.12 o superior

## Instalación local

```bash
py -m venv .venv
.venv\Scripts\python.exe -m pip install -r requirements.txt
.venv\Scripts\python.exe manage.py migrate
.venv\Scripts\python.exe manage.py crear_administrador
.venv\Scripts\python.exe manage.py runserver
```

El comando `crear_administrador` se usa una sola vez para crear el primer administrador.
Después, los demás funcionarios se registran desde el sistema.

Luego abrir http://localhost:8000

## Pruebas

```bash
.venv\Scripts\python.exe manage.py test
```

## Producción (variables del archivo .env)

Definir estas variables de entorno:

- `DJANGO_SECRET_KEY`: clave secreta propia y larga.
- `DJANGO_DEBUG=False`
- `DJANGO_ALLOWED_HOSTS`: dirección del sitio, por ejemplo `edwcaso77.pythonanywhere.com`.

## Publicar en internet

Ver [DESPLIEGUE.md](DESPLIEGUE.md) para subirlo a PythonAnywhere.
