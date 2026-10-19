import datetime

from django.test import TestCase, override_settings
from django.urls import reverse

from funcionarios.models import Area, Cargo, Funcionario
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

    def test_franja_segun_hora_de_inicio(self):
        self.assertEqual(TipoTurno(hora_inicio=datetime.time(5), hora_fin=datetime.time(14)).franja, 'manana')
        self.assertEqual(TipoTurno(hora_inicio=datetime.time(11, 59), hora_fin=datetime.time(18)).franja, 'manana')
        self.assertEqual(TipoTurno(hora_inicio=datetime.time(12), hora_fin=datetime.time(18)).franja, 'tarde')
        self.assertEqual(TipoTurno(hora_inicio=datetime.time(19), hora_fin=datetime.time(7)).franja, 'tarde')
        self.assertEqual(TipoTurno().franja, 'otros')

    def test_color_de_texto_legible(self):
        self.assertEqual(TipoTurno(color='#1F2A5C').color_texto, '#FFFFFF')
        self.assertEqual(TipoTurno(color='#6EC6D9').color_texto, '#333333')


class DatosCuadroMixin:
    """Administrador, Ana (Urgencias), Luis (Hospitalización) y los turnos Mañana y Noche."""

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


class CuadroTurnoTests(DatosCuadroMixin, TestCase):
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

    def test_nombres_por_franja_en_cada_dia(self):
        descanso = TipoTurno.objects.create(nombre='Descanso', abreviatura='D')
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=self.fecha, tipo_turno=self.manana)
        AsignacionTurno.objects.create(funcionario=self.admin, fecha=self.fecha, tipo_turno=self.manana)
        AsignacionTurno.objects.create(funcionario=self.luis, fecha=self.fecha, tipo_turno=self.noche)
        respuesta = self.client.get(reverse('turnos:cuadro'), {'anio': 2026, 'mes': 10})
        dia = next(d for s in respuesta.context['semanas'] for d in s if d['fecha'] == self.fecha)
        nombres = {franja: [a.funcionario.nombre_corto for a in lista] for franja, lista in dia['franjas'].items()}
        self.assertEqual(nombres, {'manana': ['Ana Pérez', 'Ana Pérez'], 'tarde': ['Luis Pérez'], 'otros': []})
        self.assertContains(respuesta, 'Luis Pérez')
        self.assertContains(respuesta, 'Mañana')

        AsignacionTurno.objects.create(funcionario=self.ana, fecha=self.fecha + datetime.timedelta(days=1), tipo_turno=descanso)
        respuesta = self.client.get(reverse('turnos:cuadro'), {'anio': 2026, 'mes': 10})
        siguiente = next(d for s in respuesta.context['semanas'] for d in s if d['fecha'] == self.fecha + datetime.timedelta(days=1))
        self.assertEqual(len(siguiente['franjas']['otros']), 1)

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


