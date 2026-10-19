import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse


class CalendarioMesTests(TestCase):
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
        with mock.patch('calendario.views.timezone.localdate', return_value=hoy):
            contexto = self._get(anio='abc', mes='13').context
        self.assertEqual((contexto['anio'], contexto['mes']), (2026, 10))

    def test_resalta_el_dia_de_hoy(self):
        hoy = datetime.date(2026, 10, 16)
        with mock.patch('calendario.views.timezone.localdate', return_value=hoy):
            semanas = self._get().context['semanas']
        marcados = [d['fecha'] for s in semanas for d in s if d['es_hoy']]
        self.assertEqual(marcados, [hoy])
