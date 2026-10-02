from django.contrib import admin
from django.contrib.auth.admin import UserAdmin

from .models import (
    Cart,
    CartItem,
    Category,
    CustomUser,
    Dispatch,
    Order,
    OrderItem,
    Supply,
)


@admin.register(CustomUser)
class CustomUserAdmin(UserAdmin):
    fieldsets = UserAdmin.fieldsets + (
        ('Rol de la plataforma', {'fields': ('rol',)}),
    )
    add_fieldsets = UserAdmin.add_fieldsets + (
        ('Rol de la plataforma', {'fields': ('rol',)}),
    )
    list_display = (*UserAdmin.list_display, 'rol')
    list_filter = (*UserAdmin.list_filter, 'rol')


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    search_fields = ['name']


@admin.register(Supply)
class SupplyAdmin(admin.ModelAdmin):
    list_display = (
        'commercial_name',
        'category',
        'active_ingredient',
        'lot_number',
        'expiration_date',
        'price_per_box',
        'stock_boxes',
    )
    list_filter = ['category', 'expiration_date']
    search_fields = ['commercial_name', 'active_ingredient', 'lot_number']


class OrderItemInline(admin.TabularInline):
    model = OrderItem
    extra = 0
    readonly_fields = [
        'supply',
        'commercial_name',
        'lot_number',
        'quantity_boxes',
        'price_per_box',
    ]


@admin.register(Order)
class OrderAdmin(admin.ModelAdmin):
    list_display = ('id', 'user', 'status', 'total', 'created_at')
    list_filter = ['status', 'created_at']
    search_fields = ['user__username', 'user__email']
    inlines = [OrderItemInline]
    readonly_fields = ['user', 'status', 'total', 'created_at']

    def has_delete_permission(self, request, obj=None):
        return False


admin.site.register(Cart)
admin.site.register(CartItem)


@admin.register(Dispatch)
class DispatchAdmin(admin.ModelAdmin):
    list_display = ('order', 'status', 'created_at', 'delivered_at')
    list_filter = ['status', 'created_at']
    readonly_fields = ['order', 'status', 'created_at', 'delivered_at']

    def has_add_permission(self, request):
        return False

    def has_delete_permission(self, request, obj=None):
        return False
