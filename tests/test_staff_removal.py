from django.test import TestCase, Client
from django.urls import reverse
from django.contrib.auth import get_user_model
User = get_user_model()
from core.models import Product, SaleUSD, SaleItemUSD, InventoryLog, Customer, Category
from decimal import Decimal

class StaffRemovalTest(TestCase):
    def setUp(self):
        self.user = User.objects.create_superuser('admin', 'admin@example.com', 'password')
        self.client = Client()
        self.client.force_login(self.user)
        self.category = Category.objects.create(name="Fabrics")
        self.customer = Customer.objects.create(name="Test Cust", phone="1234")
        self.product = Product.objects.create(
            name="Test Fabric",
            category=self.category,
            current_stock=10.00,
            selling_price=5.00,
            purchase_price=3.00,
            selling_unit='METER'
        )

    def test_staff_link_removed(self):
        response = self.client.get(reverse('core:sales_list'))
        self.assertNotContains(response, 'Staff Management')
        self.assertNotContains(response, 'Assign Staff')

    def test_add_sale_item_currency(self):
        sale = SaleUSD.objects.create(
            user=self.user,
            customer=self.customer,
            # currency and exchange_rate not needed for SaleUSD
        )
        url = reverse('core:add_sale_item', kwargs={'currency': 'USD', 'sale_id': sale.id})
        
        # Test adding 1.5 meters
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': '1.5'
        }, follow=False)
        
        self.assertEqual(response.status_code, 302)
        # Check that item really was created despite not following
        self.assertTrue(SaleItemUSD.objects.filter(sale=sale, product=self.product).exists())
        item = SaleItemUSD.objects.get(sale=sale, product=self.product)
        self.assertEqual(item.quantity, Decimal('1.5'))
        
        # Check inventory update
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('8.50'))

    def test_restock_inventory_decimal(self):
        url = reverse('core:restock_inventory')
        response = self.client.post(url, {
            'product_id': self.product.id,
            'quantity': '2.5',
            'notes': 'Restocking fabric'
        })
        
        self.assertEqual(response.status_code, 200) # JsonResponse
        self.product.refresh_from_db()
        self.assertEqual(self.product.current_stock, Decimal('12.50'))
        
        # Check Log
        log = InventoryLog.objects.last()
        self.assertEqual(log.quantity_change, Decimal('2.5'))
        self.assertEqual(log.user, self.user)
        # Ensure staff_member is NOT in log (it should be removed from model, checking attr)
        self.assertFalse(hasattr(log, 'staff_member'))

    def test_staff_management_url_gone(self):
        # url 'core:staff_management' should raise NoReverseMatch or 404 if accessed directly
        # But since I removed it from urls.py, reverse should fail
        with self.assertRaises(Exception): # NoReverseMatch
             reverse('core:staff_management')
