import datetime
from collections import defaultdict
from decimal import Decimal, InvalidOperation
from urllib.parse import urlencode

from django.conf import settings
from django.contrib import messages
from django.db import transaction
from django.db.models import Q
from django.http import Http404
from django.shortcuts import get_object_or_404, redirect, render
from django.urls import reverse
from django.utils import timezone
from django.views.decorators.http import require_POST

from calendario.models import Festivo
from calendario.utils import ANIO_MAX, ANIO_MIN, MESES, _entero, contexto_mes
from funcionarios.models import Area, Cargo, Funcionario
from funcionarios.permisos import administrador_requerido

from .forms import TipoTurnoForm
from .agrupar import turnos_por_dia
from .importar import ErrorExcel, fechas_de, leer_excel
from .models import TURNOS_POR_DIA, AsignacionTurno, TipoTurno, formato_horas
from . import programar as rotacion


def _area_elegida(datos):
    area = datos.get('area', '')
    return Area.objects.filter(pk=area).first() if area.isdigit() else None


def _cargo_elegido(datos):
    cargo = datos.get('cargo', '')
    return Cargo.objects.filter(pk=cargo).first() if cargo.isdigit() else None


def _funcionarios_activos(area, cargo=None):
    funcionarios = Funcionario.objects.filter(usuario__is_active=True).select_related('cargo', 'area')
    if area:
        funcionarios = funcionarios.filter(area=area)
    if cargo:
        funcionarios = funcionarios.filter(cargo=cargo)
    return funcionarios


@administrador_requerido
def cuadro(request):
    """Calendario del mes en modo edición: cada día muestra quién tiene turno y cuál."""
    contexto = contexto_mes(request)
    area = _area_elegida(request.GET)

    dias = [dia for semana in contexto['semanas'] for dia in semana]
    asignaciones = (
        AsignacionTurno.objects
        .filter(fecha__range=(dias[0]['fecha'], dias[-1]['fecha']), funcionario__usuario__is_active=True)
        .filter(**({'funcionario__area': area} if area else {}))
        .select_related('funcionario', 'tipo_turno')
    )
    por_dia = turnos_por_dia(asignaciones)
    for dia in dias:
        dia['turnos'] = por_dia[dia['fecha']]

    contexto.update({
        'areas': Area.objects.filter(activo=True),
        'area': area,
        'parametros_extra': f'&area={area.pk}' if area else '',
        'tipos_activos': TipoTurno.objects.filter(activo=True),
        # Herramientas de prueba: solo en el computador de desarrollo, nunca en el sitio publicado.
        'modo_local': settings.DEBUG,
        'total_turnos': AsignacionTurno.objects.count() if settings.DEBUG else 0,
    })
    return render(request, 'turnos/cuadro.html', contexto)


@require_POST
@administrador_requerido
def borrar_agenda(request):
    """Elimina todos los turnos asignados. Solo existe en local (DEBUG=True), para hacer pruebas."""
    if not settings.DEBUG:
        raise Http404
    borrados, _ = AsignacionTurno.objects.all().delete()
    messages.success(request, f'Agenda eliminada: {borrados} turno{"s" if borrados != 1 else ""} borrado{"s" if borrados != 1 else ""}.')
    parametros = {k: v for k in ('anio', 'mes', 'area') if (v := request.POST.get(k, '')).isdigit()}
    return redirect(f"{reverse('turnos:cuadro')}?{urlencode(parametros)}" if parametros else reverse('turnos:cuadro'))


MAX_DIAS_SELECCIONADOS = 62


