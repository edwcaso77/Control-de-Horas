from django import forms
from django.core.exceptions import ValidationError

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
    """Lo que llena el funcionario."""

    class Meta:
        model = SolicitudHoraExtra
        fields = ['hora_inicio', 'hora_fin', 'motivo', 'autorizado_por']
        widgets = {
            'hora_inicio': HORA,
            'hora_fin': HORA,
            'motivo': forms.Textarea(attrs={'rows': 3}),
        }


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
