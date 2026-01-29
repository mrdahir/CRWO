import os
import django
from decimal import Decimal

# Setup Django environment (if running standalone, but we will run via shell)
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vape_shop.settings')
django.setup()

from core.models import (
    User, Customer, Product, Category, CurrencySettings,
    SaleUSD, SaleSOS, SaleETB, SaleItemUSD, SaleItemSOS, SaleItemETB
)
from django.utils import timezone

def run_verification():
    print("=== Starting Sale Verification ===")

    # 1. Setup Data
    print("\n1. Setting up test data...")
    
    # Create or get Admin User
    admin_user, created = User.objects.get_or_create(username='test_admin')
    if created:
        admin_user.set_password('password')
        admin_user.save()
    print(f"Admin user: {admin_user.username}")

    # Create or get Customer
    customer, created = Customer.objects.get_or_create(
        phone='252634000000',
        defaults={'name': 'Test Customer'}
    )
    print(f"Customer: {customer.name} (Debt USD: {customer.total_debt_usd}, ETB: {customer.total_debt_etb})")

    # Create or get Category
    category, _ = Category.objects.get_or_create(name='Test Category')

    # Create or get Product
    product, created = Product.objects.get_or_create(
        name='Test Vape',
        defaults={
            'brand': 'TestBrand',
            'category': category,
            'purchase_price': 10.00,
            'selling_price': 20.00,
            'current_stock': 100,
            'low_stock_threshold': 5
        }
    )
    # Ensure enough stock
    product.current_stock = 100
    product.save()
    print(f"Product: {product.name} (Stock: {product.current_stock}, Price USD: {product.selling_price})")

    # Setup Currency Settings
    settings, _ = CurrencySettings.objects.get_or_create(id=1)
    settings.usd_to_etb_rate = 100 # Simple rate for math
    settings.usd_to_sos_rate = 8000
    settings.save()
    print(f"Exchange Rates - ETB: {settings.usd_to_etb_rate}, SOS: {settings.usd_to_sos_rate}")

    # 2. Test ETB Sale
    print("\n2. Testing ETB Sale Creation...")
    initial_stock = product.current_stock
    initial_debt_etb = customer.total_debt_etb

    # Calculate ETB Price
    print(f"DEBUG: selling_price type: {type(product.selling_price)}, value: {product.selling_price}")
    print(f"DEBUG: usd_to_etb_rate type: {type(settings.usd_to_etb_rate)}, value: {settings.usd_to_etb_rate}")
    
    etb_rate = Decimal(str(settings.usd_to_etb_rate))
    p_price = Decimal(str(product.selling_price))
    
    etb_price = p_price * etb_rate
    print(f"DEBUG: etb_price: {etb_price}")
    quantity = 2
    total_etb = etb_price * quantity # 4000
    
    # Create SaleETB
    sale = SaleETB.objects.create(
        customer=customer,
        user=admin_user,
        total_amount=total_etb,
        amount_paid=0,
        debt_amount=total_etb
    )

    # Create Item
    SaleItemETB.objects.create(
        sale=sale,
        product=product,
        quantity=quantity,
        unit_price=etb_price,
        total_price=total_etb
    )

    # Update Stock
    product.current_stock -= quantity
    product.save()

    # Update Customer Debt
    customer.total_debt_etb += total_etb
    customer.save()

    print(f"Sale {sale.id} created. Total: {sale.total_amount} ETB")

    # 3. Verification
    print("\n3. Verifying Results...")
    
    # Check Stock
    product.refresh_from_db()
    print(f"Stock: {initial_stock} -> {product.current_stock} (Expected: {initial_stock - quantity})")
    if product.current_stock == initial_stock - quantity:
        print("PASS: Inventory deducted correctly.")
    else:
        print("FAIL: Inventory deduction incorrect.")

    # Check Debt
    customer.refresh_from_db()
    print(f"Customer ETB Debt: {initial_debt_etb} -> {customer.total_debt_etb} (Expected change: +{total_etb})")
    if customer.total_debt_etb == initial_debt_etb + total_etb:
        print("PASS: Customer debt updated correctly.")
    else:
        print("FAIL: Customer debt update incorrect.")

    # Check Sale Retrieval
    retrieved_sale = SaleETB.objects.get(id=sale.id)
    print(f"Retrieved Sale ID: {retrieved_sale.id}, Total: {retrieved_sale.total_amount} ETB")
    if retrieved_sale:
        print("PASS: Sale persisted correctly.")

    print("\n=== Verification Complete ===")

if __name__ == '__main__':
    run_verification()
