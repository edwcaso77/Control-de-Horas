import datetime
import io

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse

from .forms import FuncionarioForm
from .models import Area, Cargo, Funcionario

Usuario = get_user_model()
CLAVE = 'Clave-de-prueba-2026'


def crear_funcionario(documento, es_administrador=False, **extra):
    datos = {
        'tipo_documento': 'CC',
        'numero_documento': documento,
        'nombres': 'Ana',
        'apellidos': 'Pérez',
        'cargo': Cargo.objects.get_or_create(nombre='Auxiliar')[0].pk,
        'area': Area.objects.get_or_create(nombre='Urgencias')[0].pk,
        'es_administrador': es_administrador,
        'password1': CLAVE,
        'password2': CLAVE,
        **extra,
    }
    form = FuncionarioForm(datos)
    assert form.is_valid(), form.errors
    return form.save()


class RegistroFuncionarioTests(TestCase):
    def setUp(self):
        self.admin = crear_funcionario('1000', es_administrador=True)
        self.client.force_login(self.admin.usuario)
        self.cargo = Cargo.objects.get(nombre='Auxiliar')
        self.area = Area.objects.get(nombre='Urgencias')

    def _datos(self, **cambios):
        datos = {
            'tipo_documento': 'CC',
            'numero_documento': '2000',
            'nombres': 'Luis',
            'apellidos': 'Gómez',
            'cargo': self.cargo.pk,
            'area': self.area.pk,
            'correo': 'luis@example.com',
            'telefono': '3001234567',
            'fecha_ingreso': '2026-02-01',
            'password1': CLAVE,
            'password2': CLAVE,
        }
        datos.update(cambios)
        return datos

    def test_crear_funcionario_crea_su_usuario_y_puede_ingresar(self):
        respuesta = self.client.post(reverse('funcionarios:crear'), self._datos())
        self.assertRedirects(respuesta, reverse('funcionarios:lista'))

        funcionario = Funcionario.objects.get(numero_documento='2000')
        self.assertEqual(funcionario.usuario.username, '2000')
        self.assertEqual(funcionario.fecha_ingreso, datetime.date(2026, 2, 1))
        self.assertFalse(funcionario.es_administrador)

        self.client.logout()
        respuesta = self.client.post(reverse('ingresar'), {'username': '2000', 'password': CLAVE})
        self.assertRedirects(respuesta, reverse('calendario:mes'))

    def test_documento_repetido(self):
        respuesta = self.client.post(reverse('funcionarios:crear'), self._datos(numero_documento='1000'))
        self.assertEqual(respuesta.status_code, 200)
        self.assertTrue(respuesta.context['form'].errors['numero_documento'])

    def test_contrasenas_distintas(self):
        respuesta = self.client.post(reverse('funcionarios:crear'), self._datos(password2='otra-cosa-2026'))
        self.assertIn('password2', respuesta.context['form'].errors)
        self.assertFalse(Funcionario.objects.filter(numero_documento='2000').exists())

    def test_contrasena_obligatoria_al_crear(self):
        respuesta = self.client.post(reverse('funcionarios:crear'), self._datos(password1='', password2=''))
        self.assertIn('password1', respuesta.context['form'].errors)

    def test_editar_sin_contrasena_conserva_la_actual(self):
        otro = crear_funcionario('3000')
        respuesta = self.client.post(
            reverse('funcionarios:editar', args=[otro.pk]),
            self._datos(numero_documento='3001', password1='', password2=''),
        )
        self.assertRedirects(respuesta, reverse('funcionarios:lista'))
        otro.refresh_from_db()
        otro.usuario.refresh_from_db()
        self.assertEqual(otro.usuario.username, '3001')
        self.assertTrue(otro.usuario.check_password(CLAVE))

    def test_desactivar_impide_ingresar(self):
        otro = crear_funcionario('4000')
        self.client.post(reverse('funcionarios:estado', args=[otro.pk]))
        otro.usuario.refresh_from_db()
        self.assertFalse(otro.usuario.is_active)

        self.client.logout()
        respuesta = self.client.post(reverse('ingresar'), {'username': '4000', 'password': CLAVE})
        self.assertEqual(respuesta.status_code, 200)

    def test_no_puede_desactivarse_a_si_mismo(self):
        self.client.post(reverse('funcionarios:estado', args=[self.admin.pk]))
        self.admin.usuario.refresh_from_db()
        self.assertTrue(self.admin.usuario.is_active)

    def test_no_puede_quitarse_el_rol_de_administrador(self):
        respuesta = self.client.post(
            reverse('funcionarios:editar', args=[self.admin.pk]),
            self._datos(numero_documento='1000', password1='', password2=''),
        )
        self.assertIn('es_administrador', respuesta.context['form'].errors)

    def test_redireccion_externa_ignorada(self):
        otro = crear_funcionario('5000')
        respuesta = self.client.post(
            reverse('funcionarios:estado', args=[otro.pk]), {'siguiente': 'https://otro-sitio.com/'},
        )
        self.assertRedirects(respuesta, reverse('funcionarios:lista'))

    def test_filtros_del_listado(self):
        crear_funcionario('6000', nombres='Marta')
        inactivo = crear_funcionario('7000', nombres='Pedro')
        inactivo.usuario.is_active = False
        inactivo.usuario.save()

        activos = self.client.get(reverse('funcionarios:lista')).context['funcionarios']
        self.assertNotIn(inactivo, activos)
        inactivos = self.client.get(reverse('funcionarios:lista'), {'estado': 'inactivos'}).context['funcionarios']
        self.assertEqual(list(inactivos), [inactivo])
        busqueda = self.client.get(reverse('funcionarios:lista'), {'q': 'marta'}).context['funcionarios']
        self.assertEqual([f.numero_documento for f in busqueda], ['6000'])


