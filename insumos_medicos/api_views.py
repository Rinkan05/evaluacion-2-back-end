"""Endpoints con permisos por rol y operaciones transaccionales de inventario."""

from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import Carro, Categoria, Insumo, Solicitud
from .filters import SupplyFilter
from .permissions import IsMedicalInstitution, IsWarehouseManager
from .serializers import (
    CartItemSerializer,
    CategorySerializer,
    OrderSerializer,
    OrderStatusSerializer,
    SupplySerializer,
)
from .services import (
    OrderRequestError,
    change_order_status,
    create_paid_order,
)


# DIRECTORIO PÚBLICO
# Entrega enlaces de descubrimiento para que un cliente conozca las rutas de la API.
class ApiRootView(APIView):
    """Directorio público con enlaces a las operaciones de la API."""

    permission_classes = [AllowAny]

    @extend_schema(responses=dict)
    def get(self, request):
        """Devuelve URLs absolutas para facilitar explorar los endpoints."""
        return Response({
            'categorias': request.build_absolute_uri('/api/categorias/'),
            'insumos': request.build_absolute_uri('/api/insumos/'),
            'carro_insumos': request.build_absolute_uri('/api/carro-insumos/'),
            'confirmar_solicitud': request.build_absolute_uri(
                '/api/solicitudes/confirmar/'
            ),
            'mis_solicitudes': request.build_absolute_uri('/api/mis-solicitudes/'),
        })


# POLÍTICA COMÚN PARA LISTAS Y DETALLES DEL CATÁLOGO
# Consultar es público; crear, modificar o borrar exige el rol de gestor.
class RoleBasedListCreateView(generics.ListCreateAPIView):
    """Hace pública la lectura de listas y restringe las escrituras al gestor.

    Las vistas de categorías e insumos heredan esta regla según el método HTTP.
    """

    def get_permissions(self):
        """GET es público; las escrituras requieren rol de gestor de bodega."""
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsWarehouseManager()]


class RoleBasedDetailView(generics.RetrieveUpdateDestroyAPIView):
    """Hace público el detalle leído y limita cambios/eliminación a bodega."""

    def get_permissions(self):
        """GET es público y los cambios/eliminaciones requieren rol de bodega."""
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsWarehouseManager()]


# CATEGORÍAS
# Reutilizan la política común para exponer lectura pública y escritura autorizada.
class CategoryListCreateView(RoleBasedListCreateView):
    """Lista categorías públicamente y reserva su creación a bodega."""

    queryset = Categoria.objects.all()
    serializer_class = CategorySerializer


