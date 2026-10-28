import datetime
import io

from django.test import TestCase
from django.urls import reverse
from openpyxl import load_workbook

from funcionarios.models import Area
from funcionarios.tests import crear_funcionario
from horas_extra.models import SolicitudHoraExtra
from turnos.models import AsignacionTurno, TipoTurno

from .clasificacion import DIURNA, DIURNA_FESTIVA, NOCTURNA, NOCTURNA_FESTIVA, clasificar, intervalo
from .conteo import conteo_semana, semana_de

# Semana del lunes 12 (festivo, Día de la Raza) al domingo 18 de octubre de 2026.
LUNES = datetime.date(2026, 10, 12)
MARTES = datetime.date(2026, 10, 13)
SABADO = datetime.date(2026, 10, 17)
DOMINGO = datetime.date(2026, 10, 18)
FESTIVOS = {LUNES}


def hora(h, m=0):
    return datetime.time(h, m)


class ClasificacionTests(TestCase):
    def _clasificar(self, fecha, inicio, fin):
        horas = clasificar(*intervalo(fecha, inicio, fin), FESTIVOS)
        return {categoria: valor for categoria, valor in horas.items() if valor}

    def test_corta_en_las_siete_de_la_noche(self):
        self.assertEqual(self._clasificar(MARTES, hora(18), hora(21)), {DIURNA: 1, NOCTURNA: 2})

    def test_corta_en_las_seis_de_la_manana(self):
        self.assertEqual(self._clasificar(MARTES, hora(5), hora(7, 30)), {NOCTURNA: 1, DIURNA: 1.5})

    def test_festivo_y_domingo(self):
        self.assertEqual(self._clasificar(LUNES, hora(8), hora(10)), {DIURNA_FESTIVA: 2})
        self.assertEqual(self._clasificar(DOMINGO, hora(18), hora(20)), {DIURNA_FESTIVA: 1, NOCTURNA_FESTIVA: 1})

    def test_pasa_la_medianoche_hacia_el_domingo(self):
        self.assertEqual(self._clasificar(SABADO, hora(22), hora(2)), {NOCTURNA: 2, NOCTURNA_FESTIVA: 2})

    def test_semana_de_lunes_a_domingo(self):
        self.assertEqual(semana_de(datetime.date(2026, 10, 15)), (LUNES, DOMINGO))


