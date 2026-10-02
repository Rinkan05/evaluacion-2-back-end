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
]
