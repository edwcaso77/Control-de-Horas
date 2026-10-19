import datetime

from django.test import TestCase
from django.urls import reverse

from funcionarios.models import Area
from funcionarios.tests import crear_funcionario

from .models import AsignacionTurno, TipoTurno


class TipoTurnoTests(TestCase):
    def test_duracion_y_horario(self):
        noche = TipoTurno(nombre='Noche', abreviatura='N', hora_inicio=datetime.time(19), hora_fin=datetime.time(7))
        self.assertEqual(noche.duracion_horas, 12)
        self.assertEqual(noche.horario, '19:00 – 07:00')
        descanso = TipoTurno(nombre='Descanso', abreviatura='D')
        self.assertEqual(descanso.duracion_horas, 0)
        self.assertEqual(descanso.horario, 'Sin horario')

    def test_color_de_texto_legible(self):
        self.assertEqual(TipoTurno(color='#1F2A5C').color_texto, '#FFFFFF')
        self.assertEqual(TipoTurno(color='#6EC6D9').color_texto, '#333333')


class CuadroTurnoTests(TestCase):
    def setUp(self):
        self.admin = crear_funcionario('1000', es_administrador=True)
        self.client.force_login(self.admin.usuario)
        self.urgencias = Area.objects.get(nombre='Urgencias')
        self.otra_area = Area.objects.create(nombre='Hospitalización')
        self.ana = crear_funcionario('2000', nombres='Ana')
        self.luis = crear_funcionario('3000', nombres='Luis', area=self.otra_area.pk)
        self.manana = TipoTurno.objects.create(
            nombre='Mañana', abreviatura='M', hora_inicio=datetime.time(7), hora_fin=datetime.time(13), color='#6EC6D9',
        )
        self.noche = TipoTurno.objects.create(
            nombre='Noche', abreviatura='N', hora_inicio=datetime.time(19), hora_fin=datetime.time(7), color='#1F2A5C',
        )
        self.fecha = datetime.date(2026, 10, 21)  # miércoles

    def _url_dia(self, fecha=None):
        fecha = fecha or self.fecha
        return reverse('turnos:dia', args=[fecha.year, fecha.month, fecha.day])

    def test_crear_tipo_de_turno(self):
        respuesta = self.client.post(reverse('turnos:tipo_crear'), {
            'nombre': 'Tarde', 'abreviatura': 't', 'hora_inicio': '13:00', 'hora_fin': '19:00', 'color': '#66b32e',
        })
        self.assertRedirects(respuesta, reverse('turnos:tipos'))
        tarde = TipoTurno.objects.get(nombre='Tarde')
        self.assertEqual((tarde.abreviatura, tarde.color), ('T', '#66B32E'))

    def test_tipo_con_una_sola_hora_es_invalido(self):
        respuesta = self.client.post(reverse('turnos:tipo_crear'), {
            'nombre': 'Raro', 'abreviatura': 'R', 'hora_inicio': '13:00', 'hora_fin': '', 'color': '#000000',
        })
        self.assertEqual(respuesta.status_code, 200)
        self.assertFalse(TipoTurno.objects.filter(nombre='Raro').exists())

    def test_asignar_turnos_de_un_dia(self):
        respuesta = self.client.post(self._url_dia(), {
            f'turno_{self.ana.pk}': self.manana.pk,
            f'turno_{self.luis.pk}': self.noche.pk,
            'alcance': 'dia',
        })
        self.assertRedirects(respuesta, f"{reverse('turnos:cuadro')}?anio=2026&mes=10")
        self.assertEqual(AsignacionTurno.objects.get(funcionario=self.ana, fecha=self.fecha).tipo_turno, self.manana)
        self.assertEqual(AsignacionTurno.objects.get(funcionario=self.luis, fecha=self.fecha).tipo_turno, self.noche)
        self.assertEqual(AsignacionTurno.objects.count(), 2)

    def test_aplicar_a_toda_la_semana(self):
        self.client.post(self._url_dia(), {f'turno_{self.ana.pk}': self.noche.pk, 'alcance': 'semana'})
        fechas = list(AsignacionTurno.objects.filter(funcionario=self.ana).values_list('fecha', flat=True))
        self.assertEqual(fechas, [datetime.date(2026, 10, d) for d in range(19, 26)])

    def test_cambiar_y_quitar_turno(self):
        self.client.post(self._url_dia(), {f'turno_{self.ana.pk}': self.manana.pk, 'alcance': 'dia'})
        self.client.post(self._url_dia(), {f'turno_{self.ana.pk}': self.noche.pk, 'alcance': 'dia'})
        self.assertEqual(AsignacionTurno.objects.get(funcionario=self.ana).tipo_turno, self.noche)
        self.client.post(self._url_dia(), {f'turno_{self.ana.pk}': '', 'alcance': 'dia'})
        self.assertFalse(AsignacionTurno.objects.filter(funcionario=self.ana).exists())

    def test_filtro_por_area_solo_toca_esa_area(self):
        AsignacionTurno.objects.create(funcionario=self.luis, fecha=self.fecha, tipo_turno=self.noche)
        respuesta = self.client.get(self._url_dia(), {'area': self.urgencias.pk})
        nombres = [fila['funcionario'].nombres for fila in respuesta.context['filas']]
        self.assertNotIn('Luis', nombres)

        # Guardar Urgencias sin turno no borra el turno de Luis, que es de otra área.
        self.client.post(self._url_dia(), {'area': self.urgencias.pk, f'turno_{self.ana.pk}': '', 'alcance': 'dia'})
        self.assertTrue(AsignacionTurno.objects.filter(funcionario=self.luis).exists())

    def test_turno_inexistente_se_ignora(self):
        self.client.post(self._url_dia(), {f'turno_{self.ana.pk}': '99999', 'alcance': 'dia'})
        self.assertFalse(AsignacionTurno.objects.exists())

    def test_resumen_del_mes(self):
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=self.fecha, tipo_turno=self.manana)
        AsignacionTurno.objects.create(funcionario=self.admin, fecha=self.fecha, tipo_turno=self.manana)
        AsignacionTurno.objects.create(funcionario=self.luis, fecha=self.fecha, tipo_turno=self.noche)
        respuesta = self.client.get(reverse('turnos:cuadro'), {'anio': 2026, 'mes': 10})
        dia = next(d for s in respuesta.context['semanas'] for d in s if d['fecha'] == self.fecha)
        self.assertEqual([(i['tipo'].abreviatura, i['total']) for i in dia['resumen']], [('M', 2), ('N', 1)])
        self.assertContains(respuesta, 'Cuadro de turno')

    def test_funcionario_inactivo_no_aparece(self):
        self.ana.usuario.is_active = False
        self.ana.usuario.save()
        filas = self.client.get(self._url_dia()).context['filas']
        self.assertNotIn(self.ana, [f['funcionario'] for f in filas])

    def test_fecha_invalida(self):
        self.assertEqual(self.client.get('/cuadro-de-turno/dia/2026/2/30/').status_code, 404)

    def test_solo_administrador(self):
        self.client.force_login(self.ana.usuario)
        self.assertEqual(self.client.get(reverse('turnos:cuadro')).status_code, 403)
        self.assertEqual(self.client.get(self._url_dia()).status_code, 403)
        self.assertEqual(self.client.get(reverse('turnos:tipos')).status_code, 403)

    def test_menu_lateral_muestra_cuadro_de_turno_solo_al_admin(self):
        self.assertContains(self.client.get(reverse('calendario:mes')), 'Cuadro de turno')
        self.client.force_login(self.ana.usuario)
        self.assertNotContains(self.client.get(reverse('calendario:mes')), 'Cuadro de turno')
