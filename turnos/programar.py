"""Borrador del cuadro de turno de un mes, con la rotación por líneas del cuadro de enfermería.

De lunes a sábado hay cuatro puestos por día; los domingos no se programan:
- Lunes, miércoles y viernes: C1 y C2 (mañana), X1 y X2 (tarde).
- Martes, jueves y sábado: M1 y M2 (mañana), T1 y T2 (tarde).

Papeles:
- Titular: tiene una línea toda la semana (C1+M1, X1+T1, C2+M2 o X2+T2) y la semana siguiente pasa a la que sigue,
  así alterna mañana y tarde y cambia de ala cada dos semanas.
- Relevo: en los días que puede, cubre las ausencias y da un día de descanso por semana a cada titular.
- Comodín: hace su turno administrativo (A) de lunes a viernes y cubre las ausencias que el relevo no alcance.
"""
import datetime
from collections import Counter, defaultdict
from dataclasses import dataclass, field

from funcionarios.models import Funcionario

from .models import AsignacionTurno

LINEAS = [('C1', 'M1'), ('X1', 'T1'), ('C2', 'M2'), ('X2', 'T2')]
NOMBRES_LINEAS = [f'{lmv} + {mjs}' for lmv, mjs in LINEAS]
ADMINISTRATIVO = 'A'
CODIGOS = [codigo for linea in LINEAS for codigo in linea] + [ADMINISTRATIVO]
JORNADA_SEMANAL = 42  # horas
DESCANSO_MINIMO = 10  # horas entre el fin de un turno y el inicio del siguiente

TITULAR, RELEVO, COMODIN, FUERA = 'titular', 'relevo', 'comodin', 'fuera'
PAPELES = [(TITULAR, 'Titular'), (RELEVO, 'Relevo'), (COMODIN, 'Comodín'), (FUERA, 'No programar')]

SIGUE, ENTRA, SALE = 'sigue', 'entra', 'sale'


