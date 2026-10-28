from django import forms
from django.core.exceptions import ValidationError

from .models import TipoTurno


class TipoTurnoForm(forms.ModelForm):
    class Meta:
        model = TipoTurno
        fields = [
            'nombre', 'abreviatura', 'color', 'horas_variables',
            'hora_inicio', 'hora_fin', 'hora_inicio_2', 'hora_fin_2',
            'hora_inicio_3', 'hora_fin_3', 'hora_inicio_4', 'hora_fin_4',
            'horas_minimas', 'horas_maximas', 'pide_hora_inicio',
        ]
        widgets = {
            'hora_inicio': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_fin': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_inicio_2': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_fin_2': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_inicio_3': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_fin_3': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_inicio_4': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_fin_4': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'horas_minimas': forms.NumberInput(attrs={'step': '0.5', 'min': '0.5', 'max': '24'}),
            'horas_maximas': forms.NumberInput(attrs={'step': '0.5', 'min': '0.5', 'max': '24'}),
            'color': forms.TextInput(attrs={'type': 'color'}),
        }

    def _unico(self, campo, valor):
        repetidos = TipoTurno.objects.filter(**{f'{campo}__iexact': valor})
        if self.instance.pk:
            repetidos = repetidos.exclude(pk=self.instance.pk)
        if repetidos.exists():
            raise ValidationError(f'Ya existe un turno con «{valor}».')
        return valor

    def clean_nombre(self):
        return self._unico('nombre', ' '.join(self.cleaned_data['nombre'].split()))

    def clean_abreviatura(self):
        return self._unico('abreviatura', self.cleaned_data['abreviatura'].strip().upper())

    def clean_color(self):
        return self.cleaned_data['color'].upper()
