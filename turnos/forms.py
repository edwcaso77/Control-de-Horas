from django import forms
from django.core.exceptions import ValidationError

from .models import TipoTurno


class TipoTurnoForm(forms.ModelForm):
    class Meta:
        model = TipoTurno
        fields = ['nombre', 'abreviatura', 'hora_inicio', 'hora_fin', 'color']
        widgets = {
            'hora_inicio': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
            'hora_fin': forms.TimeInput(attrs={'type': 'time'}, format='%H:%M'),
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