class ConteoSemanaTests(TestCase):
    def setUp(self):
        self.admin = crear_funcionario('1000', es_administrador=True, nombres='Admin', apellidos='Zuluaga')
        self.ana = crear_funcionario('2000', nombres='Ana', apellidos='Pérez')
        self.noche = TipoTurno.objects.create(nombre='Noche', abreviatura='N', hora_inicio=hora(19), hora_fin=hora(7))
        self.c1 = TipoTurno.objects.create(nombre='Ala A', abreviatura='C1', hora_inicio=hora(5), hora_fin=hora(14))
        self.hc = TipoTurno.objects.create(nombre='Disponibilidad', abreviatura='HC', horas_variables=True)

    def _extra(self, fecha, inicio, fin, estado=SolicitudHoraExtra.Estado.APROBADA):
        return SolicitudHoraExtra.objects.create(
            funcionario=self.ana, fecha=fecha, hora_inicio=inicio, hora_fin=fin, motivo='Paciente crítico', estado=estado,
        )

    def test_turnos_dan_recargo_y_solicitudes_aprobadas_dan_horas_extra(self):
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=MARTES, tipo_turno=self.noche)
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=DOMINGO, tipo_turno=self.c1)
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=SABADO, tipo_turno=self.hc, horas=2)  # sin hora de inicio
        self._extra(MARTES, hora(7), hora(9))
        self._extra(LUNES, hora(18), hora(20))
        self._extra(SABADO, hora(14), hora(16), estado=SolicitudHoraExtra.Estado.PENDIENTE)

        filas, totales, total = conteo_semana(LUNES)

        por_fecha = {fila['fecha']: fila for fila in filas}
        self.assertEqual(set(por_fecha), {LUNES, MARTES, SABADO, DOMINGO})
        self.assertEqual(por_fecha[SABADO]['horas']['total_horas'], 2)  # HC 2h; la solicitud pendiente no cuenta
        self.assertEqual(por_fecha[MARTES]['horas']['total_horas'], 14)  # turno N de 12 h + 2 h extra
        self.assertEqual(por_fecha[LUNES]['horas']['extra_diurna_festiva'], 1)
        self.assertEqual(por_fecha[LUNES]['horas']['extra_nocturna_festiva'], 1)
        self.assertEqual(por_fecha[MARTES]['horas']['recargo_nocturno'], 11)  # 19:00 a 06:00
        self.assertEqual(por_fecha[MARTES]['horas']['extra_diurna'], 2)
        self.assertEqual(por_fecha[MARTES]['actividad'], 'N · Hora extra: Paciente crítico')
        self.assertEqual(por_fecha[DOMINGO]['horas']['recargo_nocturno'], 0)
        self.assertEqual(por_fecha[DOMINGO]['horas']['nocturna_festiva'], 1)  # 05:00 a 06:00
        self.assertEqual(por_fecha[DOMINGO]['horas']['recargo_nocturno_festivo'], 1)
        self.assertEqual(por_fecha[DOMINGO]['horas']['diurna_festivo'], 8)
        self.assertEqual(por_fecha[DOMINGO]['seccion'], 'Urgencias')
        self.assertEqual(totales[self.ana]['recargo_nocturno'], 11)
        self.assertEqual(total, {
            'extra_diurna': 2, 'extra_nocturna': 0, 'extra_diurna_festiva': 1, 'extra_nocturna_festiva': 1,
            'recargo_nocturno': 11, 'diurna_festivo': 8, 'nocturna_festiva': 1, 'recargo_nocturno_festivo': 1,
            'total_horas': 27,
        })

    def test_turno_de_cuatro_bloques(self):
        a1 = TipoTurno.objects.create(
            nombre='A1 (especial)', abreviatura='A1', hora_inicio=hora(5), hora_fin=hora(7),
            hora_inicio_2=hora(10, 30), hora_fin_2=hora(13), hora_inicio_3=hora(16), hora_fin_3=hora(18),
            hora_inicio_4=hora(22), hora_fin_4=hora(0),
        )
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=MARTES, tipo_turno=a1)
        fila = conteo_semana(LUNES)[0][0]
        self.assertEqual(fila['horas']['total_horas'], 8.5)
        self.assertEqual(fila['horas']['recargo_nocturno'], 3)  # 05:00 a 06:00 y 22:00 a 00:00

    def test_filtra_por_seccion(self):
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=MARTES, tipo_turno=self.noche)
        otra = Area.objects.create(nombre='Hospitalización')
        self.assertEqual(len(conteo_semana(LUNES)[0]), 1)
        self.assertEqual(conteo_semana(LUNES, otra)[0], [])

    def test_pantalla_solo_para_administradores(self):
        self.client.force_login(self.ana.usuario)
        self.assertEqual(self.client.get(reverse('reportes:conteo')).status_code, 403)

    def test_pantalla_y_excel(self):
        AsignacionTurno.objects.create(funcionario=self.ana, fecha=MARTES, tipo_turno=self.noche)
        self.client.force_login(self.admin.usuario)

        pagina = self.client.get(reverse('reportes:conteo'), {'semana': '2026-10-15'})
        self.assertEqual(pagina.context['lunes'], LUNES)
        self.assertContains(pagina, 'HORA EXTRA NOCTURNA FESTIVAS')
        self.assertContains(pagina, 'Pérez, Ana')

        archivo = self.client.get(reverse('reportes:conteo_excel'), {'semana': '2026-10-15'})
        self.assertEqual(archivo['Content-Disposition'], 'attachment; filename="conteo_horas_2026-10-12.xlsx"')
        libro = load_workbook(io.BytesIO(archivo.content))
        hoja = libro.active
        self.assertEqual([c.value for c in hoja[4]], [
            'FECHA', 'NOMBRE', 'SECCION', 'ACTIVIDAD', 'HORA EXTRA DIURNAS', 'HORA EXTRA NOCTURNA',
            'HORA EXTRA DIURNA FESTIVAS', 'HORA EXTRA NOCTURNA FESTIVAS', 'RECARGO NOCTURNO', 'DIURNA FESTIVO',
            'NOCTURNAS FESTIVAS', 'RECARGO NOCTURNO FESTIVO', 'TOTAL HORAS',
        ])
        self.assertEqual(hoja['I5'].value, 11)
        self.assertEqual(hoja['M5'].value, 12)
        self.assertEqual(hoja['M6'].value, '=SUM(M5:M5)')

        totales = libro['Total horas']
        self.assertEqual(totales['A4'].value, 'Ana Pérez')
        self.assertEqual(totales['K4'].value, "=SUMIF('Conteo de horas'!$B$5:$B$5,$A4,'Conteo de horas'!M$5:M$5)")
        self.assertEqual(totales['K5'].value, '=SUM(K4:K4)')
