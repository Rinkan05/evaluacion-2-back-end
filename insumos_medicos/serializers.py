"""Validación y representación JSON de catálogo, carros y solicitudes."""

from django.utils import timezone
from rest_framework import serializers

from .models import (
    CartItem,
    Category,
    Dispatch,
    Order,
    OrderItem,
    Supply,
)


class CategorySerializer(serializers.ModelSerializer):
    class Meta:
        model = Category
        fields = ['id', 'name']
        read_only_fields = ['id']


class SupplySerializer(serializers.ModelSerializer):
    """Evita lotes vencidos y reserva la edición del stock al personal autorizado."""

    category = serializers.StringRelatedField(read_only=True)
    category_id = serializers.PrimaryKeyRelatedField(
        queryset=Category.objects.all(),
        source='category',
        write_only=True,
    )

    class Meta:
        model = Supply
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
        if value < timezone.localdate():
            raise serializers.ValidationError('La fecha de vencimiento debe ser futura.')
        return value


class CartItemSerializer(serializers.ModelSerializer):
    """Acepta cantidades positivas sin descontarlas del inventario."""

    supply = SupplySerializer(read_only=True)
    supply_id = serializers.PrimaryKeyRelatedField(
        queryset=Supply.objects.select_related('category').all(),
        source='supply',
        write_only=True,
    )

    class Meta:
        model = CartItem
        fields = ['id', 'supply', 'supply_id', 'quantity_boxes']
        read_only_fields = ['id']

    def validate_quantity_boxes(self, value):
        if value < 1:
            raise serializers.ValidationError('La cantidad debe ser al menos una caja.')
        return value


class OrderItemSerializer(serializers.ModelSerializer):
    subtotal = serializers.DecimalField(
        max_digits=12,
        decimal_places=2,
        read_only=True,
    )

    class Meta:
        model = OrderItem
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


class DispatchSerializer(serializers.ModelSerializer):
    class Meta:
        model = Dispatch
        fields = ['status', 'created_at', 'delivered_at']
        read_only_fields = fields


class OrderSerializer(serializers.ModelSerializer):
    """Representa el histórico inmutable y su estado de despacho."""

    items = OrderItemSerializer(many=True, read_only=True)
    dispatch = DispatchSerializer(read_only=True)

    class Meta:
        model = Order
        fields = ['id', 'status', 'created_at', 'total', 'items', 'dispatch']
        read_only_fields = fields


class OrderStatusSerializer(serializers.Serializer):
    status = serializers.ChoiceField(
        choices=[Order.Status.DELIVERED, Order.Status.CANCELLED]
    )