class CategoryDetailView(RoleBasedDetailView):
    """Lee una categoría o permite que bodega la edite y elimine."""

    queryset = Categoria.objects.all()
    serializer_class = CategorySerializer

    def destroy(self, request, *args, **kwargs):
        """Evita eliminar categorías que todavía tienen insumos asociados."""
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {'detail': 'No se puede eliminar una categoría que tiene insumos.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# CATÁLOGO DE LOTES
# Expone solo insumos vigentes y con existencias; agrega filtros de búsqueda.
class SupplyListCreateView(RoleBasedListCreateView):
    """Expone el catálogo público y reserva escritura al gestor."""

    serializer_class = SupplySerializer
    # django-filter aplica category, min_price, max_price y active_ingredient
    # al queryset público, después de excluir lotes vencidos o sin stock.
    filterset_class = SupplyFilter

    def get_queryset(self):
        """El catálogo público incluye solo lotes vigentes con stock positivo."""
        return Insumo.objects.select_related('category').filter(
            stock_boxes__gt=0,
            expiration_date__gte=timezone.localdate(),
        )


class SupplyDetailView(RoleBasedDetailView):
    """Administra el detalle de un lote según los permisos de rol."""

    http_method_names = ['get', 'put', 'delete', 'head', 'options']
    queryset = Insumo.objects.select_related('category').all()
    serializer_class = SupplySerializer

    def destroy(self, request, *args, **kwargs):
        """Protege el historial rechazando borrar lotes ligados a solicitudes."""
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {'detail': 'No se puede eliminar un insumo asociado a una solicitud.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


# CARRO DEL CLIENTE
# Los métodos consultan, agregan/actualizan o vacían únicamente el carro propio.
class CartItemsView(APIView):
    """Mantiene el carro de la institución en base de datos entre sesiones."""

    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    def get_cart(self, user):
        """Obtiene el carro guardado en DB, creando uno si aún no existe."""
        cart, _ = Carro.objects.get_or_create(user=user)
        return cart

    @extend_schema(responses=CartItemSerializer(many=True))
    def get(self, request):
        """Lista las líneas del carro propio del usuario autenticado."""
        cart = self.get_cart(request.user)
        items = cart.items.select_related('supply__category').all()
        return Response(CartItemSerializer(items, many=True).data)

    @extend_schema(
        request=CartItemSerializer,
        responses={200: CartItemSerializer, 201: CartItemSerializer},
    )
    def post(self, request):
        """Agrega o actualiza un insumo y su cantidad en el carro propio."""
        serializer = CartItemSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        supply = serializer.validated_data['supply']
        if supply.expiration_date < timezone.localdate():
            raise ValidationError({'supply_id': 'El lote está vencido.'})
        cart = self.get_cart(request.user)
        item, created = cart.items.get_or_create(
            supply=supply,
            defaults={
                'quantity_boxes': serializer.validated_data['quantity_boxes'],
            },
        )
        if not created:
            item.quantity_boxes = serializer.validated_data['quantity_boxes']
            item.save(update_fields=['quantity_boxes'])
        return Response(
            CartItemSerializer(item).data,
            status=status.HTTP_201_CREATED if created else status.HTTP_200_OK,
        )

    @extend_schema(operation_id='clearCartItems', responses={204: None})
    def delete(self, request):
        """Vacía todas las líneas del carro propio."""
        cart = self.get_cart(request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemDetailView(APIView):
    """Elimina una línea solo si pertenece al carro del usuario autenticado."""

    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    @extend_schema(operation_id='deleteCartItem', responses={204: None})
    def delete(self, request, pk):
        """Busca la línea dentro del carro propio antes de borrarla."""
        cart = get_object_or_404(Carro, user=request.user)
        item = get_object_or_404(cart.items, pk=pk)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


# CHECKOUT
# Delega al servicio de dominio la validación, pago y descuento de stock.
class ConfirmOrderView(APIView):
    """Confirma una solicitud con validación atómica y descuento de stock."""

    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    @extend_schema(request=None, responses={201: OrderSerializer})
    def post(self, request):
        """Delega en el servicio compartido por la página y la API."""
        try:
            order = create_paid_order(request.user)
        except OrderRequestError as exc:
            raise ValidationError({'detail': str(exc)}) from exc

        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


# HISTORIAL DEL CLIENTE
# La consulta se limita al usuario autenticado; no acepta IDs de otros clientes.
class MyOrdersView(generics.ListAPIView):
    """Muestra únicamente el historial de solicitudes del usuario autenticado."""

    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    def get_queryset(self):
        """Limita el historial al usuario autenticado y precarga sus relaciones."""
        if getattr(self, 'swagger_fake_view', False):
            return Solicitud.objects.none()
        return (
            Solicitud.objects.filter(user=self.request.user)
            .prefetch_related('items', 'dispatch')
        )


# TRANSICIÓN DE ESTADOS
# Solo el gestor puede entregar o cancelar una solicitud pagada; cancelar repone
# los lotes originales y sincroniza el registro del despacho.
class OrderStatusView(APIView):
    """El gestor entrega o cancela; la cancelación restituye existencias.

    El bloqueo de solicitud e inventario evita transiciones duplicadas o
    reposiciones parciales cuando hay solicitudes concurrentes.
    """

    permission_classes = [IsAuthenticated, IsWarehouseManager]

    @extend_schema(
        request=OrderStatusSerializer,
        responses=OrderSerializer,
    )
    def patch(self, request, pk=None, uuid=None):
        """Valida el estado y delega la transición atómica al servicio común."""
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_status = serializer.validated_data['status']
        try:
            order = change_order_status(
                uuid if uuid is not None else pk,
                target_status,
                uuid_lookup=uuid is not None,
            )
        except OrderRequestError as exc:
            raise ValidationError({'status': str(exc)}) from exc
        return Response(OrderSerializer(order).data)
