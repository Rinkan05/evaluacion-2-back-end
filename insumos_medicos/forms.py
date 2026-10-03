"""Formularios HTML que deben usar los modelos propios del proyecto."""

from django.contrib.auth import get_user_model
from django.contrib.auth.forms import UserCreationForm
from django import forms
from django.utils import timezone

from .models import Insumo, Solicitud

User = get_user_model()


class InstitutionCreationForm(UserCreationForm):
    """Valida y guarda cuentas nuevas en el modelo de usuario configurado."""

    class Meta(UserCreationForm.Meta):
        # UserCreationForm de Django apunta por defecto a auth.User; el proyecto
        # lo reemplaza por CustomUser, por lo que debe usar el modelo activo.
        model = User


class ManagedUserCreationForm(UserCreationForm):
    """Formulario exclusivo del maestro para crear instituciones o gestores."""

    rol = forms.ChoiceField(
        label='Rol de la cuenta',
        choices=User.Role.choices,
    )

    class Meta(UserCreationForm.Meta):
        model = User
        fields = ('username', 'rol')


class ManagedUserUpdateForm(forms.ModelForm):
    """Permite cambiar rol y activar/desactivar una cuenta no maestra."""

    class Meta:
        model = User
        fields = ('rol', 'is_active')
        labels = {
            'rol': 'Rol de la cuenta',
            'is_active': 'Cuenta activa',
        }


class SupplyForm(forms.ModelForm):
    """Valida los lotes creados o actualizados desde la gestión de bodega."""

    class Meta:
        model = Insumo
        fields = (
            'category',
            'commercial_name',
            'active_ingredient',
            'lot_number',
            'expiration_date',
            'price_per_box',
            'stock_boxes',
        )
        labels = {
            'category': 'Categoría',
            'commercial_name': 'Nombre comercial',
            'active_ingredient': 'Principio activo',
            'lot_number': 'Número de lote',
            'expiration_date': 'Fecha de vencimiento',
            'price_per_box': 'Precio por caja',
            'stock_boxes': 'Cajas disponibles',
        }
        widgets = {
            'category': forms.Select(attrs={'class': 'form-select'}),
            'commercial_name': forms.TextInput(attrs={'class': 'form-control'}),
            'active_ingredient': forms.TextInput(attrs={'class': 'form-control'}),
            'lot_number': forms.TextInput(attrs={'class': 'form-control'}),
            'expiration_date': forms.DateInput(
                attrs={'class': 'form-control', 'type': 'date'},
                format='%Y-%m-%d',
            ),
            'price_per_box': forms.NumberInput(
                attrs={'class': 'form-control', 'min': '0', 'step': '0.01'}
            ),
            'stock_boxes': forms.NumberInput(
                attrs={'class': 'form-control', 'min': '0', 'step': '1'}
            ),
        }

    def clean_expiration_date(self):
        expiration_date = self.cleaned_data['expiration_date']
        if expiration_date < timezone.localdate():
            raise forms.ValidationError(
                'La fecha de vencimiento debe ser futura.'
            )
        return expiration_date


class OrderStatusForm(forms.Form):
    """Limita los cambios manuales a entregar o cancelar solicitudes pagadas."""

    order_id = forms.IntegerField(
        min_value=1,
        widget=forms.HiddenInput(),
    )
    status = forms.ChoiceField(
        choices=(
            (Solicitud.Status.DELIVERED, 'Marcar como entregada'),
            (Solicitud.Status.CANCELLED, 'Cancelar y reponer stock'),
        ),
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