def _leer_celda(post, clave, tipos_por_id, errores, descripcion):
    """Lee los turnos de una celda del formulario: «clave_1» (principal), «clave_2» (adicional),
    para los turnos de horas variables «horas_clave_N» y, si piden hora de inicio, «inicio_clave_N».

    Devuelve [(tipo, horas, hora_inicio), …] sin repetir tipos, o None si la celda no vino en el formulario
    o tiene datos inválidos (en ese caso no se cambia nada de esa celda y se anota el error).
    """
    valores = [post.get(f'{clave}_{n}') for n in range(1, TURNOS_POR_DIA + 1)]
    if all(valor is None for valor in valores):
        return None
    elegidos = {}
    for n, valor in enumerate(valores, start=1):
        tipo = tipos_por_id.get(valor or '')
        if tipo is None:
            continue
        horas = inicio = None
        if tipo.pide_hora_inicio:
            try:
                inicio = datetime.time.fromisoformat(post.get(f'inicio_{clave}_{n}', '').strip())
            except ValueError:
                errores.append(f'{descripcion}: {tipo.abreviatura} necesita la hora de inicio. Esa celda no se guardó.')
                return None
        if tipo.horas_variables:
            try:
                horas = Decimal(post.get(f'horas_{clave}_{n}', '').replace(',', '.'))
            except InvalidOperation:
                horas = None
            if horas is None or not horas.is_finite() or not (tipo.horas_minimas <= horas <= tipo.horas_maximas):
                errores.append(
                    f'{descripcion}: {tipo.abreviatura} necesita entre {formato_horas(tipo.horas_minimas)} y '
                    f'{formato_horas(tipo.horas_maximas)} horas. Esa celda no se guardó.'
                )
                return None
        elegidos[tipo.pk] = (tipo, horas, inicio)
    return list(elegidos.values())


def _aplicar_turnos(funcionario, fechas, elegidos, usuario):
    """Deja en cada fecha exactamente los turnos elegidos para el funcionario. Devuelve cuántos cambios hubo."""
    cambios = 0
    nuevos = {tipo.pk for tipo, _, _ in elegidos}
    for fecha in fechas:
        actuales = {a.tipo_turno_id: a for a in AsignacionTurno.objects.filter(funcionario=funcionario, fecha=fecha)}
        for pk, asignacion in actuales.items():
            if pk not in nuevos:
                asignacion.delete()
                cambios += 1
        for tipo, horas, inicio in elegidos:
            actual = actuales.get(tipo.pk)
            if actual and actual.horas == horas and actual.hora_inicio == inicio:
                continue
            AsignacionTurno.objects.update_or_create(
                funcionario=funcionario, fecha=fecha, tipo_turno=tipo,
                defaults={'horas': horas, 'hora_inicio': inicio, 'asignado_por': usuario},
            )
            cambios += 1
    return cambios


def _turnos_por_funcionario_y_fecha(asignaciones):
    """{(funcionario_id, fecha): [turnos ordenados por tipo]} para llenar las celdas."""
    orden = {pk: i for i, pk in enumerate(TipoTurno.objects.values_list('pk', flat=True))}
    resultado = defaultdict(list)
    for asignacion in asignaciones:
        resultado[(asignacion.funcionario_id, asignacion.fecha)].append(asignacion)
    for lista in resultado.values():
        lista.sort(key=lambda a: orden[a.tipo_turno_id])
    return resultado


def _ranuras(turnos):
    """Los turnos de una celda repartidos en principal y adicional: [primero o None, segundo o None]."""
    return (list(turnos) + [None] * TURNOS_POR_DIA)[:TURNOS_POR_DIA]


def _tipos_elegibles(asignaciones):
    """Turnos que se pueden elegir: los activos y los que ya estén asignados aunque se hayan desactivado."""
    usados = {a.tipo_turno_id for a in asignaciones}
    return list(TipoTurno.objects.filter(Q(activo=True) | Q(pk__in=usados)))


def _avisar_errores(request, errores):
    for error in errores:
        messages.warning(request, error)


def _volver_al_cuadro(fecha, area):
    parametros = {'anio': fecha.year, 'mes': fecha.month}
    if area:
        parametros['area'] = area.pk
    return redirect(f"{reverse('turnos:cuadro')}?{urlencode(parametros)}")


def _fechas_elegidas(texto):
    """Convierte '2026-10-20,2026-10-22' en una lista ordenada de fechas válidas, sin repetir."""
    fechas = set()
    for parte in texto.split(','):
        try:
            fechas.add(datetime.date.fromisoformat(parte.strip()))
        except ValueError:
            continue
    return sorted(fechas)[:MAX_DIAS_SELECCIONADOS]


