"""Modelos de usuarios, inventario y solicitudes de abastecimiento."""

import uuid

from django.contrib.auth.models import AbstractUser
from django.db import models


# USUARIO DEL SISTEMA
# Hereda autenticación, contraseña segura y datos de Django. El campo rol
# diferencia las cuentas de instituciones médicas de las cuentas de bodega.
class CustomUser(AbstractUser):
    """Cuenta del sistema; el rol determina si actúa como cliente o gestor."""

    class Role(models.TextChoices):
        # Choices restringe los roles admitidos: se persiste el primer valor
        # y Django presenta la etiqueta legible del segundo.
        INSTITUTION = 'INSTITUCION_MEDICA', 'Cliente'
        WAREHOUSE_MANAGER = 'GESTOR_BODEGA', 'Gestor de bodega'

    rol = models.CharField(
        'rol',
        max_length=24,
        choices=Role.choices,
        default=Role.INSTITUTION,
    )

    class Meta:
        verbose_name = 'usuario'
        verbose_name_plural = 'usuarios'

    def __str__(self):
        return f'{self.username} ({self.get_rol_display()})'


# CATEGORÍA DEL CATÁLOGO
# Agrupa lotes de insumos y evita nombres repetidos para una misma categoría.
class Categoria(models.Model):
    """Clasifica el catálogo, por ejemplo medicamentos o material quirúrgico."""

    name = models.CharField('nombre', max_length=100, unique=True)

    class Meta:
        ordering = ['name']
        verbose_name = 'categoría'
        verbose_name_plural = 'categorías'

    def __str__(self):
        return self.name


