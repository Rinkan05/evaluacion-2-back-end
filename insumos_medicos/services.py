"""Operaciones de dominio que deben preservar el inventario de forma atómica."""

from django.db import transaction
from django.shortcuts import get_object_or_404
from django.utils import timezone

from .models import Carro, Despacho, DetalleSolicitud, Insumo, Solicitud


class OrderRequestError(Exception):
    """Error de negocio esperado al confirmar una solicitud de insumos."""

    pass


@transaction.atomic
def create_paid_order(user):
    """Valida stock y vencimientos, crea la solicitud y descuenta inventario.

    La transacción atómica hace que cualquier error revierta todos los cambios:
    solicitud, detalles, existencias, despacho y vaciado del carro.
    """
    # Los bloqueos serializan checkouts concurrentes del mismo carro o lote;
    # así dos instituciones no pueden consumir simultáneamente las mismas cajas.
    cart, _ = Carro.objects.select_for_update().get_or_create(user=user)
    cart_items = list(
        cart.items.select_related('supply').order_by('supply_id')
    )
    if not cart_items:
        raise OrderRequestError('El carro de insumos está vacío.')

    # Bloquear lotes siempre por PK reduce el riesgo de interbloqueos entre
    # checkouts que incluyan varios productos en distinto orden.
    supplies = {
        supply.pk: supply
        for supply in Insumo.objects.select_for_update()
        .filter(pk__in=[item.supply_id for item in cart_items])
        .order_by('pk')
    }
    total = 0
    # Fase de validación: comprobar todas las líneas antes de cambiar stock.
    # Si cualquiera falla, la excepción revierte la transacción completa.
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

    # El modelo usa la PK automática de Django (entero), no UUID. PENDIENTE
    # solo existe dentro de esta transacción: se confirma como PAGADO junto
    # con el descuento, los detalles, el despacho y el vaciado del carro.
    order = Solicitud.objects.create(
        user=user,
        status=Solicitud.Status.PENDING,
        total=total,
    )
    for cart_item in cart_items:
        supply = supplies[cart_item.supply_id]
        supply.stock_boxes -= cart_item.quantity_boxes
        supply.save(update_fields=['stock_boxes'])
        DetalleSolicitud.objects.create(
            order=order,
            supply=supply,
            commercial_name=supply.commercial_name,
            lot_number=supply.lot_number,
            quantity_boxes=cart_item.quantity_boxes,
            price_per_box=supply.price_per_box,
        )
    order.status = Solicitud.Status.PAID
    order.save(update_fields=['status'])
    Despacho.objects.create(order=order)
    cart.items.all().delete()
    return order


@transaction.atomic
def change_order_status(order_id, target_status, *, uuid_lookup=False):
    """Aplica una transición permitida y sincroniza stock y despacho en una TX."""
    # El bloqueo serializa cambios concurrentes; el chequeo de estado evita
    # procesar de nuevo una cancelación y reponer stock más de una vez.
    orders = Solicitud.objects.select_for_update().prefetch_related('items')
    lookup = {'uuid' if uuid_lookup else 'pk': order_id}
    order = get_object_or_404(
        orders,
        **lookup,
    )
    if order.status == target_status:
        return order
    if order.status != Solicitud.Status.PAID:
        raise OrderRequestError(
            'Solo se puede actualizar una solicitud pagada.'
        )

    dispatch = Despacho.objects.select_for_update().get(order=order)
    if target_status == Solicitud.Status.CANCELLED:
        # Reponer las cantidades históricas de cada lote; se bloquean en orden
        # estable para evitar que cancelaciones simultáneas se pisen.
        supply_ids = [item.supply_id for item in order.items.all()]
        supplies = {
            supply.pk: supply
            for supply in Insumo.objects.select_for_update()
            .filter(pk__in=supply_ids)
            .order_by('pk')
        }
        for item in order.items.all():
            supply = supplies[item.supply_id]
            supply.stock_boxes += item.quantity_boxes
            supply.save(update_fields=['stock_boxes'])
        dispatch.status = Despacho.Status.CANCELLED
    else:
        # Entregar cierra el despacho, pero no altera las existencias.
        dispatch.status = Despacho.Status.DELIVERED
        dispatch.delivered_at = timezone.now()

    order.status = target_status
    order.save(update_fields=['status'])
    dispatch.save(update_fields=['status', 'delivered_at'])
    return order
