import getpass

from django.core.management.base import BaseCommand, CommandError

from funcionarios.forms import FuncionarioForm


class Command(BaseCommand):
    help = 'Crea un funcionario con rol de administrador (para el primer ingreso al sistema).'

    def _preguntar(self, texto):
        valor = ''
        while not valor:
            valor = input(f'{texto}: ').strip()
        return valor

    def handle(self, *args, **opciones):
        self.stdout.write('Registro del administrador. El cargo y el área se completan después desde el sistema.\n')
        datos = {
            'tipo_documento': 'CC',
            'numero_documento': self._preguntar('Número de cédula'),
            'nombres': self._preguntar('Nombres'),
            'apellidos': self._preguntar('Apellidos'),
            'es_administrador': True,
        }
        datos['password1'] = getpass.getpass('Contraseña: ')
        datos['password2'] = getpass.getpass('Confirmar contraseña: ')

        form = FuncionarioForm(datos)
        # El primer administrador puede crearse sin cargo ni área, porque todavía no existen.
        form.fields['cargo'].required = False
        form.fields['area'].required = False
        if not form.is_valid():
            errores = '\n'.join(f'- {e}' for lista in form.errors.values() for e in lista)
            raise CommandError(f'No se pudo crear el administrador:\n{errores}')

        funcionario = form.save()
        self.stdout.write(self.style.SUCCESS(
            f'Administrador {funcionario} creado. Ingrese con el usuario {funcionario.numero_documento}.'
        ))