# LOTE INVENTARIABLE
# Cada registro representa un producto y lote concretos. Conserva principio
# activo, precio y vencimiento; las restricciones protegen la integridad del stock.
class Insumo(models.Model):
    """Lote inventariable con trazabilidad, precio, vencimiento y stock."""

    category = models.ForeignKey(
        Categoria,
        # Relación muchos-insumos-a-una-categoría; PROTECT evita dejar lotes
        # sin clasificación si alguien intenta borrar una categoría en uso.
        on_delete=models.PROTECT,
        related_name='supplies',
        verbose_name='categoría',
    )
    commercial_name = models.CharField('nombre comercial', max_length=150)
    active_ingredient = models.CharField('principio activo', max_length=150)
    lot_number = models.CharField('número de lote', max_length=80)
    expiration_date = models.DateField('fecha de vencimiento')
    price_per_box = models.DecimalField(
        'precio por caja',
        max_digits=10,
        decimal_places=2,
    )
    stock_boxes = models.PositiveIntegerField('cajas disponibles', default=0)
    created_at = models.DateTimeField('fecha de creación', auto_now_add=True)

    class Meta:
        ordering = ['commercial_name', 'lot_number']
        verbose_name = 'insumo'
        verbose_name_plural = 'insumos'
        constraints = [
            # Impide registrar dos veces el mismo lote del mismo producto.
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


# CARRO PERSISTENTE
# La relación uno a uno mantiene un solo carro por usuario en PostgreSQL.
# Guardar productos aquí no descuenta ni reserva existencias.
class Carro(models.Model):
    """Carro persistente: cada usuario tiene como máximo un carro en la DB."""

    user = models.OneToOneField(
        CustomUser,
        # OneToOne garantiza persistencia vinculada al usuario, independiente
        # de la sesión del navegador; borrar el usuario elimina su carro.
        on_delete=models.CASCADE,
        related_name='cart',
        verbose_name='usuario',
    )
    created_at = models.DateTimeField('fecha de creación', auto_now_add=True)

    class Meta:
        verbose_name = 'carro de abastecimiento'
        verbose_name_plural = 'carros de abastecimiento'

    def __str__(self):
        return f'Carro de {self.user.username}'


# LÍNEA DEL CARRO
# Relaciona el carro con el lote seleccionado y la cantidad pedida en cajas.
# Las restricciones impiden duplicar lotes y guardar cantidades no positivas.
class ItemCarro(models.Model):
    """Cantidad de cajas de un insumo solicitada en un carro; no reserva stock."""

    cart = models.ForeignKey(
        Carro,
        # Un carro contiene muchas líneas; su eliminación limpia las líneas.
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='carro',
    )
    supply = models.ForeignKey(
        Insumo,
        # Cada línea apunta a un lote. La restricción única más abajo impide
        # repetir el mismo lote dentro del mismo carro.
        on_delete=models.CASCADE,
        related_name='cart_items',
        verbose_name='insumo',
    )
    quantity_boxes = models.PositiveIntegerField('cantidad de cajas')

    class Meta:
        verbose_name = 'ítem del carro'
        verbose_name_plural = 'ítems del carro'
        constraints = [
            # La clave compuesta garantiza una sola línea por lote y carro.
            models.UniqueConstraint(
                fields=['cart', 'supply'],
                name='unique_supply_in_cart',
            ),
            models.CheckConstraint(
                condition=models.Q(quantity_boxes__gt=0),
                name='cart_quantity_positive',
            ),
        ]


# SOLICITUD HISTÓRICA
# Registra al cliente, total y estado del ciclo de vida. Los estados se declaran
# con TextChoices para limitar los valores y presentar etiquetas en español.
class Solicitud(models.Model):
    """Registro histórico de una compra y su ciclo de vida."""

    # Identificador público globalmente único para compartir y consultar la
    # solicitud sin reemplazar la PK numérica usada por las relaciones internas.
    uuid = models.UUIDField(
        default=uuid.uuid4,
        unique=True,
        editable=False,
        verbose_name='identificador único',
    )

    # Estados válidos del proceso. En el checkout PENDIENTE es interno a la
    # transacción; el registro se confirma como PAGADO con el stock descontado.
    class Status(models.TextChoices):
        PENDING = 'PENDIENTE', 'Pendiente'
        PAID = 'PAGADO', 'Pagado'
        DELIVERED = 'ENTREGADO', 'Entregado'
        CANCELLED = 'CANCELADO', 'Cancelado'

    user = models.ForeignKey(
        CustomUser,
        # Una institución puede tener muchas solicitudes; PROTECT conserva
        # el historial aunque se intente eliminar la cuenta asociada.
        on_delete=models.PROTECT,
        related_name='orders',
        verbose_name='institución',
    )
    status = models.CharField(
        'estado',
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField('fecha de creación', auto_now_add=True)
    total = models.DecimalField('total', max_digits=12, decimal_places=2, default=0)

    class Meta:
        ordering = ['-created_at', '-id']
        verbose_name = 'solicitud de abastecimiento'
        verbose_name_plural = 'solicitudes de abastecimiento'

    def __str__(self):
        return f'Solicitud #{self.pk} - {self.user.username} ({self.status})'


# DETALLE HISTÓRICO DE SOLICITUD
# Copia nombre, lote, cantidad y precio al momento de compra: el historial sigue
# siendo correcto aunque posteriormente cambie el catálogo.
class DetalleSolicitud(models.Model):
    """Copia de los datos comerciales de cada línea para conservar el historial."""

    order = models.ForeignKey(
        Solicitud,
        # Una solicitud agrupa varias líneas de detalle.
        on_delete=models.CASCADE,
        related_name='items',
        verbose_name='solicitud',
    )
    supply = models.ForeignKey(
        Insumo,
        # Se conserva la referencia al lote original: no se puede borrar si
        # aparece en el historial de una solicitud.
        on_delete=models.PROTECT,
        related_name='order_items',
        verbose_name='insumo',
    )
    commercial_name = models.CharField('nombre comercial', max_length=150)
    lot_number = models.CharField('número de lote', max_length=80)
    quantity_boxes = models.PositiveIntegerField('cantidad de cajas')
    price_per_box = models.DecimalField(
        'precio por caja',
        max_digits=10,
        decimal_places=2,
    )

    class Meta:
        verbose_name = 'detalle de solicitud'
        verbose_name_plural = 'detalles de solicitud'

    @property
    def subtotal(self):
        """Calcula el importe de la línea con el precio histórico registrado."""
        return self.quantity_boxes * self.price_per_box


# DESPACHO
# Mantiene el seguimiento logístico de una solicitud, su estado y fechas.
# La relación uno a uno evita generar varios despachos para una misma compra.
class Despacho(models.Model):
    """Seguimiento logístico uno a uno asociado con una solicitud pagada."""

    class Status(models.TextChoices):
        # El estado logístico se sincroniza con el de la solicitud.
        PENDING = 'PENDIENTE', 'Pendiente'
        DELIVERED = 'ENTREGADO', 'Entregado'
        CANCELLED = 'CANCELADO', 'Cancelado'

    order = models.OneToOneField(
        Solicitud,
        # Un despacho por solicitud; CASCADE elimina el seguimiento si se
        # elimina la solicitud.
        on_delete=models.CASCADE,
        related_name='dispatch',
        verbose_name='solicitud',
    )
    status = models.CharField(
        'estado',
        max_length=12,
        choices=Status.choices,
        default=Status.PENDING,
    )
    created_at = models.DateTimeField('fecha de creación', auto_now_add=True)
    delivered_at = models.DateTimeField('fecha de entrega', null=True, blank=True)

    class Meta:
        verbose_name = 'despacho'
        verbose_name_plural = 'despachos'
