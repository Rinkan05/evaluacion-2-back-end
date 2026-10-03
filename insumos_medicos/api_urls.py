"""Rutas REST para catálogo, carro, solicitudes, usuarios y despacho."""

from django.urls import path

from .api_views import (
    ApiRootView,
    CartItemDetailView,
    CartItemsView,
    CategoryDetailView,
    CategoryListCreateView,
    ConfirmOrderView,
    MyOrdersView,
    OrderStatusView,
    SupplyDetailView,
    SupplyListCreateView,
)


# Rutas y operaciones disponibles (la autorización se define en cada vista):
# - catálogo y categorías para consulta pública y mantenimiento por bodega;
# - carro y checkout para instituciones autenticadas;
# - consulta de solicitudes del cliente y cambio de estado por el gestor.
# Los nombres permiten construir URLs y pruebas con reverse() de Django.
urlpatterns = [
    path('', ApiRootView.as_view(), name='api-root'),
    path('categorias/', CategoryListCreateView.as_view(), name='category-list'),
    path(
        'categorias/<int:pk>/',
        CategoryDetailView.as_view(),
        name='category-detail',
    ),
    path('insumos/', SupplyListCreateView.as_view(), name='supply-list'),
    path('insumos/<int:pk>/', SupplyDetailView.as_view(), name='supply-detail'),
    path('carro-insumos/', CartItemsView.as_view(), name='cart-items'),
    path(
        'carro-insumos/<int:pk>/',
        CartItemDetailView.as_view(),
        name='cart-item-detail',
    ),
    path(
        'solicitudes/confirmar/',
        ConfirmOrderView.as_view(),
        name='confirm-order',
    ),
    path('mis-solicitudes/', MyOrdersView.as_view(), name='my-orders'),
    path(
        'solicitudes/<int:pk>/estado/',
        OrderStatusView.as_view(),
        name='order-status',
    ),
    path(
        'solicitudes/uuid/<uuid:uuid>/estado/',
        OrderStatusView.as_view(),
        name='order-status-by-uuid',
    ),
]
