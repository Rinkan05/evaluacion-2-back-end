from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken, RefreshToken

from .models import Carro, Categoria, Despacho, Insumo, Solicitud
from .services import create_paid_order


User = get_user_model()


class SupplyApiTests(APITestCase):
    """Pruebas de integración REST para catálogo, JWT, roles y pedidos."""

    def setUp(self):
        """Crea datos aislados que cada test puede usar y revertir."""
        self.institution = User.objects.create_user(
            username='clinica',
            password='test-password',
            rol=User.Role.INSTITUTION,
        )
        self.manager = User.objects.create_user(
            username='bodega',
            password='test-password',
            rol=User.Role.WAREHOUSE_MANAGER,
        )
        self.category = Categoria.objects.create(name='Medicamentos')
        self.supply = Insumo.objects.create(
            category=self.category,
            commercial_name='Paracetamol',
            active_ingredient='Paracetamol',
            lot_number='LOTE-01',
            expiration_date=timezone.localdate() + timedelta(days=90),
            price_per_box=Decimal('1200.00'),
            stock_boxes=10,
        )

    def test_registration_creates_the_configured_custom_user(self):
        """El registro web debe guardar usuarios usando el modelo activo del proyecto."""
        response = self.client.post(
            reverse('registro'),
            {
                'username': 'nueva_clinica',
                'password1': 'Clinica-Password-2026',
                'password2': 'Clinica-Password-2026',
            },
        )

        self.assertRedirects(response, reverse('inicio'))
        created_user = User.objects.get(username='nueva_clinica')
        self.assertEqual(created_user.rol, User.Role.INSTITUTION)

    def test_master_superuser_can_create_users_with_either_business_role(self):
        """El superusuario maestro crea cuentas y asigna uno de los dos roles."""
        master = User.objects.create_superuser(
            username='admin_maestro',
            email='admin@example.test',
            password='Master-Password-2026',
        )
        self.client.force_login(master)
        add_user_url = reverse('admin:academic_customuser_add')

        response = self.client.get(add_user_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'rol')

        for username, role in (
            ('institucion_admin', User.Role.INSTITUTION),
            ('gestor_admin', User.Role.WAREHOUSE_MANAGER),
        ):
            with self.subTest(role=role):
                response = self.client.post(
                    add_user_url,
                    {
                        'username': username,
                        'password1': 'New-Account-Password-2026',
                        'password2': 'New-Account-Password-2026',
                        'rol': role,
                    },
                )
                self.assertEqual(response.status_code, 302)
                created_user = User.objects.get(username=username)
                self.assertEqual(created_user.rol, role)
                self.assertFalse(created_user.is_staff)
                self.assertFalse(created_user.is_superuser)

    def test_non_superuser_cannot_manage_accounts_in_django_admin(self):
        """Una cuenta de gestor no puede entrar a la administración de usuarios."""
        staff_manager = User.objects.create_user(
            username='gestor_staff',
            password='test-password',
            rol=User.Role.WAREHOUSE_MANAGER,
            is_staff=True,
        )
        self.client.force_login(staff_manager)
        response = self.client.get(
            reverse('admin:academic_customuser_add')
        )
        self.assertEqual(response.status_code, 403)

    def test_catalog_is_public_and_writes_require_warehouse_manager(self):
        """Verifica lectura pública y escritura de categorías solo para bodega."""
        response = self.client.get(reverse('supply-list'))
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data[0]['commercial_name'], 'Paracetamol')

        self.client.force_authenticate(self.institution)
        response = self.client.post(
            reverse('category-list'),
            {'name': 'Material quirúrgico'},
        )
        self.assertEqual(response.status_code, 403)

        self.client.force_authenticate(self.manager)
        response = self.client.post(
            reverse('category-list'),
            {'name': 'Material quirúrgico'},
        )
        self.assertEqual(response.status_code, 201)

    def test_jwt_token_includes_user_role_claim(self):
        """Comprueba tokens, claims de rol y renovación del access token."""
        response = self.client.post(
            reverse('token-obtain-pair'),
            {'username': self.institution.username, 'password': 'test-password'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['rol'], User.Role.INSTITUTION)
        token = AccessToken(response.data['access'])
        self.assertEqual(token['rol'], User.Role.INSTITUTION)
        self.assertEqual(token['username'], self.institution.username)
        refresh_token = RefreshToken(response.data['refresh'])
        self.assertEqual(refresh_token['rol'], User.Role.INSTITUTION)

        refresh_response = self.client.post(
            reverse('token-refresh'),
            {'refresh': response.data['refresh']},
        )
        self.assertEqual(refresh_response.status_code, 200)
        refreshed_access = AccessToken(refresh_response.data['access'])
        self.assertEqual(refreshed_access['rol'], User.Role.INSTITUTION)

    def test_jwt_permissions_are_enforced_by_user_role(self):
        """Prueba endpoints con Bearer y verifica acceso según cada rol."""
        self.assertEqual(self.client.get(reverse('supply-list')).status_code, 200)
        self.assertEqual(self.client.get(reverse('cart-items')).status_code, 401)
        self.assertEqual(self.client.post(reverse('confirm-order')).status_code, 401)

        institution_tokens = self.client.post(
            reverse('token-obtain-pair'),
            {'username': self.institution.username, 'password': 'test-password'},
        )
        self.assertEqual(institution_tokens.status_code, 200)
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {institution_tokens.data["access"]}'
        )
        self.assertEqual(self.client.get(reverse('cart-items')).status_code, 200)
        cart_response = self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 1},
        )
        self.assertEqual(cart_response.status_code, 201)
        self.assertEqual(
            self.client.post(
                reverse('category-list'),
                {'name': 'Material quirúrgico'},
            ).status_code,
            403,
        )

        order_response = self.client.post(reverse('confirm-order'))
        self.assertEqual(order_response.status_code, 201)
        order_id = order_response.data['id']
        self.assertEqual(
            self.client.patch(
                reverse('order-status', args=[order_id]),
                {'status': Solicitud.Status.DELIVERED},
            ).status_code,
            403,
        )

        manager_tokens = self.client.post(
            reverse('token-obtain-pair'),
            {'username': self.manager.username, 'password': 'test-password'},
        )
        self.assertEqual(manager_tokens.status_code, 200)
        self.assertEqual(manager_tokens.data['rol'], User.Role.WAREHOUSE_MANAGER)
        manager_access = AccessToken(manager_tokens.data['access'])
        self.assertEqual(manager_access['rol'], User.Role.WAREHOUSE_MANAGER)
        self.client.credentials(
            HTTP_AUTHORIZATION=f'Bearer {manager_tokens.data["access"]}'
        )
        supply_response = self.client.post(
            reverse('supply-list'),
            {
                'category_id': self.category.pk,
                'commercial_name': 'Guantes de nitrilo',
                'active_ingredient': 'Nitrilo',
                'lot_number': 'GUANTE-JWT-01',
                'expiration_date': (
                    timezone.localdate() + timedelta(days=365)
                ).isoformat(),
                'price_per_box': '2500.00',
                'stock_boxes': 5,
            },
        )
        self.assertEqual(supply_response.status_code, 201)
        self.assertEqual(
            self.client.patch(
                reverse('order-status', args=[order_id]),
                {'status': Solicitud.Status.DELIVERED},
            ).status_code,
            200,
        )
        self.assertEqual(self.client.get(reverse('cart-items')).status_code, 403)

    def test_catalog_page_and_persistent_cart_render(self):
        """Verifica que la página carga y el carro persiste al cerrar sesión."""
        self.client.force_login(self.institution)
        response = self.client.get(reverse('inicio'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paracetamol')
        self.assertContains(response, 'Maximiliano Solis')
        self.assertContains(response, 'AP-N4-C1')
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 2},
        )
        response = self.client.get(reverse('carrito'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, '2')
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 10)

        self.client.get(reverse('cerrar-sesion'))
        self.client.force_login(self.institution)
        response = self.client.get(reverse('carrito'))
        self.assertContains(response, '2')

    def test_catalog_filter_supports_category_and_price_range(self):
        """Comprueba los filtros de categoría y rango de precios del catálogo."""
        response = self.client.get(
            reverse('supply-list'),
            {'category': self.category.pk, 'min_price': '1000', 'max_price': '1500'},
        )
        self.assertEqual(response.status_code, 200)
        self.assertEqual(len(response.data), 1)

        response = self.client.get(
            reverse('supply-list'),
            {'min_price': '1500'},
        )
        self.assertEqual(response.data, [])

    def test_openapi_schema_and_swagger_ui_are_available(self):
        """Verifica el esquema, el requisito Bearer y la interfaz Swagger."""
        response = self.client.get(reverse('schema'))
        self.assertEqual(response.status_code, 200)
        self.assertIn('/api/insumos/', response.data['paths'])
        self.assertIn('BearerAuth', response.data['components']['securitySchemes'])
        protected = response.data['paths']['/api/carro-insumos/']['get']
        self.assertEqual(protected['security'], [{'BearerAuth': []}])
        public = response.data['paths']['/api/insumos/']['get']
        self.assertIn({}, public['security'])
        response = self.client.get(reverse('swagger-ui'))
        self.assertEqual(response.status_code, 200)

    def test_expired_lots_are_not_listed_or_added_to_cart(self):
        """Impide mostrar o añadir al carro un lote cuya fecha ya pasó."""
        expired_supply = Insumo.objects.create(
            category=self.category,
            commercial_name='Suero vencido',
            active_ingredient='Cloruro de sodio',
            lot_number='LOTE-VENCIDO',
            expiration_date=timezone.localdate() - timedelta(days=1),
            price_per_box=Decimal('500.00'),
            stock_boxes=5,
        )
        response = self.client.get(reverse('supply-list'))
        self.assertEqual(len(response.data), 1)

        self.client.force_authenticate(self.institution)
        response = self.client.post(
            reverse('cart-items'),
            {'supply_id': expired_supply.pk, 'quantity_boxes': 1},
        )
        self.assertEqual(response.status_code, 400)

    def test_manager_can_create_and_delete_supply(self):
        """Comprueba que un gestor puede dar de alta y borrar un lote."""
        self.client.force_authenticate(self.manager)
        response = self.client.post(
            reverse('supply-list'),
            {
                'category_id': self.category.pk,
                'commercial_name': 'Guantes',
                'active_ingredient': 'Nitrilo',
                'lot_number': 'GUANTE-01',
                'expiration_date': (
                    timezone.localdate() + timedelta(days=365)
                ).isoformat(),
                'price_per_box': '2500.00',
                'stock_boxes': 30,
            },
        )
        self.assertEqual(response.status_code, 201)
        supply_id = response.data['id']
        response = self.client.delete(
            reverse('supply-detail', args=[supply_id])
        )
        self.assertEqual(response.status_code, 204)

    def test_supply_detail_requires_put_instead_of_patch(self):
        """La matriz de roles permite PUT del gestor, pero no PATCH parcial."""
        self.client.force_authenticate(self.manager)
        detail_url = reverse('supply-detail', args=[self.supply.pk])
        response = self.client.patch(
            detail_url,
            {'stock_boxes': 15},
        )
        self.assertEqual(response.status_code, 405)

        response = self.client.put(
            detail_url,
            {
                'category_id': self.category.pk,
                'commercial_name': self.supply.commercial_name,
                'active_ingredient': self.supply.active_ingredient,
                'lot_number': self.supply.lot_number,
                'expiration_date': self.supply.expiration_date.isoformat(),
                'price_per_box': str(self.supply.price_per_box),
                'stock_boxes': 15,
            },
        )
        self.assertEqual(response.status_code, 200)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 15)

    def test_cart_supports_item_and_collection_deletion(self):
        """Valida eliminación individual y vaciado completo del carro."""
        self.client.force_authenticate(self.institution)
        response = self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 2},
        )
        item_id = response.data['id']
        response = self.client.delete(
            reverse('cart-item-detail', args=[item_id])
        )
        self.assertEqual(response.status_code, 204)

        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 2},
        )
        response = self.client.delete(reverse('cart-items'))
        self.assertEqual(response.status_code, 204)
        self.assertFalse(Carro.objects.get(user=self.institution).items.exists())

    def test_confirming_request_deducts_stock_and_creates_dispatch(self):
        """Confirma que el pago crea historial/despacho y descuenta existencias."""
        self.client.force_authenticate(self.institution)
        response = self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 3},
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(reverse('confirm-order'))
        self.assertEqual(response.status_code, 201)
        order = Solicitud.objects.get(pk=response.data['id'])
        self.assertEqual(str(order.uuid), response.data['uuid'])
        self.assertEqual(order.status, Solicitud.Status.PAID)
        self.assertEqual(order.total, Decimal('3600.00'))
        self.assertEqual(order.items.count(), 1)
        self.assertTrue(Despacho.objects.filter(order=order).exists())
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 7)
        self.assertFalse(Carro.objects.get(user=self.institution).items.exists())

    def test_insufficient_stock_does_not_create_order_or_clear_cart(self):
        """Asegura que el stock insuficiente revierte el checkout completo."""
        self.client.force_authenticate(self.institution)
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 11},
        )

        response = self.client.post(reverse('confirm-order'))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Solicitud.objects.count(), 0)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 10)
        self.assertTrue(Carro.objects.get(user=self.institution).items.exists())

    def test_manager_cancellation_restores_stock_only_once(self):
        """Comprueba reposición al cancelar y evita reponer el mismo pedido dos veces."""
        self.client.force_authenticate(self.institution)
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 4},
        )
        order_response = self.client.post(reverse('confirm-order'))
        order_id = order_response.data['id']

        self.client.force_authenticate(self.manager)
        response = self.client.patch(
            reverse('order-status', args=[order_id]),
            {'status': Solicitud.Status.CANCELLED},
        )
        self.assertEqual(response.status_code, 200)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 10)
        self.assertEqual(
            Despacho.objects.get(order_id=order_id).status,
            Despacho.Status.CANCELLED,
        )

        response = self.client.patch(
            reverse('order-status', args=[order_id]),
            {'status': Solicitud.Status.CANCELLED},
        )
        self.assertEqual(response.status_code, 200)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 10)

    def test_delivery_finishes_dispatch_without_restoring_stock(self):
        """Verifica que una entrega completa el despacho sin reponer stock."""
        self.client.force_authenticate(self.institution)
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 2},
        )
        order_response = self.client.post(reverse('confirm-order'))
        order_id = order_response.data['id']
        order_uuid = order_response.data['uuid']
        self.client.force_authenticate(self.manager)

        response = self.client.patch(
            reverse('order-status-by-uuid', args=[order_uuid]),
            {'status': Solicitud.Status.DELIVERED},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['uuid'], order_uuid)
        self.assertEqual(response.data['status'], Solicitud.Status.DELIVERED)
        dispatch = Despacho.objects.get(order_id=order_id)
        self.assertEqual(dispatch.status, Despacho.Status.DELIVERED)
        self.assertIsNotNone(dispatch.delivered_at)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 8)

    def test_institution_sees_only_its_own_requests(self):
        """Aísla el historial de solicitudes para que cada cliente vea el suyo."""
        self.client.force_authenticate(self.institution)
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 1},
        )
        own_order = self.client.post(reverse('confirm-order')).data['id']
        other_institution = User.objects.create_user(
            username='otra-clinica',
            password='test-password',
            rol=User.Role.INSTITUTION,
        )
        self.client.force_authenticate(other_institution)

        response = self.client.get(reverse('my-orders'))

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data, [])
        self.assertTrue(Solicitud.objects.filter(pk=own_order).exists())

    def test_only_manager_can_change_request_status(self):
        """Impide que una institución cambie el estado de una solicitud."""
        self.client.force_authenticate(self.institution)
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 1},
        )
        order_id = self.client.post(reverse('confirm-order')).data['id']

        response = self.client.patch(
            reverse('order-status', args=[order_id]),
            {'status': Solicitud.Status.DELIVERED},
        )

        self.assertEqual(response.status_code, 403)

    def test_warehouse_page_creates_updates_and_deletes_supplies(self):
        """Permite al gestor administrar lotes desde la página protegida."""
        management_url = reverse('gestion-interna')
        self.client.force_login(self.institution)
        self.assertNotEqual(self.client.get(management_url).status_code, 200)

        self.client.force_login(self.manager)
        response = self.client.get(management_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Agregar insumo')
        self.assertContains(response, 'Solicitudes de abastecimiento')

        supply_data = {
            'category': self.category.pk,
            'commercial_name': 'Guantes de nitrilo',
            'active_ingredient': 'Nitrilo',
            'lot_number': 'GUANTE-WEB-01',
            'expiration_date': (
                timezone.localdate() + timedelta(days=365)
            ).isoformat(),
            'price_per_box': '2500.00',
            'stock_boxes': 30,
        }
        response = self.client.post(
            management_url,
            {'action': 'create-supply', **supply_data},
        )
        self.assertRedirects(response, management_url)
        supply = Insumo.objects.get(lot_number='GUANTE-WEB-01')

        updated_data = {
            **supply_data,
            'stock_boxes': 45,
            'action': 'update-supply',
            'supply_id': supply.pk,
        }
        response = self.client.post(management_url, updated_data)
        self.assertRedirects(response, management_url)
        supply.refresh_from_db()
        self.assertEqual(supply.stock_boxes, 45)

        response = self.client.post(
            management_url,
            {'action': 'delete-supply', 'supply_id': supply.pk},
        )
        self.assertRedirects(response, management_url)
        self.assertFalse(Insumo.objects.filter(pk=supply.pk).exists())

    def test_warehouse_page_uses_api_order_transition_rules(self):
        """La página comparte entrega y reposición atómica de la API."""
        cart, _ = Carro.objects.get_or_create(user=self.institution)
        cart.items.create(supply=self.supply, quantity_boxes=1)
        first_order = create_paid_order(self.institution)
        self.client.force_login(self.manager)
        management_url = reverse('gestion-interna')

        response = self.client.post(
            management_url,
            {
                'action': 'update-order-status',
                'order_id': first_order.pk,
                'status': Solicitud.Status.CANCELLED,
            },
        )
        self.assertRedirects(response, management_url)
        first_order.refresh_from_db()
        self.supply.refresh_from_db()
        self.assertEqual(first_order.status, Solicitud.Status.CANCELLED)
        self.assertEqual(self.supply.stock_boxes, 10)
        self.assertEqual(
            Despacho.objects.get(order=first_order).status,
            Despacho.Status.CANCELLED,
        )

        self.client.post(
            management_url,
            {
                'action': 'update-order-status',
                'order_id': first_order.pk,
                'status': Solicitud.Status.CANCELLED,
            },
        )
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 10)

        cart.items.create(supply=self.supply, quantity_boxes=1)
        second_order = create_paid_order(self.institution)
        response = self.client.post(
            management_url,
            {
                'action': 'update-order-status',
                'order_id': second_order.pk,
                'status': Solicitud.Status.DELIVERED,
            },
        )
        self.assertRedirects(response, management_url)
        second_order.refresh_from_db()
        self.supply.refresh_from_db()
        self.assertEqual(second_order.status, Solicitud.Status.DELIVERED)
        self.assertEqual(self.supply.stock_boxes, 9)
        self.assertEqual(
            Despacho.objects.get(order=second_order).status,
            Despacho.Status.DELIVERED,
        )

    def test_only_master_superuser_can_open_site_user_management(self):
        """El panel web deniega el acceso a clientes y gestores ordinarios."""
        management_url = reverse('gestionar-usuarios')
        self.assertEqual(self.client.get(management_url).status_code, 302)

        for account in (self.institution, self.manager):
            with self.subTest(username=account.username):
                self.client.force_login(account)
                self.assertEqual(self.client.get(management_url).status_code, 403)

        master = User.objects.create_superuser(
            username='maestro_panel',
            email='maestro@example.test',
            password='Master-Password-2026',
        )
        self.client.force_login(master)
        response = self.client.get(management_url)
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Crear usuario')
        self.assertContains(response, 'Superusuario maestro')

        response = self.client.get(
            management_url,
            {'usuario': self.institution.pk},
        )
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'EDITAR CUENTA')
        self.assertContains(response, self.institution.username)
        self.assertContains(response, 'Cliente')
        self.assertContains(response, 'Guardar cambios')
        self.assertContains(response, 'Desactivar cuenta')

    def test_master_site_panel_creates_and_manages_non_superuser_accounts(self):
        """Crea roles de negocio y permite cambiar rol/estado sin dar privilegios."""
        master = User.objects.create_superuser(
            username='maestro_gestion',
            email='maestro-gestion@example.test',
            password='Master-Password-2026',
        )
        self.client.force_login(master)
        management_url = reverse('gestionar-usuarios')

        for username, role in (
            ('institucion_panel', User.Role.INSTITUTION),
            ('gestor_panel', User.Role.WAREHOUSE_MANAGER),
        ):
            with self.subTest(role=role):
                response = self.client.post(
                    management_url,
                    {
                        'action': 'create',
                        'username': username,
                        'rol': role,
                        'password1': 'Panel-Account-Password-2026',
                        'password2': 'Panel-Account-Password-2026',
                    },
                )
                created_user = User.objects.get(username=username)
                self.assertRedirects(
                    response,
                    f'{management_url}?usuario={created_user.pk}',
                )
                self.assertEqual(created_user.rol, role)
                self.assertFalse(created_user.is_staff)
                self.assertFalse(created_user.is_superuser)

        manager_account = User.objects.get(username='gestor_panel')
        response = self.client.post(
            management_url,
            {
                'action': 'update',
                'user_id': manager_account.pk,
                'rol': User.Role.INSTITUTION,
                'is_active': 'on',
            },
        )
        self.assertRedirects(
            response,
            f'{management_url}?usuario={manager_account.pk}',
        )
        manager_account.refresh_from_db()
        self.assertEqual(manager_account.rol, User.Role.INSTITUTION)
        self.assertTrue(manager_account.is_active)

        response = self.client.post(
            management_url,
            {
                'action': 'toggle-active',
                'user_id': manager_account.pk,
            },
        )
        self.assertRedirects(
            response,
            f'{management_url}?usuario={manager_account.pk}',
        )
        manager_account.refresh_from_db()
        self.assertFalse(manager_account.is_active)

    def test_master_site_panel_cannot_edit_or_deactivate_master_accounts(self):
        """Las acciones manipuladas no permiten cambiar ni desactivar al maestro."""
        master = User.objects.create_superuser(
            username='maestro_protegido',
            email='maestro-protegido@example.test',
            password='Master-Password-2026',
        )
        self.client.force_login(master)
        response = self.client.post(
            reverse('gestionar-usuarios'),
            {
                'action': 'toggle-active',
                'user_id': master.pk,
            },
        )
        self.assertEqual(response.status_code, 404)
        master.refresh_from_db()
        self.assertTrue(master.is_active)
        self.assertTrue(master.is_superuser)
