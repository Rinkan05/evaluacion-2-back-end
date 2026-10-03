"""Registro de la aplicación de dominio en Django."""

from django.apps import AppConfig


class AcademicConfig(AppConfig):
    """Conserva la etiqueta histórica y registra extensiones al iniciar el proyecto."""

    name = 'insumos_medicos'
    label = 'academic'

    def ready(self):
        """Importa el esquema para que DRF Spectacular lo registre."""
        # Este proyecto no define receptores de señales; solo carga la extensión
        # OpenAPI al iniciar Django.
        from . import schema  # noqa: F401