class PermisosTests(TestCase):
    def test_funcionario_comun_no_entra_a_administracion(self):
        comun = crear_funcionario('8000')
        self.client.force_login(comun.usuario)
        self.assertEqual(self.client.get(reverse('funcionarios:lista')).status_code, 403)
        self.assertEqual(self.client.get(reverse('funcionarios:catalogo', args=['cargos'])).status_code, 403)
        self.assertEqual(self.client.get(reverse('calendario:mes')).status_code, 200)

    def test_sin_sesion_redirige_al_ingreso(self):
        respuesta = self.client.get(reverse('funcionarios:lista'))
        self.assertRedirects(respuesta, f"{reverse('ingresar')}?next={reverse('funcionarios:lista')}")


class CatalogoTests(TestCase):
    def setUp(self):
        self.client.force_login(crear_funcionario('1000', es_administrador=True).usuario)

    def test_agregar_y_nombre_repetido(self):
        url = reverse('funcionarios:catalogo', args=['areas'])
        self.client.post(url, {'nombre': '  Consulta   externa '})
        self.assertTrue(Area.objects.filter(nombre='Consulta externa').exists())
        respuesta = self.client.post(url, {'nombre': 'consulta externa'})
        self.assertTrue(respuesta.context['form'].errors)

    def test_cargo_inactivo_no_se_ofrece_en_formulario(self):
        Cargo.objects.create(nombre='Retirado', activo=False)
        form = FuncionarioForm()
        self.assertNotIn('Retirado', [c.nombre for c in form.fields['cargo'].queryset])

    def test_tipo_de_catalogo_desconocido(self):
        self.assertEqual(self.client.get('/funcionarios/configuracion/otros/').status_code, 404)


class ComandoFuncionariosPruebaTests(TestCase):
    def test_crear_y_borrar(self):
        import tempfile
        from django.core.management import call_command
        from django.test import override_settings
        from pathlib import Path

        Area.objects.create(nombre='Sala de Hemodialisis')
        with tempfile.TemporaryDirectory() as carpeta, override_settings(BASE_DIR=Path(carpeta)):
            call_command('funcionarios_prueba', stdout=io.StringIO())
            prueba = Funcionario.objects.filter(numero_documento__startswith='9000000')
            self.assertEqual(prueba.count(), 15)
            self.assertEqual(prueba.filter(cargo__nombre='Auxiliar de Enfermeria').count(), 7)
            self.assertEqual(prueba.filter(cargo__nombre='Enfermero Profesional').count(), 5)
            self.assertEqual(prueba.filter(cargo__nombre='Médico').count(), 3)
            self.assertTrue((Path(carpeta) / 'credenciales_prueba.txt').exists())

            call_command('funcionarios_prueba', stdout=io.StringIO())  # no duplica
            self.assertEqual(prueba.count(), 15)

            call_command('funcionarios_prueba', '--borrar', stdout=io.StringIO())
            self.assertEqual(prueba.count(), 0)
            self.assertFalse(Usuario.objects.filter(username__startswith='9000000').exists())