@administrador_requerido
def dia(request, anio, mes, dia):
    """Asigna los turnos (principal y adicional) de cada funcionario en un día, o en toda su semana."""
    try:
        fecha = datetime.date(anio, mes, dia)
    except ValueError:
        raise Http404
    area = _area_elegida(request.POST if request.method == 'POST' else request.GET)
    funcionarios = list(_funcionarios_activos(area))

    lunes = fecha - datetime.timedelta(days=fecha.weekday())
    semana = [lunes + datetime.timedelta(days=i) for i in range(7)]
    asignaciones = list(
        AsignacionTurno.objects.filter(funcionario__in=funcionarios, fecha__in=semana).select_related('tipo_turno')
    )
    celdas = _turnos_por_funcionario_y_fecha(asignaciones)
    tipos = _tipos_elegibles([a for a in asignaciones if a.fecha == fecha])

    if request.method == 'POST':
        tipos_por_id = {str(t.pk): t for t in tipos}
        fechas = semana if request.POST.get('alcance') == 'semana' else [fecha]
        errores = []
        with transaction.atomic():
            for funcionario in funcionarios:
                elegidos = _leer_celda(request.POST, f'turno_{funcionario.pk}', tipos_por_id, errores, funcionario.nombre_completo)
                if elegidos is not None:
                    _aplicar_turnos(funcionario, fechas, elegidos, request.user)
        _avisar_errores(request, errores)
        if len(fechas) == 1:
            messages.success(request, f'Turnos del {fecha:%d/%m/%Y} guardados.')
        else:
            messages.success(request, f'Turnos de la semana del {semana[0]:%d/%m} al {semana[-1]:%d/%m/%Y} guardados.')
        return _volver_al_cuadro(fecha, area)

    filas = [
        {
            'funcionario': f,
            'clave': f'turno_{f.pk}',
            'ranuras': _ranuras(celdas[(f.pk, fecha)]),
            'semana': [celdas[(f.pk, d)] for d in semana],
        }
        for f in funcionarios
    ]
    return render(request, 'turnos/dia.html', {
        'fecha': fecha,
        'festivo': Festivo.objects.filter(fecha=fecha).first(),
        'anterior': fecha - datetime.timedelta(days=1),
        'siguiente': fecha + datetime.timedelta(days=1),
        'semana': semana,
        'filas': filas,
        'tipos': tipos,
        'areas': Area.objects.filter(activo=True),
        'area': area,
    })


@administrador_requerido
def varios(request):
    """Asigna turnos en varios días elegidos en el cuadro del mes (?fechas=AAAA-MM-DD,AAAA-MM-DD…).

    Muestra una columna por día: cada celda es el turno principal y el adicional de un funcionario en ese día.
    """
    datos = request.POST if request.method == 'POST' else request.GET
    fechas = _fechas_elegidas(datos.get('fechas', ''))
    area = _area_elegida(datos)
    cargo = _cargo_elegido(datos)
    if not fechas:
        messages.error(request, 'Seleccione al menos un día en el cuadro.')
        return redirect('turnos:cuadro')
    funcionarios = list(_funcionarios_activos(area, cargo))

    asignaciones = list(
        AsignacionTurno.objects.filter(funcionario__in=funcionarios, fecha__in=fechas).select_related('tipo_turno')
    )
    celdas = _turnos_por_funcionario_y_fecha(asignaciones)
    tipos = _tipos_elegibles(asignaciones)

    if request.method == 'POST':
        tipos_por_id = {str(t.pk): t for t in tipos}
        cambios = 0
        errores = []
        with transaction.atomic():
            for funcionario in funcionarios:
                for fecha in fechas:
                    descripcion = f'{funcionario.nombre_completo} el {fecha:%d/%m}'
                    elegidos = _leer_celda(
                        request.POST, f'turno_{funcionario.pk}_{fecha.isoformat()}', tipos_por_id, errores, descripcion,
                    )
                    if elegidos is not None:
                        cambios += _aplicar_turnos(funcionario, [fecha], elegidos, request.user)
        _avisar_errores(request, errores)
        messages.success(request, f'Turnos guardados ({cambios} cambio{"s" if cambios != 1 else ""}).')
        return _volver_al_cuadro(fechas[0], area)

    filas = [
        {
            'funcionario': f,
            'celdas': [
                {
                    'fecha': d,
                    'clave': f'turno_{f.pk}_{d.isoformat()}',
                    'etiqueta': f'{f.nombre_completo}, {d:%d/%m}',
                    'ranuras': _ranuras(celdas[(f.pk, d)]),
                }
                for d in fechas
            ],
        }
        for f in funcionarios
    ]
    return render(request, 'turnos/varios.html', {
        'fechas': fechas,
        'fechas_texto': ','.join(d.isoformat() for d in fechas),
        'filas': filas,
        'tipos': tipos,
        'area': area,
        'cargo': cargo,
        'cargos': Cargo.objects.filter(activo=True),
    })


@administrador_requerido
def tipos(request):
    return render(request, 'turnos/tipos.html', {'tipos': TipoTurno.objects.all()})


