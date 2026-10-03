"""Filtros públicos para buscar insumos por categoría, precio y lote."""

import django_filters

from .models import Insumo


class SupplyFilter(django_filters.FilterSet):
    """Convierte parámetros de consulta HTTP en filtros del queryset.

    category busca por ID; min_price/max_price son límites inclusivos; el
    principio activo usa búsqueda parcial sin distinguir mayúsculas.
    """

    # Número de categoría, precio mínimo inclusivo y máximo inclusivo.
    category = django_filters.NumberFilter(field_name='category_id')
    min_price = django_filters.NumberFilter(
        field_name='price_per_box',
        lookup_expr='gte',
    )
    max_price = django_filters.NumberFilter(
        field_name='price_per_box',
        lookup_expr='lte',
    )
    # Permite buscar fragmentos del principio activo (por ejemplo, "para").
    active_ingredient = django_filters.CharFilter(lookup_expr='icontains')

    class Meta:
        model = Insumo
        fields = ['category', 'min_price', 'max_price', 'active_ingredient']
