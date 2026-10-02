"""Endpoints con permisos por rol y operaciones transaccionales de inventario."""

from django.db import transaction
from django.db.models.deletion import ProtectedError
from django.shortcuts import get_object_or_404
from django.utils import timezone
from rest_framework import generics, status
from rest_framework.exceptions import ValidationError
from rest_framework.permissions import AllowAny, IsAuthenticated
from rest_framework.response import Response
from rest_framework.views import APIView
from drf_spectacular.utils import extend_schema

from .models import Cart, Category, Dispatch, Order, Supply
from .filters import SupplyFilter
from .permissions import IsMedicalInstitution, IsWarehouseManager
from .serializers import (
    CartItemSerializer,
    CategorySerializer,
    OrderSerializer,
    OrderStatusSerializer,
    SupplySerializer,
)
from .services import OrderRequestError, create_paid_order


class ApiRootView(APIView):
    permission_classes = [AllowAny]

    @extend_schema(responses=dict)
    def get(self, request):
        return Response({
            'categorias': request.build_absolute_uri('/api/categorias/'),
            'insumos': request.build_absolute_uri('/api/insumos/'),
            'carro_insumos': request.build_absolute_uri('/api/carro-insumos/'),
            'confirmar_solicitud': request.build_absolute_uri(
                '/api/solicitudes/confirmar/'
            ),
            'mis_solicitudes': request.build_absolute_uri('/api/mis-solicitudes/'),
        })


class RoleBasedListCreateView(generics.ListCreateAPIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsWarehouseManager()]


class RoleBasedDetailView(generics.RetrieveUpdateDestroyAPIView):
    def get_permissions(self):
        if self.request.method == 'GET':
            return [AllowAny()]
        return [IsWarehouseManager()]


class CategoryListCreateView(RoleBasedListCreateView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer


class CategoryDetailView(RoleBasedDetailView):
    queryset = Category.objects.all()
    serializer_class = CategorySerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {'detail': 'No se puede eliminar una categoría que tiene insumos.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class SupplyListCreateView(RoleBasedListCreateView):
    """Expone el catálogo público y reserva escritura al gestor."""

    serializer_class = SupplySerializer
    filterset_class = SupplyFilter

    def get_queryset(self):
        return Supply.objects.select_related('category').filter(
            stock_boxes__gt=0,
            expiration_date__gte=timezone.localdate(),
        )


class SupplyDetailView(RoleBasedDetailView):
    queryset = Supply.objects.select_related('category').all()
    serializer_class = SupplySerializer

    def destroy(self, request, *args, **kwargs):
        instance = self.get_object()
        try:
            self.perform_destroy(instance)
        except ProtectedError:
            return Response(
                {'detail': 'No se puede eliminar un insumo asociado a una solicitud.'},
                status=status.HTTP_409_CONFLICT,
            )
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemsView(APIView):
    """Mantiene el carro de la institución en base de datos entre sesiones."""

    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    def get_cart(self, user):
        cart, _ = Cart.objects.get_or_create(user=user)
        return cart

    @extend_schema(responses=CartItemSerializer(many=True))
    def get(self, request):
        cart = self.get_cart(request.user)
        items = cart.items.select_related('supply__category').all()
        return Response(CartItemSerializer(items, many=True).data)

    @extend_schema(
        request=CartItemSerializer,
        responses={200: CartItemSerializer, 201: CartItemSerializer},
    )
    def post(self, request):
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
        cart = self.get_cart(request.user)
        cart.items.all().delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class CartItemDetailView(APIView):
    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    @extend_schema(operation_id='deleteCartItem', responses={204: None})
    def delete(self, request, pk):
        cart = get_object_or_404(Cart, user=request.user)
        item = get_object_or_404(cart.items, pk=pk)
        item.delete()
        return Response(status=status.HTTP_204_NO_CONTENT)


class ConfirmOrderView(APIView):
    """Confirma una solicitud con validación atómica y descuento de stock."""

    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    @extend_schema(request=None, responses={201: OrderSerializer})
    def post(self, request):
        try:
            order = create_paid_order(request.user)
        except OrderRequestError as exc:
            raise ValidationError({'detail': str(exc)}) from exc

        return Response(
            OrderSerializer(order).data,
            status=status.HTTP_201_CREATED,
        )


class MyOrdersView(generics.ListAPIView):
    serializer_class = OrderSerializer
    permission_classes = [IsAuthenticated, IsMedicalInstitution]

    def get_queryset(self):
        if getattr(self, 'swagger_fake_view', False):
            return Order.objects.none()
        return (
            Order.objects.filter(user=self.request.user)
            .prefetch_related('items', 'dispatch')
        )


class OrderStatusView(APIView):
    """El gestor entrega o cancela; la cancelación restituye existencias."""

    permission_classes = [IsAuthenticated, IsWarehouseManager]

    @extend_schema(
        request=OrderStatusSerializer,
        responses=OrderSerializer,
    )
    @transaction.atomic
    def patch(self, request, pk):
        serializer = OrderStatusSerializer(data=request.data)
        serializer.is_valid(raise_exception=True)
        target_status = serializer.validated_data['status']
        order = get_object_or_404(
            Order.objects.select_for_update().prefetch_related('items'),
            pk=pk,
        )

        if order.status == target_status:
            return Response(OrderSerializer(order).data)
        if order.status != Order.Status.PAID:
            raise ValidationError({
                'status': 'Solo se puede actualizar una solicitud pagada.'
            })

        dispatch = Dispatch.objects.select_for_update().get(order=order)
        if target_status == Order.Status.CANCELLED:
            supply_ids = [item.supply_id for item in order.items.all()]
            supplies = {
                supply.pk: supply
                for supply in Supply.objects.select_for_update()
                .filter(pk__in=supply_ids)
                .order_by('pk')
            }
            for item in order.items.all():
                supply = supplies[item.supply_id]
                supply.stock_boxes += item.quantity_boxes
                supply.save(update_fields=['stock_boxes'])
            dispatch.status = Dispatch.Status.CANCELLED
        else:
            dispatch.status = Dispatch.Status.DELIVERED
            dispatch.delivered_at = timezone.now()

        order.status = target_status
        order.save(update_fields=['status'])
        dispatch.save(update_fields=['status', 'delivered_at'])
        return Response(OrderSerializer(order).data)