@administrador_requerido
def tipo_crear(request):
    form = TipoTurnoForm(request.POST or None)
    if form.is_valid():
        tipo = form.save()
        messages.success(request, f'Turno «{tipo.nombre}» creado.')
        return redirect('turnos:tipos')
    return render(request, 'turnos/tipo_formulario.html', {'form': form, 'titulo': 'Nuevo tipo de turno'})


@administrador_requerido
def tipo_editar(request, pk):
    tipo = get_object_or_404(TipoTurno, pk=pk)
    form = TipoTurnoForm(request.POST or None, instance=tipo)
    if form.is_valid():
        form.save()
        messages.success(request, f'Turno «{tipo.nombre}» actualizado.')
        return redirect('turnos:tipos')
    return render(request, 'turnos/tipo_formulario.html', {'form': form, 'titulo': f'Editar turno: {tipo.nombre}'})


@require_POST
@administrador_requerido
def tipo_estado(request, pk):
    tipo = get_object_or_404(TipoTurno, pk=pk)
    tipo.activo = not tipo.activo
    tipo.save(update_fields=['activo'])
    messages.success(request, f'Turno «{tipo.nombre}» {"activado" if tipo.activo else "desactivado"}.')
    return redirect('turnos:tipos')


SESION_EXCEL = 'cuadro_excel'
TAMANO_MAXIMO_EXCEL = 10 * 1024 * 1024


@administrador_requerido
def subir_excel(request):
    """Paso 1: se sube el Excel del cuadro de turno y se muestra lo que se va a cargar, hoja por hoja."""
    hoy = timezone.localdate()
    hojas = None
    if request.method == 'POST':
        archivo = request.FILES.get('archivo')
        if not archivo:
            messages.error(request, 'Elija el archivo de Excel del cuadro de turno.')
        elif not archivo.name.lower().endswith('.xlsx'):
            messages.error(request, 'El archivo debe ser un Excel .xlsx.')
        elif archivo.size > TAMANO_MAXIMO_EXCEL:
            messages.error(request, 'El archivo es demasiado grande (máximo 10 MB).')
        else:
            try:
                hojas = leer_excel(archivo)
            except ErrorExcel as error:
                messages.error(request, str(error))
            else:
                if not hojas:
                    messages.error(request, 'No se encontró ningún cuadro de turno en el archivo (fila «FECHAS / DIAS» con los días del mes).')
                request.session[SESION_EXCEL] = {'archivo': archivo.name, 'hojas': hojas}
    return render(request, 'turnos/subir_excel.html', {
        'hojas': hojas,
        'archivo': request.FILES.get('archivo'),
        'meses': list(enumerate(MESES, start=1)),
        # Años cercanos, más los que traiga el archivo.
        'anios': sorted(set(range(hoy.year - 1, hoy.year + 3)) | {h['anio'] for h in hojas or [] if h['anio']}),
        'tipos': TipoTurno.objects.filter(activo=True),
    })


@require_POST
@administrador_requerido
def cargar_excel(request):
    """Paso 2: carga las hojas elegidas. Cada día que trae el Excel queda con los turnos del Excel."""
    datos = request.session.get(SESION_EXCEL)
    if not datos:
        messages.error(request, 'Vuelva a subir el archivo: la vista previa ya no está disponible.')
        return redirect('turnos:subir_excel')
    tipos = {t.pk: t for t in TipoTurno.objects.all()}
    funcionarios = {f.pk: f for f in Funcionario.objects.all()}
    vaciar = request.POST.get('vaciar') == 'on'

    resumen, primer_mes = [], None
    with transaction.atomic():
        for indice, hoja in enumerate(datos['hojas']):
            if request.POST.get(f'hoja_{indice}') != 'on' or not hoja['total']:
                continue
            anio = _entero(request.POST.get(f'anio_{indice}'), 0, ANIO_MIN, ANIO_MAX)
            mes = _entero(request.POST.get(f'mes_{indice}'), 0, 1, 12)
            if not anio or not mes:
                messages.error(request, f'Hoja «{hoja["hoja"]}»: elija el mes y el año del cuadro.')
                transaction.set_rollback(True)
                return redirect('turnos:subir_excel')
            primer_mes = primer_mes or (anio, mes)
            por_dia = fechas_de(hoja, anio, mes)
            cambios = 0
            if vaciar:
                # Los días del mes que el Excel deja vacíos (vacaciones, descansos) quedan sin turno.
                personas = {int(pk) for pk in hoja['turnos']}
                sobrantes = AsignacionTurno.objects.filter(funcionario_id__in=personas, fecha__year=anio, fecha__month=mes)
                for asignacion in sobrantes:
                    if (asignacion.funcionario_id, asignacion.fecha) not in por_dia:
                        asignacion.delete()
                        cambios += 1
            for (funcionario_id, fecha), turnos in por_dia.items():
                elegidos = [(tipos[tipo_id], horas, inicio) for tipo_id, horas, inicio in turnos]
                cambios += _aplicar_turnos(funcionarios[funcionario_id], [fecha], elegidos, request.user)
            resumen.append(f'«{hoja["hoja"]}» {MESES[mes - 1].lower()} {anio}: {len(hoja["personas"])} funcionarios, {cambios} cambios')

    if not resumen:
        messages.error(request, 'Marque al menos una hoja para cargar.')
        return redirect('turnos:subir_excel')
    del request.session[SESION_EXCEL]
    messages.success(request, 'Cuadro cargado desde Excel. ' + ' · '.join(resumen) + '.')
    return redirect(f"{reverse('turnos:cuadro')}?{urlencode({'anio': primer_mes[0], 'mes': primer_mes[1]})}")


