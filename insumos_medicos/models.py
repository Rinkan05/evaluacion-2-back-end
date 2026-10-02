"""Datos B2B del catálogo, el carro persistente y el despacho de solicitudes."""

from django.contrib.auth.models import AbstractUser
from django.db import models


# Identidad y roles que gobiernan el acceso a los flujos de abastecimiento.
class CustomUser(AbstractUser):
    class Role(models.TextChoices):
        INSTITUTION = 'INSTITUCION_MEDICA', 'Institución médica'
        WAREHOUSE_MANAGER = 'GESTOR_BODEGA', 'Gestor de bodega'

    rol = models.CharField(
        max_length=24,
        choices=Role.choices,
        default=Role.INSTITUTION,
    )

    def __str__(self):
        return f'{self.username} ({self.get_rol_display()})'


# Catálogo por categorías y lotes; cada lote conserva inventario y vencimiento.
class Category(models.Model):
    name = models.CharField(max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'categoría'
        verbose_name_plural = 'categorías'

    def __str__(self):
        return self.name


class Supply(models.Model):
    category = models.ForeignKey(
        Category,
        on_delete=models.PROTECT,
        related_name='supplies',
    )
    commercial_name = models.CharField(max_length=150)
    active_ingredient = models.CharField(max_length=150)
    lot_number = models.CharField(max_length=80)
    expiration_date = models.DateField()
    price_per_box = models.DecimalField(max_digits=10, decimal_places=2)
    stock_boxes = models.PositiveIntegerField(default=0)
    created_at = models.DateTimeField(auto_now_add=True)

    class Meta:
        ordering = ['commercial_name', 'lot_number']
        constraints = [
            models.UniqueConstraint(
                fields=['commercial_name', 'lot_number'],
                name='unique_supply_lot',
            ),
            models.CheckConstraint(
                condition=models.Q(price_per_box__gte=0),
                name='supply_price_nonnegative',
            ),
        ]

    def __str__(self):
        return f'{self.commercial_name} (lote {self.lot_number})'


# El carro es persistente y único por institución; no reserva inventario.
class Cart(models.Model):
    user = models.OneToOneField(
        CustomUser,
        on_delete=models.CASCADE,
        related_name='cart',
    )
    created_at = models.DateTimeField(auto_now_add=True)

    def __str__(self):
        return f'Carro de {self.user.username}'


class CartItem(models.Model):
    cart = models.ForeignKey(Cart, on_delete=models.CASCADE, related_name='items')
    supply = models.ForeignKey(Supply, on_delete=models.CASCADE, related_name='cart_items')
    quantity_boxes = models.PositiveIntegerField()

    class Meta:
        constraints = [
            models.UniqueConstraint(
                fields=['cart', 'supply'],
                name='unique_supply_in_cart',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_boxes__gt=0),
                name='cart_quantity_positive',
            ),
        ]


# La orden conserva estados y líneas históricas aun si cambia el catálogo.
class Order(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDIENTE', 'Pendiente'
        PAID = 'PAGADO', 'Pagado'
        DELIVERED = 'ENTREGADO', 'Entregado'
        CANCELLED = 'CANCELADO', 'Cancelado'

    user = models.ForeignKey(
        CustomUser,
        on_delete=models.PROTECT,
        related_name='orders',
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    total = models.DecimalField(max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['-created_at', '-id']

    def __str__(self):
        return f'Solicitud #{self.pk} - {self.user.username} ({self.status})'


class OrderItem(models.Model):
    order = models.ForeignKey(Order, on_delete=models.CASCADE, related_name='items')
    supply = models.ForeignKey(Supply, on_delete=models.PROTECT, related_name='order_items')
    commercial_name = models.CharField(max_length=150)
    lot_number = models.CharField(max_length=80)
    quantity_boxes = models.PositiveIntegerField()
    price_per_box = models.DecimalField(max_digits=10, decimal_places=2)

    @property
    def subtotal(self):
        return self.quantity_boxes * self.price_per_box


# El despacho sigue la transición final de la solicitud pagada.
class Dispatch(models.Model):
    class Status(models.TextChoices):
        PENDING = 'PENDIENTE', 'Pendiente'
        DELIVERED = 'ENTREGADO', 'Entregado'
        CANCELLED = 'CANCELADO', 'Cancelado'

    order = models.OneToOneField(
        Order,
        on_delete=models.CASCADE,
        related_name='dispatch',
    )
    status = models.CharField(
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField(auto_now_add=True)
    delivered_at = models.DateTimeField(null=True, blank=True)
