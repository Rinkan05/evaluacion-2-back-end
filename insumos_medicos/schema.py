"""Describe JWT como autenticación Bearer en el esquema OpenAPI."""

from drf_spectacular.extensions import OpenApiAuthenticationExtension


class SimpleJWTAuthenticationScheme(OpenApiAuthenticationExtension):
    """Enseña a Swagger UI cómo enviar el JWT en la cabecera HTTP."""

    target_class = 'rest_framework_simplejwt.authentication.JWTAuthentication'
    name = 'BearerAuth'

    def get_security_definition(self, auto_schema):
        """Declara el formato Authorization: Bearer <token>."""
        return {
            'type': 'http',
            'scheme': 'bearer',
            'bearerFormat': 'JWT',
        }
