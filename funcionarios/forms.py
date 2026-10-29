from django import forms
from django.contrib.auth import get_user_model, password_validation
from django.contrib.auth.forms import AuthenticationForm
from django.core.exceptions import ValidationError
from django.db import transaction
from django.db.models import Q

from .models import Area, Cargo, Funcionario

Usuario = get_user_model()


class IngresoForm(AuthenticationForm):
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['username'].label = 'Número de documento'
        self.fields['password'].label = 'Contraseña'


class FuncionarioForm(forms.ModelForm):
    password1 = forms.CharField(label='Contraseña', strip=False, required=False, widget=forms.PasswordInput)
    password2 = forms.CharField(label='Confirmar contraseña', strip=False, required=False, widget=forms.PasswordInput)

    class Meta:
        model = Funcionario
        fields = [
            'tipo_documento', 'numero_documento', 'nombres', 'apellidos',
            'cargo', 'area', 'correo', 'telefono', 'fecha_ingreso', 'fecha_retiro', 'es_administrador',
        ]
        widgets = {
            'fecha_ingreso': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
            'fecha_retiro': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d'),
        }

    def __init__(self, *args, usuario_actual=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.usuario_actual = usuario_actual

        # Solo se ofrecen cargos y áreas activos, pero se conserva el valor actual aunque esté inactivo.
        for campo, modelo in (('cargo', Cargo), ('area', Area)):
            actual = getattr(self.instance, f'{campo}_id', None)
            self.fields[campo].queryset = modelo.objects.filter(Q(activo=True) | Q(pk=actual))
            self.fields[campo].required = True
            self.fields[campo].empty_label = 'Seleccione…'

        self.fields['numero_documento'].help_text = 'También es el usuario para entrar al sistema.'

        es_nuevo = self.instance.pk is None
        self.fields['password1'].required = es_nuevo
        self.fields['password2'].required = es_nuevo
        if not es_nuevo:
            self.fields['password1'].help_text = 'Déjela en blanco para conservar la contraseña actual.'

    def _editando_a_si_mismo(self):
        return (
            self.instance.pk is not None
            and self.usuario_actual is not None
            and self.instance.usuario_id == self.usuario_actual.pk
        )

    def clean_numero_documento(self):
        numero = self.cleaned_data['numero_documento'].strip()
        usuarios = Usuario.objects.filter(username__iexact=numero)
        if self.instance.pk:
            usuarios = usuarios.exclude(pk=self.instance.usuario_id)
        if usuarios.exists():
            raise ValidationError('Ya existe un usuario con este número de documento.')
        return numero

    def clean_es_administrador(self):
        es_admin = self.cleaned_data['es_administrador']
        if self._editando_a_si_mismo() and not es_admin and not self.usuario_actual.is_superuser:
            raise ValidationError('No puede quitarse a sí mismo el rol de administrador.')
        return es_admin

    def clean(self):
        datos = super().clean()
        ingreso, retiro = datos.get('fecha_ingreso'), datos.get('fecha_retiro')
        if ingreso and retiro and retiro < ingreso:
            self.add_error('fecha_retiro', 'La fecha de retiro no puede ser anterior a la de ingreso.')
        password1 = datos.get('password1')
        password2 = datos.get('password2')
        if password1 or password2:
            if password1 != password2:
                self.add_error('password2', 'Las contraseñas no coinciden.')
            else:
                try:
                    password_validation.validate_password(password1)
                except ValidationError as error:
                    self.add_error('password1', error)
        return datos

    @transaction.atomic
    def save(self, commit=True):
        funcionario = super().save(commit=False)
        usuario = funcionario.usuario if funcionario.usuario_id else Usuario()
        usuario.username = funcionario.numero_documento
        usuario.first_name = funcionario.nombres[:150]
        usuario.last_name = funcionario.apellidos[:150]
        usuario.email = funcionario.correo
        if self.cleaned_data.get('password1'):
            usuario.set_password(self.cleaned_data['password1'])
        usuario.save()
        funcionario.usuario = usuario
        funcionario.save()
        return funcionario


class CatalogoForm(forms.ModelForm):
    class Meta:
        fields = ['nombre']

    def clean_nombre(self):
        nombre = ' '.join(self.cleaned_data['nombre'].split())
        repetidos = self._meta.model.objects.filter(nombre__iexact=nombre)
        if self.instance.pk:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise ValidationError(f'Ya existe «{nombre}».')
        return nombre


def catalogo_form(modelo):
    return forms.modelform_factory(modelo, form=CatalogoForm, fields=['nombre'])
