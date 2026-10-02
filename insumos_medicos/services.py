"""Operaciones de dominio que deben preservar el inventario de forma atómica."""

from django.db import transaction
from django.utils import timezone

from .models import Cart, Dispatch, Order, OrderItem, Supply


class OrderRequestError(Exception):
    pass


@transaction.atomic
def create_paid_order(user):
    """Valida todos los lotes antes de pagar, descontar stock y crear despacho."""
    cart, _ = Cart.objects.select_for_update().get_or_create(user=user)
    cart_items = list(
        cart.items.select_related('supply').order_by('supply_id')
    )
    if not cart_items:
        raise OrderRequestError('El carro de insumos está vacío.')

    supplies = {
        supply.pk: supply
        for supply in Supply.objects.select_for_update()
        .filter(pk__in=[item.supply_id for item in cart_items])
        .order_by('pk')
    }
    total = 0
    for cart_item in cart_items:
        supply = supplies.get(cart_item.supply_id)
        if supply is None:
            raise OrderRequestError('Un insumo ya no está disponible.')
        if supply.expiration_date < timezone.localdate():
            raise OrderRequestError(f'El lote {supply.lot_number} está vencido.')
        if supply.stock_boxes < cart_item.quantity_boxes:
            raise OrderRequestError(
                f'Stock insuficiente para {supply.commercial_name}: '
                f'disponibles {supply.stock_boxes}, '
                f'solicitadas {cart_item.quantity_boxes}.'
            )
        total += supply.price_per_box * cart_item.quantity_boxes

    order = Order.objects.create(
        user=user,
        status=Order.Status.PENDING,
        total=total,
    )
    for cart_item in cart_items:
        supply = supplies[cart_item.supply_id]
        supply.stock_boxes -= cart_item.quantity_boxes
        supply.save(update_fields=['stock_boxes'])
        OrderItem.objects.create(
            order=order,
            supply=supply,
            commercial_name=supply.commercial_name,
            lot_number=supply.lot_number,
            quantity_boxes=cart_item.quantity_boxes,
            price_per_box=supply.price_per_box,
        )
    order.status = Order.Status.PAID
    order.save(update_fields=['status'])
    Dispatch.objects.create(order=order)
    cart.items.all().delete()
    return order