LETRAS_DIAS = ['L', 'M', 'M', 'J', 'V', 'S', 'D']


def _fecha_iso(texto):
    try:
        return datetime.date.fromisoformat((texto or '').strip())
    except ValueError:
        return None


@administrador_requerido
def programar(request):
    """Arma el borrador del cuadro de un mes para un cargo, con la rotación por líneas, y lo guarda en el cuadro."""
    datos = request.POST if request.method == 'POST' else request.GET
    hoy = timezone.localdate()
    proximo = (hoy.replace(day=1) + datetime.timedelta(days=32)).replace(day=1)
    anio = _entero(datos.get('anio'), proximo.year, ANIO_MIN, ANIO_MAX)
    mes = _entero(datos.get('mes'), proximo.month, 1, 12)
    cargo = _cargo_elegido(datos)
    contexto = {
        'anio': anio, 'mes': mes, 'nombre_mes': MESES[mes - 1], 'cargo': cargo,
        'cargos': Cargo.objects.filter(activo=True),
        'meses': list(enumerate(MESES, start=1)),
        'anios': range(hoy.year - 1, hoy.year + 3),
        'papeles': rotacion.PAPELES, 'lineas': list(enumerate(rotacion.NOMBRES_LINEAS)),
    }
    if cargo is None:
        return render(request, 'turnos/programar.html', contexto)

    tipos = {t.abreviatura.upper(): t for t in TipoTurno.objects.filter(abreviatura__in=rotacion.CODIGOS)}
    faltan = [codigo for codigo in rotacion.CODIGOS if codigo not in tipos]
    dias = rotacion.dias_del_mes(anio, mes)
    laborables = [d for d in dias if d.weekday() < 6]
    grupo = rotacion.grupo_del_mes(cargo, anio, mes)
    enviado = request.method == 'POST'

    personas, filas_formulario, errores = [], [], []
    for p in grupo:
        if not p['esta']:
            continue
        pk = p['funcionario'].pk
        papel, linea = p['papel'], p['linea']
        vacaciones_desde = vacaciones_hasta = None
        elegidos = {d: '' for d in laborables}  # lo que el relevo eligió cada día; empieza en «No puede»
        if enviado:
            papel = datos.get(f'papel_{pk}', papel)
            linea = _entero(datos.get(f'linea_{pk}'), None, 0, len(rotacion.LINEAS) - 1)
            vacaciones_desde = _fecha_iso(datos.get(f'vac_desde_{pk}'))
            vacaciones_hasta = _fecha_iso(datos.get(f'vac_hasta_{pk}')) or vacaciones_desde
            elegidos = {d: datos.get(f'disp_{pk}_{d.isoformat()}', '') for d in laborables}
        disponibles = {d: rotacion.turnos_aceptados(d, valor) for d, valor in elegidos.items()}
        ausencias = {d for d in dias if not p['desde'] <= d <= p['hasta']}
        if vacaciones_desde:
            ausencias |= {d for d in dias if vacaciones_desde <= d <= vacaciones_hasta}
        filas_formulario.append({
            **p, 'papel': papel, 'linea': linea, 'vac_desde': vacaciones_desde, 'vac_hasta': vacaciones_hasta,
            'disponibles': [
                {'fecha': d, 'valor': elegidos[d], 'opciones': rotacion.opciones_relevo(d)} for d in laborables
            ],
            'dias_disponibles': sum(1 for aceptados in disponibles.values() if aceptados),
        })
        if papel != rotacion.FUERA:
            personas.append(rotacion.Persona(
                funcionario=p['funcionario'], papel=papel, linea=linea, ausencias=ausencias,
                disponibles=disponibles if papel == rotacion.RELEVO else None,
            ))

    lineas_titulares = [p.linea for p in personas if p.papel == rotacion.TITULAR]
    if None in lineas_titulares:
        errores.append('Elija la línea de la primera semana de cada titular.')
    elif len(set(lineas_titulares)) != len(lineas_titulares):
        errores.append('Dos titulares tienen la misma línea: cada línea es de un solo titular.')
    if faltan:
        errores.append(f'Faltan estos tipos de turno: {", ".join(faltan)}. Créelos en Tipos de turno.')

    contexto.update({
        'cambios': {estado: [p for p in grupo if p['estado'] == estado] for estado in (rotacion.SIGUE, rotacion.ENTRA, rotacion.SALE)},
        'filas_formulario': filas_formulario,
        'errores': errores if enviado else [e for e in errores if e.startswith('Faltan')],
        'jornada': rotacion.JORNADA_SEMANAL,
    })
    if not enviado or errores:
        return render(request, 'turnos/programar.html', contexto)

    festivos = set(Festivo.objects.filter(fecha__range=(dias[0], dias[-1])).values_list('fecha', flat=True))
    borrador = rotacion.generar(personas, anio, mes, tipos, festivos)
    ids = [p.funcionario.pk for p in personas]
    existentes = AsignacionTurno.objects.filter(funcionario_id__in=ids, fecha__range=(dias[0], dias[-1]))

    if datos.get('accion') == 'guardar':
        with transaction.atomic():
            existentes.delete()
            AsignacionTurno.objects.bulk_create([
                AsignacionTurno(funcionario_id=pk, fecha=fecha, tipo_turno=tipos[codigo], asignado_por=request.user)
                for pk, propios in borrador.turnos.items() for fecha, codigo in propios.items()
            ])
        total = sum(len(propios) for propios in borrador.turnos.values())
        messages.success(request, f'Cuadro de {MESES[mes - 1].lower()} {anio} ({cargo}) guardado: {total} turnos.')
        return redirect(f"{reverse('turnos:cuadro')}?{urlencode({'anio': anio, 'mes': mes})}")

    orden = {rotacion.TITULAR: 0, rotacion.RELEVO: 1, rotacion.COMODIN: 2}
    nombres_papeles = dict(rotacion.PAPELES)
    semanas = rotacion.semanas_del_mes(anio, mes)
    filas = []
    for p in sorted(personas, key=lambda p: (orden[p.papel], p.linea if p.linea is not None else 0)):
        pk = p.funcionario.pk
        propios = borrador.turnos[pk]
        horas = rotacion.horas_por_semana(borrador, pk, anio, mes, tipos)
        filas.append({
            'funcionario': p.funcionario,
            'papel': nombres_papeles[p.papel],
            'linea': rotacion.NOMBRES_LINEAS[p.linea] if p.papel == rotacion.TITULAR else '',
            'celdas': [
                {
                    'tipo': tipos.get(propios.get(d)), 'domingo': d.weekday() == 6, 'festivo': d in festivos,
                    'descanso': d in borrador.descansos[pk], 'ausente': d in p.ausencias and d.weekday() < 6,
                }
                for d in dias
            ],
            'horas': [{'horas': formato_horas(h), 'excede': h > rotacion.JORNADA_SEMANAL} for h in horas],
        })
    contexto.update({
        'borrador': True,
        'columnas': [{'fecha': d, 'letra': LETRAS_DIAS[d.weekday()], 'domingo': d.weekday() == 6, 'festivo': d in festivos} for d in dias],
        'filas': filas,
        'vacantes': [{'codigos': borrador.vacantes.get(d, []), 'domingo': d.weekday() == 6} for d in dias],
        'hay_vacantes': any(borrador.vacantes.values()),
        'semanas': [f'{s[0].day}–{s[-1].day}' for s in semanas],
        'avisos': borrador.avisos,
        'existentes': existentes.count(),
    })
    return render(request, 'turnos/programar.html', contexto)
