"""Cuadro de turno de un mes en PDF: una fila por funcionario y una columna por día, para imprimir."""
import calendar
import datetime
import io
from collections import defaultdict
from xml.sax.saxutils import escape

from django.conf import settings
from django.utils import timezone
from reportlab.lib import colors
from reportlab.lib.pagesizes import landscape, letter
from reportlab.lib.styles import ParagraphStyle
from reportlab.lib.units import mm
from reportlab.platypus import Image, Paragraph, SimpleDocTemplate, Spacer, Table, TableStyle

from calendario.models import Festivo
from calendario.utils import MESES

from .models import AsignacionTurno, TipoTurno, formato_horas

AZUL = colors.HexColor('#1F2A5C')
GRIS_FESTIVO = colors.HexColor('#E6E8EF')
GRIS_LINEA = colors.HexColor('#9AA0B4')
INICIALES = 'LMMJVSD'  # lunes a domingo

LOGO = settings.BASE_DIR / 'static' / 'img' / 'logo.png'
LOGO_PROPORCION = 764 / 200  # ancho / alto de la imagen del logo
ALTO_LOGO = 14 * mm

ANCHO_NOMBRE = 46 * mm
ANCHO_HORAS = 12 * mm
MARGEN = 8 * mm


def cuadro_pdf(anio, mes, funcionarios, filtros_texto=''):
    """Bytes del PDF del cuadro del mes para los funcionarios dados (en el orden en que vienen)."""
    dias = [datetime.date(anio, mes, d) for d in range(1, calendar.monthrange(anio, mes)[1] + 1)]
    festivos = set(Festivo.objects.filter(fecha__range=(dias[0], dias[-1])).values_list('fecha', flat=True))
    asignaciones = AsignacionTurno.objects.filter(
        funcionario__in=funcionarios, fecha__range=(dias[0], dias[-1]),
    ).select_related('tipo_turno')

    orden_tipos = {pk: i for i, pk in enumerate(TipoTurno.objects.values_list('pk', flat=True))}
    celdas = defaultdict(list)
    for asignacion in asignaciones:
        celdas[(asignacion.funcionario_id, asignacion.fecha)].append(asignacion)
    for lista in celdas.values():
        lista.sort(key=lambda a: orden_tipos[a.tipo_turno_id])

    # Encabezado de dos filas: inicial del día de la semana y número del día.
    filas = [
        ['Funcionario'] + [INICIALES[d.weekday()] for d in dias] + ['Horas'],
        [''] + [str(d.day) for d in dias] + [''],
    ]
    estilo = [
        ('FONT', (0, 0), (-1, -1), 'Helvetica', 6.5),
        ('FONT', (0, 0), (-1, 1), 'Helvetica-Bold', 7),
        ('TEXTCOLOR', (0, 0), (-1, 1), colors.white),
        ('BACKGROUND', (0, 0), (-1, 1), AZUL),
        ('SPAN', (0, 0), (0, 1)),
        ('SPAN', (-1, 0), (-1, 1)),
        ('ALIGN', (1, 0), (-1, -1), 'CENTER'),
        ('VALIGN', (0, 0), (-1, -1), 'MIDDLE'),
        ('GRID', (0, 0), (-1, -1), 0.4, GRIS_LINEA),
        ('LEFTPADDING', (0, 0), (-1, -1), 1.5),
        ('RIGHTPADDING', (0, 0), (-1, -1), 1.5),
        ('TOPPADDING', (0, 0), (-1, -1), 1.5),
        ('BOTTOMPADDING', (0, 0), (-1, -1), 1.5),
        ('LEFTPADDING', (0, 0), (0, -1), 3),
        ('FONT', (-1, 2), (-1, -1), 'Helvetica-Bold', 6.5),
    ]
    # Domingos y festivos sombreados en toda la columna (en el encabezado, un azul más claro).
    for col, dia in enumerate(dias, start=1):
        if dia.weekday() == 6 or dia in festivos:
            estilo.append(('BACKGROUND', (col, 0), (col, 1), colors.HexColor('#3C4A8C')))
            estilo.append(('BACKGROUND', (col, 2), (col, -1), GRIS_FESTIVO))

    nombre = ParagraphStyle('nombre', fontName='Helvetica', fontSize=6.5, leading=7.5)
    usados = {}
    for fila_n, funcionario in enumerate(funcionarios, start=2):
        fila = [Paragraph(escape(f'{funcionario.apellidos}, {funcionario.nombres}'), nombre)]
        total = 0.0
        for col, dia in enumerate(dias, start=1):
            turnos = celdas[(funcionario.pk, dia)]
            fila.append('\n'.join(a.tipo_turno.abreviatura for a in turnos))
            total += sum(a.horas_trabajadas for a in turnos)
            for a in turnos:
                usados[a.tipo_turno_id] = a.tipo_turno
            if len(turnos) == 1:
                tipo = turnos[0].tipo_turno
                estilo.append(('BACKGROUND', (col, fila_n), (col, fila_n), colors.HexColor(tipo.color)))
                estilo.append(('TEXTCOLOR', (col, fila_n), (col, fila_n), colors.HexColor(tipo.color_texto)))
            elif len(turnos) > 1:
                estilo.append(('FONT', (col, fila_n), (col, fila_n), 'Helvetica', 5))
        fila.append(formato_horas(total) if total else '')
        filas.append(fila)

    if not funcionarios:
        filas.append(['No hay funcionarios activos con este filtro.'] + [''] * (len(dias) + 1))
        estilo.append(('SPAN', (0, 2), (-1, 2)))

    ancho_pagina = landscape(letter)[0] - 2 * MARGEN
    ancho_dia = (ancho_pagina - ANCHO_NOMBRE - ANCHO_HORAS) / len(dias)
    tabla = Table(
        filas, colWidths=[ANCHO_NOMBRE] + [ancho_dia] * len(dias) + [ANCHO_HORAS], repeatRows=2,
    )
    tabla.setStyle(TableStyle(estilo))

    titulo = ParagraphStyle('titulo', fontName='Helvetica-Bold', fontSize=13, textColor=AZUL, spaceAfter=2)
    texto = ParagraphStyle('texto', fontName='Helvetica', fontSize=7.5, textColor=colors.HexColor('#444444'))
    # Encabezado: logo de la empresa a la izquierda; título y filtros a la derecha.
    encabezado = Table(
        [[
            Image(str(LOGO), width=ALTO_LOGO * LOGO_PROPORCION, height=ALTO_LOGO),
            [
                Paragraph(f'Cuadro de turno · {MESES[mes - 1]} {anio}', titulo),
                Paragraph(
                    (f'{escape(filtros_texto)} · ' if filtros_texto else 'Todas las áreas y cargos · ')
                    + f'{len(funcionarios)} funcionario{"s" if len(funcionarios) != 1 else ""} · '
                    f'Generado el {timezone.localtime():%d/%m/%Y %H:%M}. Columnas sombreadas: domingos y festivos.',
                    texto,
                ),
            ],
        ]],
        colWidths=[ALTO_LOGO * LOGO_PROPORCION + 6 * mm, None],
        style=[('VALIGN', (0, 0), (-1, -1), 'MIDDLE'), ('LEFTPADDING', (0, 0), (0, 0), 0)],
        hAlign='LEFT',
    )
    contenido = [encabezado, Spacer(1, 3 * mm), tabla]
    if usados:
        orden = sorted(usados.values(), key=lambda t: orden_tipos[t.pk])
        convenciones = ' · '.join(f'<b>{escape(t.abreviatura)}</b> {escape(t.nombre)} ({escape(t.horario)})' for t in orden)
        contenido += [Spacer(1, 3 * mm), Paragraph(f'Convenciones: {convenciones}', texto)]

    salida = io.BytesIO()
    documento = SimpleDocTemplate(
        salida, pagesize=landscape(letter), leftMargin=MARGEN, rightMargin=MARGEN, topMargin=MARGEN,
        bottomMargin=MARGEN, title=f'Cuadro de turno {MESES[mes - 1]} {anio}', author='Control de Horas',
    )
    documento.build(contenido, onFirstPage=_pie, onLaterPages=_pie)
    return salida.getvalue()


def _pie(lienzo, documento):
    lienzo.saveState()
    lienzo.setFont('Helvetica', 7)
    lienzo.setFillColor(colors.HexColor('#777777'))
    lienzo.drawRightString(documento.pagesize[0] - MARGEN, MARGEN / 2, f'Página {documento.page}')
    lienzo.drawString(MARGEN, MARGEN / 2, 'Ures Medical Center IPS S.A.S · Control de Horas')
    lienzo.restoreState()
