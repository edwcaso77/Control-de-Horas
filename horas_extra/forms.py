from django import forms
from django.core.exceptions import ValidationError

from funcionarios.models import Funcionario

from .models import SolicitudHoraExtra

HORA = forms.TimeInput(attrs={'type': 'time'}, format='%H:%M')


class _HorarioForm(forms.ModelForm):
    def clean(self):
        datos = super().clean()
        inicio, fin = datos.get('hora_inicio'), datos.get('hora_fin')
        if inicio and fin and inicio == fin:
            raise ValidationError('La hora de inicio y la de fin no pueden ser iguales.')
        return datos


class SolicitudForm(_HorarioForm):
    """Lo que llena el funcionario. Elige de la lista el administrador que autoriza."""

    class Meta:
        model = SolicitudHoraExtra
        fields = ['hora_inicio', 'hora_fin', 'motivo', 'administrador']
        widgets = {
            'hora_inicio': HORA,
            'hora_fin': HORA,
            'motivo': forms.Textarea(attrs={'rows': 3}),
        }

    def __init__(self, *args, funcionario=None, **kwargs):
        super().__init__(*args, **kwargs)
        administradores = Funcionario.objects.filter(es_administrador=True, usuario__is_active=True)
        if funcionario is not None:
            # Nadie se autoriza su propia hora extra.
            administradores = administradores.exclude(pk=funcionario.pk)
        campo = self.fields['administrador']
        campo.queryset = administradores
        campo.required = True
        campo.label = 'Administrador que autoriza'
        campo.empty_label = 'Seleccione…'
        campo.help_text = 'Solo este administrador verá y revisará la solicitud.'


class SolicitudSinTurnoForm(SolicitudForm):
    """Hora extra en un día sin turno asignado (por ejemplo, un domingo que le pidieron trabajar)."""

    class Meta(SolicitudForm.Meta):
        fields = ['fecha'] + SolicitudForm.Meta.fields
        widgets = {**SolicitudForm.Meta.widgets, 'fecha': forms.DateInput(attrs={'type': 'date'}, format='%Y-%m-%d')}

    def __init__(self, *args, hoy=None, **kwargs):
        super().__init__(*args, **kwargs)
        self.hoy = hoy
        self.fields['fecha'].label = 'Día trabajado'
        if hoy:
            self.fields['fecha'].widget.attrs['max'] = hoy.isoformat()

    def clean_fecha(self):
        fecha = self.cleaned_data['fecha']
        if self.hoy and fecha > self.hoy:
            raise ValidationError('La hora extra se solicita después de trabajarla: ese día todavía no ha llegado.')
        return fecha


class RevisionForm(_HorarioForm):
    """Lo que revisa el administrador: puede corregir el horario y dejar un comentario."""

    class Meta:
        model = SolicitudHoraExtra
        fields = ['hora_inicio', 'hora_fin', 'comentario']
        widgets = {
            'hora_inicio': HORA,
            'hora_fin': HORA,
            'comentario': forms.Textarea(attrs={'rows': 3}),
        }
