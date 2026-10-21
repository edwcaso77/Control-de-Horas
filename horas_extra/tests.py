import datetime
from unittest import mock

from django.test import TestCase
from django.urls import reverse

from funcionarios.tests import crear_funcionario
from turnos.models import AsignacionTurno, TipoTurno

from .models import SolicitudHoraExtra

HOY = datetime.date(2026, 10, 21)


@mock.patch('horas_extra.views.timezone.localdate', return_value=HOY)
@mock.patch('calendario.views.timezone.localdate', return_value=HOY)
class SolicitudHoraExtraTests(TestCase):
    def setUp(self):
        self.admin = crear_funcionario('1000', es_administrador=True)
        self.ana = crear_funcionario('2000', nombres='Ana')
        self.luis = crear_funcionario('3000', nombres='Luis')
        self.c1 = TipoTurno.objects.create(nombre='Ala A', abreviatura='C1', hora_inicio=datetime.time(5), hora_fin=datetime.time(14))
        self.turno_ana = AsignacionTurno.objects.create(funcionario=self.ana, fecha=datetime.date(2026, 10, 20), tipo_turno=self.c1)
        self.turno_luis = AsignacionTurno.objects.create(funcionario=self.luis, fecha=datetime.date(2026, 10, 20), tipo_turno=self.c1)

    def _solicitar(self, turno=None, **datos):
        turno = turno or self.turno_ana
        valores = {'hora_inicio': '14:00', 'hora_fin': '16:30', 'motivo': 'Paciente crítico', 'administrador': self.admin.pk}
        valores.update(datos)
        return self.client.post(reverse('horas_extra:solicitar', args=[turno.pk]), valores)

    def test_funcionario_solicita_desde_su_turno(self, *_):
        self.client.force_login(self.ana.usuario)
        formulario = self.client.get(reverse('horas_extra:solicitar', args=[self.turno_ana.pk]))
        self.assertEqual(formulario.context['form'].initial['hora_inicio'], datetime.time(14))  # fin del turno C1

        respuesta = self._solicitar()
        self.assertRedirects(respuesta, reverse('calendario:dia', args=[2026, 10, 20]))
        solicitud = SolicitudHoraExtra.objects.get()
        self.assertEqual((solicitud.funcionario, solicitud.fecha, solicitud.turno), (self.ana, self.turno_ana.fecha, self.turno_ana))
        self.assertEqual((solicitud.estado, solicitud.horas, solicitud.horas_texto), ('pendiente', 2.5, '2.5 h'))

    def test_el_dia_muestra_boton_y_estado_de_la_solicitud(self, *_):
        self.client.force_login(self.ana.usuario)
        dia = self.client.get(reverse('calendario:dia', args=[2026, 10, 20]))
        self.assertContains(dia, reverse('horas_extra:solicitar', args=[self.turno_ana.pk]))
        self._solicitar()
        dia = self.client.get(reverse('calendario:dia', args=[2026, 10, 20]))
        self.assertContains(dia, 'Mis solicitudes de hora extra')
        self.assertContains(dia, 'Pendiente')

    def test_no_puede_solicitar_sobre_turno_ajeno(self, *_):
        self.client.force_login(self.ana.usuario)
        self.assertEqual(self._solicitar(turno=self.turno_luis).status_code, 404)
        self.assertFalse(SolicitudHoraExtra.objects.exists())

    def test_no_puede_solicitar_un_dia_futuro(self, *_):
        futuro = AsignacionTurno.objects.create(funcionario=self.ana, fecha=datetime.date(2026, 10, 25), tipo_turno=self.c1)
        self.client.force_login(self.ana.usuario)
        self._solicitar(turno=futuro)
        self.assertFalse(SolicitudHoraExtra.objects.exists())
        dia = self.client.get(reverse('calendario:dia', args=[2026, 10, 25]))
        self.assertNotContains(dia, reverse('horas_extra:solicitar', args=[futuro.pk]))

    def test_datos_obligatorios_y_horario_valido(self, *_):
        self.client.force_login(self.ana.usuario)
        respuesta = self._solicitar(motivo='', administrador='')
        self.assertEqual(set(respuesta.context['form'].errors), {'motivo', 'administrador'})
        self._solicitar(hora_inicio='14:00', hora_fin='14:00')
        self.assertFalse(SolicitudHoraExtra.objects.exists())

    def test_hora_extra_que_pasa_la_medianoche(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar(hora_inicio='22:00', hora_fin='01:00')
        self.assertEqual(SolicitudHoraExtra.objects.get().horas, 3)

    def test_cancelar_solo_si_esta_pendiente(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar()
        solicitud = SolicitudHoraExtra.objects.get()
        solicitud.estado = SolicitudHoraExtra.Estado.APROBADA
        solicitud.save()
        self.client.post(reverse('horas_extra:cancelar', args=[solicitud.pk]))
        self.assertTrue(SolicitudHoraExtra.objects.exists())

        solicitud.estado = SolicitudHoraExtra.Estado.PENDIENTE
        solicitud.save()
        self.client.post(reverse('horas_extra:cancelar', args=[solicitud.pk]))
        self.assertFalse(SolicitudHoraExtra.objects.exists())

    def test_no_puede_cancelar_solicitud_ajena(self, *_):
        self.client.force_login(self.luis.usuario)
        self._solicitar(turno=self.turno_luis)
        self.client.force_login(self.ana.usuario)
        self.assertEqual(self.client.post(reverse('horas_extra:cancelar', args=[SolicitudHoraExtra.objects.get().pk])).status_code, 404)

    def test_administrador_ve_menu_con_pendientes_y_listado(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar()
        self.client.force_login(self.admin.usuario)
        calendario = self.client.get(reverse('calendario:mes'))
        self.assertContains(calendario, 'Horas extra')
        self.assertContains(calendario, 'title="Solicitudes pendientes">1</span>')
        listado = self.client.get(reverse('horas_extra:lista'))
        self.assertEqual(len(listado.context['solicitudes']), 1)
        self.assertEqual(len(self.client.get(reverse('horas_extra:lista'), {'estado': 'aprobadas'}).context['solicitudes']), 0)

    def test_administrador_corrige_y_aprueba(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar()
        solicitud = SolicitudHoraExtra.objects.get()
        self.client.force_login(self.admin.usuario)
        respuesta = self.client.post(reverse('horas_extra:revisar', args=[solicitud.pk]), {
            'hora_inicio': '14:00', 'hora_fin': '16:00', 'comentario': 'Se ajusta a 2 horas', 'decision': 'aprobada',
        })
        self.assertRedirects(respuesta, reverse('horas_extra:lista'))
        solicitud.refresh_from_db()
        self.assertEqual((solicitud.estado, solicitud.horas, solicitud.revisado_por), ('aprobada', 2, self.admin.usuario))
        self.assertIsNotNone(solicitud.revisado_en)

        # La funcionaria ve el resultado y el comentario en su día.
        self.client.force_login(self.ana.usuario)
        dia = self.client.get(reverse('calendario:dia', args=[2026, 10, 20]))
        self.assertContains(dia, 'Aprobada')
        self.assertContains(dia, 'Se ajusta a 2 horas')

    def test_administrador_rechaza(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar()
        solicitud = SolicitudHoraExtra.objects.get()
        self.client.force_login(self.admin.usuario)
        self.client.post(reverse('horas_extra:revisar', args=[solicitud.pk]), {
            'hora_inicio': '14:00', 'hora_fin': '16:30', 'comentario': 'No fue autorizada', 'decision': 'rechazada',
        })
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'rechazada')

    def test_decision_invalida(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar()
        self.client.force_login(self.admin.usuario)
        respuesta = self.client.post(reverse('horas_extra:revisar', args=[SolicitudHoraExtra.objects.get().pk]), {
            'hora_inicio': '14:00', 'hora_fin': '16:30', 'decision': 'otra',
        })
        self.assertEqual(respuesta.status_code, 404)

    def test_funcionario_no_entra_a_la_administracion_de_horas_extra(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar()
        self.assertEqual(self.client.get(reverse('horas_extra:lista')).status_code, 403)
        self.assertEqual(self.client.get(reverse('horas_extra:revisar', args=[SolicitudHoraExtra.objects.get().pk])).status_code, 403)
        self.assertNotContains(self.client.get(reverse('calendario:mes')), 'Horas extra')

    def test_lo_solicitado_se_conserva_al_editar_el_tiempo_aprobado(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar()  # 14:00 – 16:30 (2.5 h)
        solicitud = SolicitudHoraExtra.objects.get()
        self.assertEqual((solicitud.horario_solicitado, solicitud.tiempo_modificado), ('14:00 – 16:30', False))

        self.client.force_login(self.admin.usuario)
        revision = self.client.get(reverse('horas_extra:revisar', args=[solicitud.pk]))
        self.assertContains(revision, 'Tiempo aprobado')
        self.assertContains(revision, '14:00 – 16:30')
        self.client.post(reverse('horas_extra:revisar', args=[solicitud.pk]), {
            'hora_inicio': '14:00', 'hora_fin': '15:30', 'decision': 'aprobada',
        })
        solicitud.refresh_from_db()
        self.assertEqual((solicitud.horario_solicitado, solicitud.horas_solicitadas), ('14:00 – 16:30', 2.5))
        self.assertEqual((solicitud.horario, solicitud.horas, solicitud.tiempo_modificado), ('14:00 – 15:30', 1.5, True))

        listado = self.client.get(reverse('horas_extra:lista'), {'estado': 'aprobadas'})
        self.assertContains(listado, '2.5 h')
        self.assertContains(listado, '1.5 h')
        self.assertContains(listado, 'editado')

        # Ya aprobada, se puede volver a editar el tiempo aprobado.
        self.assertContains(self.client.get(reverse('horas_extra:revisar', args=[solicitud.pk])), 'Guardar tiempo aprobado')
        self.client.post(reverse('horas_extra:revisar', args=[solicitud.pk]), {
            'hora_inicio': '14:00', 'hora_fin': '16:00', 'decision': 'aprobada',
        })
        solicitud.refresh_from_db()
        self.assertEqual((solicitud.horas, solicitud.horas_solicitadas), (2, 2.5))

        self.client.force_login(self.ana.usuario)
        dia = self.client.get(reverse('calendario:dia', args=[2026, 10, 20]))
        self.assertContains(dia, '2.5 h')
        self.assertContains(dia, '<strong>2 h</strong>')


@mock.patch('horas_extra.views.timezone.localdate', return_value=HOY)
@mock.patch('calendario.views.timezone.localdate', return_value=HOY)
class AdministradorQueAutorizaTests(TestCase):
    """Cada solicitud va a un administrador elegido de la lista, y solo él la ve."""

    def setUp(self):
        self.jefe1 = crear_funcionario('1000', nombres='Marta', es_administrador=True)
        self.jefe2 = crear_funcionario('1001', nombres='Pedro', es_administrador=True)
        self.ana = crear_funcionario('2000', nombres='Ana')
        c1 = TipoTurno.objects.create(nombre='Ala A', abreviatura='C1', hora_inicio=datetime.time(5), hora_fin=datetime.time(14))
        self.turno = AsignacionTurno.objects.create(funcionario=self.ana, fecha=datetime.date(2026, 10, 20), tipo_turno=c1)
        self.turno_jefe1 = AsignacionTurno.objects.create(funcionario=self.jefe1, fecha=datetime.date(2026, 10, 20), tipo_turno=c1)

    def _solicitar(self, para, turno=None):
        return self.client.post(reverse('horas_extra:solicitar', args=[(turno or self.turno).pk]), {
            'hora_inicio': '14:00', 'hora_fin': '16:00', 'motivo': 'Relevo tarde', 'administrador': para.pk,
        })

    def test_el_formulario_lista_los_administradores(self, *_):
        self.client.force_login(self.ana.usuario)
        form = self.client.get(reverse('horas_extra:solicitar', args=[self.turno.pk])).context['form']
        self.assertEqual(set(form.fields['administrador'].queryset), {self.jefe1, self.jefe2})

    def test_un_administrador_no_se_autoriza_a_si_mismo(self, *_):
        self.client.force_login(self.jefe1.usuario)
        form = self.client.get(reverse('horas_extra:solicitar', args=[self.turno_jefe1.pk])).context['form']
        self.assertEqual(list(form.fields['administrador'].queryset), [self.jefe2])
        self._solicitar(para=self.jefe1, turno=self.turno_jefe1)
        self.assertFalse(SolicitudHoraExtra.objects.exists())

    def test_no_se_puede_dirigir_a_alguien_que_no_es_administrador(self, *_):
        otro = crear_funcionario('3000', nombres='Luis')
        self.client.force_login(self.ana.usuario)
        self._solicitar(para=otro)
        self.assertFalse(SolicitudHoraExtra.objects.exists())

    def test_cada_administrador_ve_solo_lo_suyo(self, *_):
        self.client.force_login(self.ana.usuario)
        self._solicitar(para=self.jefe1)
        solicitud = SolicitudHoraExtra.objects.get()
        self.assertEqual((solicitud.administrador, solicitud.autorizador), (self.jefe1, 'Marta Pérez'))

        self.client.force_login(self.jefe1.usuario)
        self.assertEqual(list(self.client.get(reverse('horas_extra:lista')).context['solicitudes']), [solicitud])
        self.assertContains(self.client.get(reverse('calendario:mes')), 'title="Solicitudes pendientes">1</span>')
        self.assertEqual(self.client.get(reverse('horas_extra:revisar', args=[solicitud.pk])).status_code, 200)

        self.client.force_login(self.jefe2.usuario)
        self.assertEqual(list(self.client.get(reverse('horas_extra:lista'), {'estado': 'todas'}).context['solicitudes']), [])
        self.assertNotContains(self.client.get(reverse('calendario:mes')), 'Solicitudes pendientes')
        self.assertEqual(self.client.get(reverse('horas_extra:revisar', args=[solicitud.pk])).status_code, 404)
        respuesta = self.client.post(reverse('horas_extra:revisar', args=[solicitud.pk]), {
            'hora_inicio': '14:00', 'hora_fin': '16:00', 'decision': 'aprobada',
        })
        self.assertEqual(respuesta.status_code, 404)
        solicitud.refresh_from_db()
        self.assertEqual(solicitud.estado, 'pendiente')

    def test_solicitudes_antiguas_las_ven_todos_los_administradores(self, *_):
        antigua = SolicitudHoraExtra.objects.create(
            funcionario=self.ana, fecha=self.turno.fecha, turno=self.turno, hora_inicio=datetime.time(14),
            hora_fin=datetime.time(15), motivo='Antes del cambio', autorizado_por='Jefe escrito a mano',
        )
        for jefe in (self.jefe1, self.jefe2):
            self.client.force_login(jefe.usuario)
            self.assertIn(antigua, self.client.get(reverse('horas_extra:lista')).context['solicitudes'])
        self.assertEqual(antigua.autorizador, 'Jefe escrito a mano')
