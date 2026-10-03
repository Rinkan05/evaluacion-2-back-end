"""Permisos reutilizables para instituciones y gestores de bodega."""

from rest_framework.permissions import BasePermission


def is_warehouse_manager(user):
    """Centraliza RBAC: solo gestores configurados y superusuarios son bodega."""
    return user.is_authenticated and (
        user.is_superuser
        or user.rol in {'GESTOR_BODEGA', 'ADMINISTRADOR'}
    )


class IsWarehouseManager(BasePermission):
    """Restringe operaciones de bodega al personal autorizado."""

    def has_permission(self, request, view):
        """DRF consulta este permiso antes de ejecutar la operación de bodega."""
        return is_warehouse_manager(request.user)


class IsMedicalInstitution(BasePermission):
    """Restringe operaciones de cliente a instituciones autenticadas."""

    def has_permission(self, request, view):
        """Exige sesión autenticada y excluye gestores de las operaciones B2B."""
        return (
            request.user.is_authenticated
            and not is_warehouse_manager(request.user)
        )