def dias_del_mes(anio, mes):
    primero = datetime.date(anio, mes, 1)
    siguiente = datetime.date(anio + mes // 12, mes % 12 + 1, 1)
    return [primero + datetime.timedelta(days=i) for i in range((siguiente - primero).days)]


def semanas_del_mes(anio, mes):
    """Los días de lunes a sábado del mes, agrupados por semana."""
    semanas = {}
    for fecha in dias_del_mes(anio, mes):
        if fecha.weekday() < 6:
            semanas.setdefault(fecha - datetime.timedelta(days=fecha.weekday()), []).append(fecha)
    return list(semanas.values())


def puesto(linea, fecha):
    """El turno de una línea en un día: el de lunes, miércoles y viernes o el de martes, jueves y sábado."""
    return LINEAS[linea][fecha.weekday() % 2]


def linea_de(codigos):
    """La línea que alguien trabajó en una semana: la de la mayoría de sus turnos, si son al menos tres."""
    votos = Counter(i for codigo in codigos for i, linea in enumerate(LINEAS) if codigo in linea)
    if votos:
        linea, veces = votos.most_common(1)[0]
        if veces >= 3:
            return linea
    return None


def _lunes(fecha):
    return fecha - datetime.timedelta(days=fecha.weekday())


def grupo_del_mes(cargo, anio, mes):
    """Las personas del cargo para el cuadro del mes, comparadas con el cuadro del mes anterior.

    Cada una con su estado (sigue, entra o sale), los días que está (por ingreso y retiro), y un papel y una línea
    sugeridos: la rotación sigue donde quedó la última semana del mes anterior.
    """
    dias = dias_del_mes(anio, mes)
    inicio, fin = dias[0], dias[-1]
    fin_anterior = inicio - datetime.timedelta(days=1)
    anteriores = defaultdict(list)
    for asignacion in (AsignacionTurno.objects
                       .filter(funcionario__cargo=cargo, fecha__range=(fin_anterior.replace(day=1), fin_anterior))
                       .select_related('tipo_turno')):
        anteriores[asignacion.funcionario_id].append((asignacion.fecha, asignacion.tipo_turno.abreviatura.upper()))

    # Si el mes empieza entre martes y sábado, su primera semana es la misma que cerró el mes anterior.
    continua = inicio.weekday() in range(1, 6)
    personas = []
    for funcionario in Funcionario.objects.filter(cargo=cargo).select_related('usuario'):
        desde = max(inicio, funcionario.fecha_ingreso or inicio)
        hasta = min(fin, funcionario.fecha_retiro or fin)
        # Un inactivo sin fecha de retiro ya no se programa.
        esta = desde <= hasta and (funcionario.activo or funcionario.fecha_retiro is not None)
        turnos = anteriores.get(funcionario.pk, [])
        if not esta and not turnos:
            continue
        if turnos and (not esta or hasta < fin):
            estado = SALE
        elif not turnos:
            estado = ENTRA
        else:
            estado = SIGUE

        linea = None
        por_semana = defaultdict(list)
        for fecha, codigo in turnos:
            por_semana[_lunes(fecha)].append(codigo)
        # Decide la última semana con al menos tres turnos (las de vacaciones o los pedazos de semana no cuentan):
        # si esa semana tuvo una línea, la rotación sigue desde ahí; si no, cubría puestos sueltos (relevo).
        for lunes in sorted(por_semana, reverse=True):
            if len(por_semana[lunes]) < 3:
                continue
            encontrada = linea_de(por_semana[lunes])
            if encontrada is not None:
                semanas_despues = (_lunes(fin_anterior) - lunes).days // 7
                linea = (encontrada + semanas_despues + (0 if continua else 1)) % len(LINEAS)
            break

        codigos = Counter(codigo for _, codigo in turnos)
        if not esta:
            papel = FUERA
        elif codigos and codigos.most_common(1)[0][0] == ADMINISTRATIVO:
            papel = COMODIN
        elif linea is not None:
            papel = TITULAR
        else:
            papel = RELEVO
        personas.append({
            'funcionario': funcionario, 'estado': estado, 'desde': desde, 'hasta': hasta, 'esta': esta,
            'papel': papel, 'linea': linea if papel == TITULAR else None,
        })

    # Las líneas que quedan libres (por ejemplo, de quien se fue) pasan a los que entran.
    titulares = [p for p in personas if p['papel'] == TITULAR]
    ocupadas = set()
    for p in titulares:
        if p['linea'] in ocupadas:
            p['linea'] = None
        ocupadas.add(p['linea'])
    libres = [i for i in range(len(LINEAS)) if i not in ocupadas]
    for p in titulares:
        if p['linea'] is None and libres:
            p['linea'] = libres.pop(0)
    for p in personas:
        if p['estado'] == ENTRA and p['papel'] == RELEVO and libres:
            p['papel'], p['linea'] = TITULAR, libres.pop(0)
    return personas


@dataclass
class Persona:
    funcionario: Funcionario
    papel: str
    linea: int | None = None  # línea de la primera semana del mes (titulares)
    ausencias: set = field(default_factory=set)  # días que no está: vacaciones, antes del ingreso, después del retiro
    # Relevo: {fecha: {turnos que acepta ese día}}; None = cualquier turno cualquier día.
    # Si un día acepta un solo turno, es un turno que pidió: se le da y ese día descansa el titular que lo tenía.
    disponibles: dict | None = None

    def puede(self, fecha, codigo):
        return self.disponibles is None or codigo in self.disponibles.get(fecha, ())

    def pedido(self, fecha):
        """El turno que pidió ese día, o None si no pidió uno en particular."""
        aceptados = (self.disponibles or {}).get(fecha, set())
        return next(iter(aceptados)) if len(aceptados) == 1 else None


# Lo que el relevo puede elegir cada día, además de un turno en particular.
CUALQUIERA, MANANA, TARDE = 'todos', 'manana', 'tarde'


def opciones_relevo(fecha):
    """Opciones del día para el relevo: [(valor, texto)]."""
    puestos = sorted(puesto(linea, fecha) for linea in range(len(LINEAS)))
    return [('', 'No puede'), (CUALQUIERA, 'Cualquiera'), (MANANA, 'Mañana'), (TARDE, 'Tarde')] + [(c, c) for c in puestos]


def turnos_aceptados(fecha, valor):
    """Los turnos del día que acepta el relevo según lo que eligió."""
    lineas = {CUALQUIERA: range(len(LINEAS)), MANANA: (0, 2), TARDE: (1, 3)}.get(valor)
    if lineas is not None:
        return {puesto(linea, fecha) for linea in lineas}
    todos = {puesto(linea, fecha) for linea in range(len(LINEAS))}
    return {valor} if valor in todos else set()


@dataclass
class Borrador:
    turnos: dict  # {funcionario_id: {fecha: abreviatura}}
    descansos: dict  # {funcionario_id: {fechas}}
    vacantes: dict  # {fecha: [abreviaturas sin cubrir]}
    avisos: list


def _fin(fecha, tipo):
    fin = datetime.datetime.combine(fecha, tipo.hora_fin_ultimo_bloque)
    if fin <= datetime.datetime.combine(fecha, tipo.hora_inicio):
        fin += datetime.timedelta(days=1)
    return fin


def _choca(turnos, fecha, codigo, tipos):
    """True si el turno deja menos de DESCANSO_MINIMO horas con el del día anterior o el del siguiente."""
    tipo = tipos[codigo]
    minimo = datetime.timedelta(hours=DESCANSO_MINIMO)
    antes = turnos.get(fecha - datetime.timedelta(days=1))
    if antes and datetime.datetime.combine(fecha, tipo.hora_inicio) - _fin(fecha - datetime.timedelta(days=1), tipos[antes]) < minimo:
        return True
    siguiente_dia = fecha + datetime.timedelta(days=1)
    despues = turnos.get(siguiente_dia)
    return bool(despues and datetime.datetime.combine(siguiente_dia, tipos[despues].hora_inicio) - _fin(fecha, tipo) < minimo)


def generar(personas, anio, mes, tipos, festivos=()):
    """Arma el borrador del mes. `tipos` es {abreviatura: TipoTurno} con todos los CODIGOS."""
    turnos = {p.funcionario.pk: {} for p in personas}
    descansos = defaultdict(set)
    vacantes = defaultdict(list)
    avisos = []
    titulares = [p for p in personas if p.papel == TITULAR]
    relevos = [p for p in personas if p.papel == RELEVO]
    comodines = [p for p in personas if p.papel == COMODIN]

    def horas_semana(p, fecha):
        lunes = _lunes(fecha)
        return sum(tipos[c].duracion_horas for f, c in turnos[p.funcionario.pk].items() if _lunes(f) == lunes)

    def cubrir(fecha, codigo, quienes, pasar_jornada=False):
        """Le da el puesto al que lleve menos horas esa semana; sin pasar la jornada, salvo pasar_jornada."""
        for p in sorted(quienes, key=lambda p: (horas_semana(p, fecha), len(turnos[p.funcionario.pk]))):
            propios = turnos[p.funcionario.pk]
            if not p.puede(fecha, codigo) or fecha in p.ausencias or fecha in propios or _choca(propios, fecha, codigo, tipos):
                continue
            if not pasar_jornada and horas_semana(p, fecha) + tipos[codigo].duracion_horas > JORNADA_SEMANAL:
                continue
            propios[fecha] = codigo
            return True
        return False

    for numero, semana in enumerate(semanas_del_mes(anio, mes)):
        lineas_semana = {(t.linea + numero) % len(LINEAS): t for t in titulares}
        # Puestos de la semana: los de cada titular, y los de las líneas sin titular, que hay que cubrir.
        for linea in range(len(LINEAS)):
            titular = lineas_semana.get(linea)
            for fecha in semana:
                codigo = puesto(linea, fecha)
                if titular and fecha not in titular.ausencias:
                    turnos[titular.funcionario.pk][fecha] = codigo
                # Relevo dentro de la jornada; si no alcanza, el comodín (deja su A ese día); si tampoco, relevo con horas extra.
                elif not (cubrir(fecha, codigo, relevos) or cubrir(fecha, codigo, comodines, pasar_jornada=True)
                          or cubrir(fecha, codigo, relevos, pasar_jornada=True)):
                    vacantes[fecha].append(codigo)

        # Primero los turnos que pidió el relevo: ese día descansa el titular que tenía ese turno.
        con_descanso = {t.funcionario.pk for t in titulares if any(fecha in t.ausencias for fecha in semana)}
        for relevo in relevos:
            for fecha in semana:
                codigo = relevo.pedido(fecha)
                if codigo is None or turnos[relevo.funcionario.pk].get(fecha) == codigo:
                    continue
                titular = next((t for t in titulares if turnos[t.funcionario.pk].get(fecha) == codigo), None)
                if titular and titular.funcionario.pk not in con_descanso and cubrir(fecha, codigo, [relevo]):
                    del turnos[titular.funcionario.pk][fecha]
                    descansos[titular.funcionario.pk].add(fecha)
                    con_descanso.add(titular.funcionario.pk)
                else:
                    avisos.append(
                        f'{relevo.funcionario.nombre_completo} pidió {codigo} el {fecha:%d/%m} y no se le pudo dar '
                        '(ese titular ya descansa esa semana, el relevo ya tiene turno o pasaría la jornada).'
                    )

        # Un descanso por titular en las semanas completas, si el relevo puede cubrirlo. El día se corre cada semana.
        if len(semana) < 6:
            continue
        for orden, titular in enumerate(titulares[numero % len(titulares):] + titulares[:numero % len(titulares)]):
            if titular.funcionario.pk in con_descanso:
                continue  # ya tiene días libres esa semana
            propios = turnos[titular.funcionario.pk]
            for k in range(len(semana)):
                fecha = semana[(orden + numero + k) % len(semana)]
                if fecha in propios and cubrir(fecha, propios[fecha], relevos):
                    del propios[fecha]
                    descansos[titular.funcionario.pk].add(fecha)
                    break
            else:
                avisos.append(
                    f'{titular.funcionario.nombre_completo} trabaja completa la semana del {semana[0]:%d/%m}: '
                    'el relevo no tiene un día disponible para darle descanso.'
                )

    for p in comodines:
        propios = turnos[p.funcionario.pk]
        for fecha in dias_del_mes(anio, mes):
            if fecha.weekday() < 5 and fecha not in festivos and fecha not in p.ausencias and fecha not in propios:
                propios[fecha] = ADMINISTRATIVO

    if len(titulares) != len(LINEAS):
        avisos.insert(0, f'Hay {len(titulares)} titulares para {len(LINEAS)} líneas.')
    return Borrador(turnos=turnos, descansos=descansos, vacantes=vacantes, avisos=avisos)


def horas_por_semana(borrador, funcionario_id, anio, mes, tipos):
    """Horas de cada semana del mes para una persona, según los turnos del borrador."""
    propios = borrador.turnos.get(funcionario_id, {})
    return [
        sum(tipos[propios[fecha]].duracion_horas for fecha in semana if fecha in propios)
        for semana in semanas_del_mes(anio, mes)
    ]
