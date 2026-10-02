from django.contrib import admin
from django.urls import include, path
from drf_spectacular.views import (
    SpectacularAPIView,
    SpectacularSwaggerView,
)
from rest_framework.permissions import AllowAny
from rest_framework_simplejwt.views import TokenRefreshView
from rest_framework_simplejwt.views import TokenObtainPairView as BaseTokenObtainPairView

from insumos_medicos import views
from insumos_medicos.tokens import RoleTokenObtainPairSerializer


class TokenObtainPairView(BaseTokenObtainPairView):
    serializer_class = RoleTokenObtainPairSerializer


urlpatterns = [
    path('admin/', admin.site.urls),
    path('api/', include('insumos_medicos.api_urls')),
    path('api/token/', TokenObtainPairView.as_view(), name='token-obtain-pair'),
    path('api/token/refresh/', TokenRefreshView.as_view(), name='token-refresh'),
    path(
        'api/schema/',
        SpectacularAPIView.as_view(permission_classes=[AllowAny]),
        name='schema',
    ),
    path(
        'api/docs/',
        SpectacularSwaggerView.as_view(
            url_name='schema',
            permission_classes=[AllowAny],
        ),
        name='swagger-ui',
    ),
    path('', views.pagina_inicio, name='inicio'),
    path('quienes-somos/', views.quienes_somos, name='quienes-somos'),
    path('servicios/', views.servicios, name='servicios'),
    path('contacto/', views.contacto, name='contacto'),
    path('registro/', views.registrar_usuario, name='registro'),
    path('iniciar-sesion/', views.iniciar_sesion, name='iniciar-sesion'),
    path('acceso-superusuario/', views.iniciar_sesion, name='acceso-superusuario'),
    path('personal/', views.panel_personal, name='panel-personal'),
    path('cerrar-sesion/', views.cerrar_sesion, name='cerrar-sesion'),
    path('gestion-interna/', views.gestionar_interno, name='gestion-interna'),
    path('carrito/', views.carrito, name='carrito'),
    path(
        'carrito/agregar/<int:insumo_id>/',
        views.agregar_carrito,
        name='agregar-carrito',
    ),
    path('carrito/actualizar/', views.actualizar_carrito, name='actualizar-carrito'),
    path(
        'carrito/eliminar/<int:insumo_id>/',
        views.eliminar_del_carrito,
        name='eliminar-carrito',
    ),
    path('carrito/finalizar/', views.finalizar_compra, name='finalizar-compra'),
    path('mis-solicitudes/', views.mis_solicitudes, name='mis-solicitudes'),
    path('<path:unknown_path>', views.pagina_inicio, name='fallback'),
]
