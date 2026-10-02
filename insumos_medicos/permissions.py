"""Permisos reutilizables para instituciones y gestores de bodega."""

from rest_framework.permissions import BasePermission


def is_warehouse_manager(user):
    return user.is_authenticated and (
        user.is_superuser
        or user.rol in {'GESTOR_BODEGA', 'ADMINISTRADOR'}
    )


class IsWarehouseManager(BasePermission):
    def has_permission(self, request, view):
        return is_warehouse_manager(request.user)


class IsMedicalInstitution(BasePermission):
    def has_permission(self, request, view):
        return (
            request.user.is_authenticated
            and not is_warehouse_manager(request.user)
        )
