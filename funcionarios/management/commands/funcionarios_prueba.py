import secrets

from django.conf import settings
from django.core.management.base import BaseCommand, CommandError
from django.db import transaction

from funcionarios.forms import FuncionarioForm
from funcionarios.models import Area, Cargo, Funcionario

# Documentos reservados para datos de prueba: 900000001, 900000002…
PREFIJO_DOCUMENTO = '9000000'
ARCHIVO_CREDENCIALES = 'credenciales_prueba.txt'

PERSONAS = {
    'Auxiliar de Enfermeria': [
        ('Laura', 'Gómez Prueba'), ('Andrés', 'Ruiz Prueba'), ('Paola', 'Martínez Prueba'),
        ('Jorge', 'Herrera Prueba'), ('Diana', 'Castro Prueba'), ('Camilo', 'Vargas Prueba'),
        ('Natalia', 'Ríos Prueba'),
    ],
    'Enfermero Profesional': [
        ('Sofía', 'Morales Prueba'), ('Julián', 'Ortiz Prueba'), ('Valentina', 'Rojas Prueba'),
        ('Felipe', 'Mendoza Prueba'), ('Carolina', 'Silva Prueba'),
    ],
    'Médico': [
        ('Ricardo', 'Peña Prueba'), ('Mónica', 'Salazar Prueba'), ('Esteban', 'Navarro Prueba'),
    ],
}


class Command(BaseCommand):
    help = 'Crea (o con --borrar, elimina) funcionarios ficticios para hacer pruebas.'

    def add_arguments(self, parser):
        parser.add_argument('--area', default='Sala de Hemodialisis', help='Área donde quedan los funcionarios de prueba.')
        parser.add_argument('--borrar', action='store_true', help='Elimina los funcionarios de prueba y sus turnos.')

    def handle(self, *args, area, borrar, **opciones):
        if borrar:
            self._borrar()
        else:
            self._crear(area)

    @transaction.atomic
    def _crear(self, nombre_area):
        area = Area.objects.filter(nombre__iexact=nombre_area).first()
        if area is None:
            raise CommandError(f'No existe el área «{nombre_area}». Créela primero o indique otra con --area.')

        clave = 'Prueba-' + secrets.token_urlsafe(8)
        creados = []
        numero = 0
        for nombre_cargo, personas in PERSONAS.items():
            cargo, _ = Cargo.objects.get_or_create(nombre=nombre_cargo)
            for nombres, apellidos in personas:
                numero += 1
                documento = f'{PREFIJO_DOCUMENTO}{numero:02d}'
                if Funcionario.objects.filter(numero_documento=documento).exists():
                    continue
                form = FuncionarioForm({
                    'tipo_documento': 'CC', 'numero_documento': documento,
                    'nombres': nombres, 'apellidos': apellidos,
                    'cargo': cargo.pk, 'area': area.pk,
                    'password1': clave, 'password2': clave,
                })
                if not form.is_valid():
                    raise CommandError(f'No se pudo crear {nombres} {apellidos}: {form.errors.as_text()}')
                creados.append((form.save(), nombre_cargo))

        if not creados:
            self.stdout.write('Los funcionarios de prueba ya existían; no se creó ninguno.')
            return

        # La contraseña no se muestra en pantalla: queda en un archivo local que git ignora.
        ruta = settings.BASE_DIR / ARCHIVO_CREDENCIALES
        with open(ruta, 'w', encoding='utf-8') as archivo:
            archivo.write('Funcionarios de prueba (datos ficticios). Usuario = documento.\n')
            archivo.write(f'Contraseña de todos: {clave}\n\n')
            for funcionario, nombre_cargo in creados:
                archivo.write(f'{funcionario.numero_documento}  {funcionario.nombre_completo}  ({nombre_cargo})\n')

        self.stdout.write(self.style.SUCCESS(f'{len(creados)} funcionarios de prueba creados en «{area}».'))
        self.stdout.write(f'Usuarios y contraseña en: {ruta}')

    @transaction.atomic
    def _borrar(self):
        from turnos.models import AsignacionTurno

        funcionarios = list(Funcionario.objects.filter(numero_documento__startswith=PREFIJO_DOCUMENTO).select_related('usuario'))
        AsignacionTurno.objects.filter(funcionario__in=funcionarios).delete()
        for funcionario in funcionarios:
            usuario = funcionario.usuario
            funcionario.delete()
            usuario.delete()
        (settings.BASE_DIR / ARCHIVO_CREDENCIALES).unlink(missing_ok=True)
        self.stdout.write(self.style.SUCCESS(f'{len(funcionarios)} funcionarios de prueba eliminados, con sus turnos.'))
