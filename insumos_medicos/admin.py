"""Personaliza la consola administrativa para la gestión interna de bodega."""

from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Carro,
    Categoria,
    CustomUser,
    Despacho,
    DetalleSolicitud,
    Insumo,
    ItemCarro,
    Solicitud,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    """Permite al superusuario maestro crear cuentas y asignarles un rol B2B.

    El campo rol clasifica al usuario como institución o gestor. No equivale a
    los indicadores internos is_staff/is_superuser de Django, que conceden
    privilegios de administración del sitio.
    """

    fieldsets = UserAdmin.fieldsets + (
        ('Rol de la plataforma', {'fields': ('rol',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Rol de la plataforma', {'fields': ('rol',)}),
    )
    list_display = (*UserAdmin.list_display, 'rol')
    list_filter = (*UserAdmin.list_filter, 'rol')

    def has_view_permission(self, request, obj=None):
        """Reserva la consulta de cuentas al superusuario maestro."""
        return request.user.is_superuser

    def has_add_permission(self, request):
        """Solo el superusuario maestro puede crear cuentas con un rol asignado."""
        return request.user.is_superuser

    def has_change_permission(self, request, obj=None):
        """Solo el superusuario maestro puede editar cuentas y sus roles."""
        return request.user.is_superuser

    def has_delete_permission(self, request, obj=None):
        """Solo el superusuario maestro puede eliminar cuentas del sistema."""
        return request.user.is_superuser


@admin.register(Categoria)
class CategoryAdmin(admin.ModelAdmin):
    """Facilita buscar y mantener categorías desde Django Admin."""

    search_fields = ['name']


@admin.register(Insumo)
class SupplyAdmin(admin.ModelAdmin):
    """Muestra y filtra lotes por categoría y vencimiento en la bodega."""

    list_display = (
        'commercial_name',
        'category',
        'active_ingredient',
        'lot_number',
        'expiration_date',
        'price_per_box',
        'stock_boxes',
    )
    list_filter = ['category', 'expiration_date']
    search_fields = ['commercial_name', 'active_ingredient', 'lot_number']


class OrderItemInline(admin.TabularInline):
    """Presenta los detalles históricos dentro de cada solicitud."""

    model = DetalleSolicitud
    extra = 0
    readonly_fields = [
        'supply',
        'commercial_name',
        'lot_number',
        'quantity_boxes',
        'price_per_box',
    ]


@admin.register(Solicitud)
class OrderAdmin(admin.ModelAdmin):
    """Permite revisar solicitudes sin borrar ni alterar su estado histórico."""

    list_display = ('id', 'user', 'status', 'total', 'created_at')
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'user__email']
    inlines = [OrderItemInline]
    readonly_fields = ['user', 'status', 'total', 'created_at']

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Carro)
admin.site.register(ItemCarro)


@admin.register(Despacho)
class DispatchAdmin(admin.ModelAdmin):
    """Consulta despachos; su creación y estado se controlan desde el flujo API."""

    list_display = ('order', 'status', 'created_at', 'delivered_at')
    list_filter = ['status', 'created_at']
    readonly_fields = ['order', 'status', 'created_at', 'delivered_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