class VariosDiasTests(DatosCuadroMixin, TestCase):
    fechas = [datetime.date(2026, 10, 20), datetime.date(2026, 10, 22), datetime.date(2026, 10, 27)]

    def _url(self):
        return reverse('turnos:varios')

    def _texto(self, fechas=None):
        return ','.join(d.isoformat() for d in (fechas or self.fechas))

    def _celda(self, funcionario, fecha):
        return f'turno_{funcionario.pk}_{fecha.isoformat()}'

    def test_cada_celda_se_asigna_por_separado(self):
        d1, d2, d3 = self.fechas
        respuesta = self.client.post(self._url(), {
            'fechas': self._texto(),
            self._celda(self.ana, d1): self.manana.pk,
            self._celda(self.ana, d2): self.noche.pk,
            self._celda(self.ana, d3): '',
            self._celda(self.luis, d2): self.manana.pk,
        })
        self.assertRedirects(respuesta, f"{reverse('turnos:cuadro')}?anio=2026&mes=10")
        turnos = {(a.funcionario_id, a.fecha): a.tipo_turno for a in AsignacionTurno.objects.all()}
        self.assertEqual(turnos, {
            (self.ana.pk, d1): self.manana,
            (self.ana.pk, d2): self.noche,
            (self.luis.pk, d2): self.manana,
        })

    def test_celda_vacia_quita_y_celda_ausente_conserva(self):
        d1, d2, _ = self.fechas
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=d1, tipo_turno=self.noche)
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=d2, tipo_turno=self.noche)
        self.client.post(self._url(), {'fechas': self._texto(), self._celda(self.ana, d1): ''})
        self.assertEqual(list(AsignacionTurno.objects.values_list('fecha', flat=True)), [d2])

    def test_celda_sin_cambios_no_modifica_quien_asigno(self):
        d1 = self.fechas[0]
        asignacion = AsignacionTurno.objects.create(funcionario=self.ana, fecha=d1, tipo_turno=self.noche)
        self.client.post(self._url(), {'fechas': self._texto(), self._celda(self.ana, d1): self.noche.pk})
        asignacion.refresh_from_db()
        self.assertIsNone(asignacion.asignado_por)

    def test_tabla_muestra_turnos_actuales_por_dia(self):
        AsignacionTurno.objects.create(funcionario=self.luis, fecha=self.fechas[1], tipo_turno=self.manana)
        filas = {f['funcionario'].pk: f for f in self.client.get(self._url(), {'fechas': self._texto()}).context['filas']}
        self.assertEqual([c['turno'] for c in filas[self.luis.pk]['celdas']], [None, self.manana, None])

    def test_filtro_por_cargo(self):
        enfermero = Cargo.objects.create(nombre='Enfermero')
        self.luis.cargo = enfermero
        self.luis.save()
        respuesta = self.client.get(self._url(), {'fechas': self._texto(), 'cargo': enfermero.pk})
        self.assertEqual([f['funcionario'] for f in respuesta.context['filas']], [self.luis])

        # Guardar con el filtro de cargo no toca a funcionarios de otros cargos.
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=self.fechas[0], tipo_turno=self.noche)
        self.client.post(self._url(), {
            'fechas': self._texto(), 'cargo': enfermero.pk, self._celda(self.ana, self.fechas[0]): '',
        })
        self.assertTrue(AsignacionTurno.objects.filter(funcionario=self.ana).exists())

    def test_fechas_invalidas_o_vacias(self):
        respuesta = self.client.get(self._url(), {'fechas': 'hola,2026-13-40'})
        self.assertRedirects(respuesta, reverse('turnos:cuadro'))
        contexto = self.client.get(self._url(), {'fechas': '2026-10-22,basura,2026-10-20,2026-10-22'}).context
        self.assertEqual(contexto['fechas'], [datetime.date(2026, 10, 20), datetime.date(2026, 10, 22)])

    def test_respeta_el_area(self):
        AsignacionTurno.objects.create(funcionario=self.luis, fecha=self.fechas[0], tipo_turno=self.noche)
        self.client.post(self._url(), {
            'fechas': self._texto(), 'area': self.urgencias.pk, self._celda(self.luis, self.fechas[0]): '',
        })
        self.assertTrue(AsignacionTurno.objects.filter(funcionario=self.luis).exists())

    def test_solo_administrador_en_varios_dias(self):
        self.client.force_login(self.ana.usuario)
        self.assertEqual(self.client.get(self._url(), {'fechas': self._texto()}).status_code, 403)

    def test_cuadro_tiene_casillas_y_barra(self):
        respuesta = self.client.get(reverse('turnos:cuadro'), {'anio': 2026, 'mes': 10})
        self.assertContains(respuesta, 'class="casilla-dia" value="2026-10-20"')
        self.assertContains(respuesta, 'id="barra-seleccion"')


class BorrarAgendaTests(DatosCuadroMixin, TestCase):
    def setUp(self):
        super().setUp()
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=self.fecha, tipo_turno=self.manana)
        AsignacionTurno.objects.create(funcionario=self.luis, fecha=self.fecha, tipo_turno=self.noche)

    def test_en_produccion_no_aparece_ni_funciona(self):
        # Las pruebas corren con DEBUG=False, igual que el sitio publicado.
        self.assertNotContains(self.client.get(reverse('turnos:cuadro')), 'Eliminar toda la agenda')
        self.assertEqual(self.client.post(reverse('turnos:borrar_agenda')).status_code, 404)
        self.assertEqual(AsignacionTurno.objects.count(), 2)

    @override_settings(DEBUG=True)
    def test_en_local_borra_solo_los_turnos(self):
        self.assertContains(self.client.get(reverse('turnos:cuadro')), 'Eliminar toda la agenda')
        respuesta = self.client.post(reverse('turnos:borrar_agenda'), {'anio': 2026, 'mes': 10})
        self.assertRedirects(respuesta, f"{reverse('turnos:cuadro')}?anio=2026&mes=10")
        self.assertEqual(AsignacionTurno.objects.count(), 0)
        self.assertEqual(TipoTurno.objects.count(), 2)
        self.assertTrue(Funcionario.objects.filter(pk=self.ana.pk).exists())

    @override_settings(DEBUG=True)
    def test_solo_administrador_y_por_post(self):
        self.assertEqual(self.client.get(reverse('turnos:borrar_agenda')).status_code, 405)
        self.client.force_login(self.ana.usuario)
        self.assertEqual(self.client.post(reverse('turnos:borrar_agenda')).status_code, 403)
        self.assertEqual(AsignacionTurno.objects.count(), 2)
