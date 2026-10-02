from django.apps import AppConfig


class AcademicConfig(AppConfig):
    name = 'insumos_medicos'
    label = 'academic'

    def ready(self):
        from . import schema  # noqa: F401
