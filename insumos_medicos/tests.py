from datetime import timedelta
from decimal import Decimal

from django.contrib.auth import get_user_model
from django.urls import reverse
from django.utils import timezone
from rest_framework.test import APITestCase
from rest_framework_simplejwt.tokens import AccessToken

from .models import Cart, Category, Dispatch, Order, Supply


User = get_user_model()


class SupplyApiTests(APITestCase):
    def setUp(self):
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
        self.category = Category.objects.create(name='Medicamentos')
        self.supply = Supply.objects.create(
            category=self.category,
            commercial_name='Paracetamol',
            active_ingredient='Paracetamol',
            lot_number='LOTE-01',
            expiration_date=timezone.localdate() + timedelta(days=90),
            price_per_box=Decimal('1200.00'),
            stock_boxes=10,
        )

    def test_catalog_is_public_and_writes_require_warehouse_manager(self):
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
        response = self.client.post(
            reverse('token-obtain-pair'),
            {'username': self.institution.username, 'password': 'test-password'},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['rol'], User.Role.INSTITUTION)
        token = AccessToken(response.data['access'])
        self.assertEqual(token['rol'], User.Role.INSTITUTION)
        self.assertEqual(token['username'], self.institution.username)

    def test_catalog_page_and_persistent_cart_render(self):
        self.client.force_login(self.institution)
        response = self.client.get(reverse('inicio'))
        self.assertEqual(response.status_code, 200)
        self.assertContains(response, 'Paracetamol')
        self.assertContains(response, 'Maxi solis')
        self.assertContains(response, 'Sección 1')
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
        expired_supply = Supply.objects.create(
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

    def test_cart_supports_item_and_collection_deletion(self):
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
        self.assertFalse(Cart.objects.get(user=self.institution).items.exists())

    def test_confirming_request_deducts_stock_and_creates_dispatch(self):
        self.client.force_authenticate(self.institution)
        response = self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 3},
        )
        self.assertEqual(response.status_code, 201)

        response = self.client.post(reverse('confirm-order'))
        self.assertEqual(response.status_code, 201)
        order = Order.objects.get(pk=response.data['id'])
        self.assertEqual(order.status, Order.Status.PAID)
        self.assertEqual(order.total, Decimal('3600.00'))
        self.assertEqual(order.items.count(), 1)
        self.assertTrue(Dispatch.objects.filter(order=order).exists())
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 7)
        self.assertFalse(Cart.objects.get(user=self.institution).items.exists())

    def test_insufficient_stock_does_not_create_order_or_clear_cart(self):
        self.client.force_authenticate(self.institution)
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 11},
        )

        response = self.client.post(reverse('confirm-order'))

        self.assertEqual(response.status_code, 400)
        self.assertEqual(Order.objects.count(), 0)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 10)
        self.assertTrue(Cart.objects.get(user=self.institution).items.exists())

    def test_manager_cancellation_restores_stock_only_once(self):
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
            {'status': Order.Status.CANCELLED},
        )
        self.assertEqual(response.status_code, 200)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 10)
        self.assertEqual(
            Dispatch.objects.get(order_id=order_id).status,
            Dispatch.Status.CANCELLED,
        )

        response = self.client.patch(
            reverse('order-status', args=[order_id]),
            {'status': Order.Status.CANCELLED},
        )
        self.assertEqual(response.status_code, 200)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 10)

    def test_delivery_finishes_dispatch_without_restoring_stock(self):
        self.client.force_authenticate(self.institution)
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 2},
        )
        order_id = self.client.post(reverse('confirm-order')).data['id']
        self.client.force_authenticate(self.manager)

        response = self.client.patch(
            reverse('order-status', args=[order_id]),
            {'status': Order.Status.DELIVERED},
        )

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.data['status'], Order.Status.DELIVERED)
        dispatch = Dispatch.objects.get(order_id=order_id)
        self.assertEqual(dispatch.status, Dispatch.Status.DELIVERED)
        self.assertIsNotNone(dispatch.delivered_at)
        self.supply.refresh_from_db()
        self.assertEqual(self.supply.stock_boxes, 8)

    def test_institution_sees_only_its_own_requests(self):
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
        self.assertTrue(Order.objects.filter(pk=own_order).exists())

    def test_only_manager_can_change_request_status(self):
        self.client.force_authenticate(self.institution)
        self.client.post(
            reverse('cart-items'),
            {'supply_id': self.supply.pk, 'quantity_boxes': 1},
        )
        order_id = self.client.post(reverse('confirm-order')).data['id']

        response = self.client.patch(
            reverse('order-status', args=[order_id]),
            {'status': Order.Status.DELIVERED},
        )

        self.assertEqual(response.status_code, 403)
