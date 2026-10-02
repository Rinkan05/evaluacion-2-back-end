"""Filtros públicos para buscar insumos por categoría, precio y lote."""

import django_filters

from .models import Supply


class SupplyFilter(django_filters.FilterSet):
    """Permite acotar el catálogo sin modificar sus datos."""

    category = django_filters.NumberFilter(field_name='category_id')
    min_price = django_filters.NumberFilter(
        field_name='price_per_box',
        lookup_expr='gte',
    )
    max_price = django_filters.NumberFilter(
        field_name='price_per_box',
        lookup_expr='lte',
    )
    active_ingredient = django_filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Supply
        fields = ['category', 'min_price', 'max_price', 'active_ingredient']
