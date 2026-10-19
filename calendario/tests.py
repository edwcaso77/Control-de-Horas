import datetime
from unittest import mock

from django.contrib.auth import get_user_model
from django.test import TestCase
from django.urls import reverse


class CalendarioMesTests(TestCase):
    def setUp(self):
        self.client.force_login(get_user_model().objects.create_user('prueba'))

    def test_exige_iniciar_sesion(self):
        self.client.logout()
        respuesta = self._get()
        self.assertRedirects(respuesta, f"{reverse('ingresar')}?next={reverse('calendario:mes')}")

    def _get(self, **params):
        return self.client.get(reverse('calendario:mes'), params)

    def test_enero_2026_empieza_en_lunes_29_de_diciembre(self):
        respuesta = self._get(anio=2026, mes=1)
        semanas = respuesta.context['semanas']
        self.assertEqual(semanas[0][0]['fecha'], datetime.date(2025, 12, 29))
        self.assertTrue(semanas[0][0]['otro_mes'])
        self.assertEqual(semanas[0][3]['fecha'], datetime.date(2026, 1, 1))
        self.assertEqual(semanas[-1][-1]['fecha'], datetime.date(2026, 2, 1))
        self.assertContains(respuesta, 'Enero')

    def test_fines_de_semana_marcados(self):
        semana = self._get(anio=2026, mes=1).context['semanas'][0]
        self.assertEqual([d['fin_de_semana'] for d in semana], [False] * 5 + [True, True])

    def test_navegacion_cruza_el_anio(self):
        enero = self._get(anio=2026, mes=1).context
        self.assertEqual(enero['anterior'], (2025, 12))
        diciembre = self._get(anio=2026, mes=12).context
        self.assertEqual(diciembre['siguiente'], (2027, 1))

    def test_parametros_invalidos_usan_el_mes_actual(self):
        hoy = datetime.date(2026, 10, 16)
        with mock.patch('calendario.utils.timezone.localdate', return_value=hoy):
            contexto = self._get(anio='abc', mes='13').context
        self.assertEqual((contexto['anio'], contexto['mes']), (2026, 10))

    def test_resalta_el_dia_de_hoy(self):
        hoy = datetime.date(2026, 10, 16)
        with mock.patch('calendario.utils.timezone.localdate', return_value=hoy):
            semanas = self._get().context['semanas']
        marcados = [d['fecha'] for s in semanas for d in s if d['es_hoy']]
        self.assertEqual(marcados, [hoy])


class ConsultaDiaTests(TestCase):
    def setUp(self):
        from funcionarios.models import Area
        from funcionarios.tests import crear_funcionario
        from turnos.models import AsignacionTurno, TipoTurno

        self.admin = crear_funcionario('1000', es_administrador=True)
        self.ana = crear_funcionario('2000', nombres='Ana')
        otra = Area.objects.create(nombre='Hospitalización')
        self.luis = crear_funcionario('3000', nombres='Luis', area=otra.pk)
        self.otra_area = otra
        manana = TipoTurno.objects.create(nombre='Ala A', abreviatura='C1', hora_inicio=datetime.time(5), hora_fin=datetime.time(14))
        tarde = TipoTurno.objects.create(nombre='Ala A (LMV)', abreviatura='X1', hora_inicio=datetime.time(14), hora_fin=datetime.time(23))
        self.fecha = datetime.date(2026, 10, 19)
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=self.fecha, tipo_turno=manana)
        AsignacionTurno.objects.create(funcionario=self.luis, fecha=self.fecha, tipo_turno=tarde)
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=self.fecha + datetime.timedelta(days=1), tipo_turno=tarde)

    def _url(self, fecha=None):
        fecha = fecha or self.fecha
        return reverse('calendario:dia', args=[fecha.year, fecha.month, fecha.day])

    def _nombres(self, respuesta):
        return {clase: [a.funcionario.nombres for a in lista] for _, clase, lista in respuesta.context['franjas']}

    def test_administrador_ve_solo_ese_dia_por_franja(self):
        self.client.force_login(self.admin.usuario)
        respuesta = self.client.get(self._url())
        self.assertEqual(self._nombres(respuesta), {'manana': ['Ana'], 'tarde': ['Luis'], 'otros': []})
        self.assertContains(respuesta, 'Editar turnos de este día')

    def test_filtro_por_area(self):
        self.client.force_login(self.admin.usuario)
        respuesta = self.client.get(self._url(), {'area': self.otra_area.pk})
        self.assertEqual(self._nombres(respuesta), {'manana': [], 'tarde': ['Luis'], 'otros': []})

    def test_funcionario_solo_ve_su_turno(self):
        self.client.force_login(self.ana.usuario)
        respuesta = self.client.get(self._url())
        self.assertEqual(self._nombres(respuesta), {'manana': ['Ana'], 'tarde': [], 'otros': []})
        self.assertNotContains(respuesta, 'Luis')
        self.assertNotContains(respuesta, 'Editar turnos de este día')

    def test_dia_sin_turnos_y_fecha_invalida(self):
        self.client.force_login(self.admin.usuario)
        self.assertContains(self.client.get(self._url(datetime.date(2026, 10, 1))), 'No hay turnos asignados')
        self.assertEqual(self.client.get('/dia/2026/2/30/').status_code, 404)

    def test_exige_sesion_y_calendario_enlaza_los_dias(self):
        self.assertEqual(self.client.get(self._url()).status_code, 302)
        self.client.force_login(self.ana.usuario)
        self.assertContains(self.client.get(reverse('calendario:mes'), {'anio': 2026, 'mes': 10}), self._url())
