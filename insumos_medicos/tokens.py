"""Emite access y refresh JWT con el rol B2B incluido como claim."""

from rest_framework_simplejwt.serializers import TokenObtainPairSerializer


class RoleTokenObtainPairSerializer(TokenObtainPairSerializer):
    """Añade al JWT los datos básicos de autorización del usuario."""

    @classmethod
    def get_token(cls, user):
        """Agrega claims al refresh; SimpleJWT los hereda al access token."""
        token = super().get_token(user)
        token['rol'] = user.rol
        token['username'] = user.username
        return token

    def validate(self, attrs):
        """Devuelve el rol junto a los tokens para que el cliente identifique su perfil."""
        data = super().validate(attrs)
        data['rol'] = self.user.rol
        return data
