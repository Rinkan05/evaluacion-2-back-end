"""Validación y representación JSON de catálogo, carros y solicitudes."""

from django.utils import timezone
from rest_framework import serializers

from .models import (
    Categoria,
    Despacho,
    DetalleSolicitud,
    Insumo,
    ItemCarro,
    Solicitud,
)


# SERIALIZADOR DE CATEGORÍA
# Define los campos expuestos por la API y evita que el cliente asigne el ID.
class CategorySerializer(serializers.ModelSerializer):

    class Meta:
        model = Categoria
        fields = ['id', 'name']
        read_only_fields = ['id']


# SERIALIZADOR DE INSUMO
# Convierte el lote a JSON, permite elegir una categoría existente y valida
# la fecha de vencimiento. La autorización para escribir vive en la vista.
class SupplySerializer(serializers.ModelSerializer):

    category = serializers.StringRelatedField(read_only=True)
    # En lectura se muestra el nombre; al escribir se recibe la clave de categoría.
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Categoria.objects.all(),
        source='category',
        write_only=True,
    )

    class Meta:
        model = Insumo
        # Lista explícita de datos permitidos en la representación REST del lote.
        fields = [
            'id',
            'category',
            'category_id',
            'commercial_name',
            'active_ingredient',
            'lot_number',
            'expiration_date',
            'price_per_box',
            'stock_boxes',
            'created_at',
        ]
        read_only_fields = ['id', 'created_at']

    def validate_expiration_date(self, value):
        """Rechaza nuevos lotes cuya fecha de vencimiento ya pasó."""
        if value < timezone.localdate():
            raise serializers.ValidationError('La fecha de vencimiento debe ser futura.')
        return value


# SERIALIZADOR DE LÍNEA DEL CARRO
# Acepta el ID del lote y una cantidad positiva. No modifica inventario: el
# descuento se realiza únicamente al confirmar la solicitud.
class CartItemSerializer(serializers.ModelSerializer):

    supply = SupplySerializer(read_only=True)
    supply_id = serializers.PrimaryKeyRelatedField(
        queryset=Insumo.objects.select_related('category').all(),
        source='supply',
        write_only=True,
    )

    class Meta:
        model = ItemCarro
        fields = ['id', 'supply', 'supply_id', 'quantity_boxes']
        read_only_fields = ['id']

    def validate_quantity_boxes(self, value):
        """Impide cantidades cero o negativas en una línea del carro."""
        if value < 1:
            raise serializers.ValidationError('La cantidad debe ser al menos una caja.')
        return value


# SERIALIZADOR DE DETALLE HISTÓRICO
# Presenta los valores guardados al pagar y calcula el subtotal como solo lectura.
class OrderItemSerializer(serializers.ModelSerializer):

    subtotal = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = DetalleSolicitud
        fields = [
            'id',
            'supply',
            'commercial_name',
            'lot_number',
            'quantity_boxes',
            'price_per_box',
            'subtotal',
        ]
        read_only_fields = fields


# SERIALIZADOR DE DESPACHO
# Expone estado y fechas, sin permitir que el cliente modifique el seguimiento.
class DispatchSerializer(serializers.ModelSerializer):

    class Meta:
        model = Despacho
        fields = ['status', 'created_at', 'delivered_at']
        read_only_fields = fields


# SERIALIZADOR DE SOLICITUD
# Combina datos de la solicitud, sus líneas históricas y el despacho relacionado.
class OrderSerializer(serializers.ModelSerializer):

    # Se genera en el servidor y se entrega como identificador público inmutable.
    uuid = serializers.UUIDField(read_only=True)
    items = OrderItemSerializer(many=True, read_only=True)
    dispatch = DispatchSerializer(read_only=True)

    class Meta:
        model = Solicitud
        # Los datos anidados son de solo lectura para conservar el historial.
        fields = ['id', 'uuid', 'status', 'created_at', 'total', 'items', 'dispatch']
        read_only_fields = fields


# SERIALIZADOR DE CAMBIO DE ESTADO
# El gestor solo puede solicitar ENTREGADO o CANCELADO. El checkout controla
# PENDIENTE y PAGADO para que no se evite la validación de stock.
class OrderStatusSerializer(serializers.Serializer):

    status = serializers.ChoiceField(
        choices=[Solicitud.Status.DELIVERED, Solicitud.Status.CANCELLED]
    )
