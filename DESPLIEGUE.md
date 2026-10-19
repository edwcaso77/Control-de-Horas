# Publicar en PythonAnywhere (plan gratuito)

Guía paso a paso para subir Control de Horas a `https://SU_USUARIO.pythonanywhere.com`.

> En todos los comandos, reemplace **SU_USUARIO** por su nombre de usuario de PythonAnywhere.
> Si su usuario es `edwcaso77`, la ruta del proyecto queda `/home/edwcaso77/Control-de-Horas`.

> ⚠️ El plan gratuito es para **pruebas y demostraciones**. Antes de cargar los datos reales de los
> funcionarios, conviene pasar a un servidor pagado o institucional con copias de seguridad.

---

## 1. Crear la cuenta

1. Entre a https://www.pythonanywhere.com y elija **Pricing & signup → Create a Beginner account** (gratis).
2. El nombre de usuario será parte de la dirección del sitio: `SU_USUARIO.pythonanywhere.com`.
3. Confirme su correo.

## 2. Descargar el proyecto desde GitHub

En PythonAnywhere abra **Consoles → Bash** y ejecute:

```bash
git clone https://github.com/edwcaso77/Control-de-Horas.git
cd Control-de-Horas
```

> **Si el repositorio es privado**, GitHub pedirá usuario y contraseña. La contraseña **no** es la de
> su cuenta: es un *token*. Créelo en GitHub → Settings → Developer settings → Personal access tokens →
> Fine-grained tokens, con acceso de solo lectura (*Contents: Read-only*) al repositorio Control-de-Horas.

## 3. Crear el entorno virtual e instalar dependencias

El proyecto necesita **Python 3.12 o superior**. Use la versión más alta que ofrezca PythonAnywhere
(en el ejemplo, 3.13):

```bash
python3.13 -m venv ~/.virtualenvs/control-horas
source ~/.virtualenvs/control-horas/bin/activate
pip install -r requirements.txt
```

## 4. Configurar el archivo `.env`

Genere una clave secreta y cópiela:

```bash
python -c "from django.core.management.utils import get_random_secret_key; print(get_random_secret_key())"
```

Cree el archivo `.env` a partir del ejemplo y ábralo para editarlo:

```bash
cp .env.ejemplo .env
nano .env
```

Déjelo así (con su clave y su usuario):

```
DJANGO_SECRET_KEY=la-clave-que-copió
DJANGO_DEBUG=False
DJANGO_ALLOWED_HOSTS=SU_USUARIO.pythonanywhere.com
```

Guarde con `Ctrl+O`, `Enter`, y salga con `Ctrl+X`.

## 5. Crear la base de datos, el CSS y su administrador

```bash
python manage.py migrate
python manage.py collectstatic --noinput
python manage.py crear_administrador
```

El último comando le pide su cédula, nombres, apellidos y contraseña.

## 6. Crear la aplicación web

1. Vaya a la pestaña **Web → Add a new web app → Next**.
2. Elija **Manual configuration** (¡no "Django"!) y la **misma versión de Python** del paso 3.
3. Ya creada, en la misma pestaña **Web** complete:

   | Sección | Campo | Valor |
   |---|---|---|
   | Code | Source code | `/home/SU_USUARIO/Control-de-Horas` |
   | Code | Working directory | `/home/SU_USUARIO/Control-de-Horas` |
   | Virtualenv | | `/home/SU_USUARIO/.virtualenvs/control-horas` |
   | Static files | URL `/static/` | Directorio `/home/SU_USUARIO/Control-de-Horas/staticfiles` |
   | Security | Force HTTPS | **Enabled** |

4. En **Code → WSGI configuration file**, haga clic en el archivo, **borre todo su contenido** y péguele esto:

   ```python
   import os
   import sys

   ruta = '/home/SU_USUARIO/Control-de-Horas'
   if ruta not in sys.path:
       sys.path.insert(0, ruta)

   os.environ['DJANGO_SETTINGS_MODULE'] = 'config.settings'

   from django.core.wsgi import get_wsgi_application
   application = get_wsgi_application()
   ```

   Guarde con el botón **Save**.

5. Vuelva a la pestaña **Web** y presione el botón verde **Reload**.
6. Abra `https://SU_USUARIO.pythonanywhere.com` e ingrese con su cédula y contraseña.

---

## Actualizar el sitio con cambios nuevos

Cada vez que haya cambios nuevos en GitHub, en una consola **Bash** de PythonAnywhere:

```bash
cd ~/Control-de-Horas
source ~/.virtualenvs/control-horas/bin/activate
git pull
pip install -r requirements.txt
python manage.py migrate
python manage.py collectstatic --noinput
```

Y luego **Web → Reload**.

## Copia de seguridad de la base de datos

Toda la información está en el archivo `db.sqlite3`. Para descargar una copia:
**Files → Control-de-Horas → db.sqlite3 → Download**. Hágalo con frecuencia.

## Mantener el sitio encendido

El plan gratuito apaga la aplicación si no se renueva. Entre a la pestaña **Web** al menos cada
**3 meses** y presione **"Run until 3 months from today"**. PythonAnywhere le envía un correo antes de
que venza.

## Si algo falla

- **"Something went wrong" o error 500:** revise **Web → Log files → Error log**; el último error
  aparece al final.
- **"Bad Request (400)":** `DJANGO_ALLOWED_HOSTS` en `.env` no coincide con la dirección del sitio.
- **La página se ve sin colores:** falta `collectstatic` o la ruta de *Static files* está mal escrita.
- **"En producción debe definir DJANGO_SECRET_KEY":** el archivo `.env` no existe o la clave está vacía.
