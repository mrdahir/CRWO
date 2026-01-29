import os
import django
from decimal import Decimal

# Setup Django environment
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vape_shop.settings')
django.setup()

from core.models import Product, Category, Customer, Sale, SaleItem, SaleUSD, SaleSOS, SaleETB, SaleItemUSD, SaleItemSOS, SaleItemETB

def run():
    print("--- Starting Database Reset (Preserving Admin) ---")
    
    # 1. Clear Transactional Data
    print("Deleting Sales...")
    SaleItemUSD.objects.all().delete()
    SaleItemSOS.objects.all().delete()
    SaleItemETB.objects.all().delete()
    SaleUSD.objects.all().delete()
    SaleSOS.objects.all().delete()
    SaleETB.objects.all().delete()
    SaleItem.objects.all().delete()
    Sale.objects.all().delete()
    
    print("Deleting Customers...")
    Customer.objects.all().delete()
    
    # 2. Clear Inventory
    print("Deleting Products...")
    Product.objects.all().delete()
    
    # 3. Seed Data
    print("--- Seeding New Data ---")
    
    # Ensure Category
    cat_vape, _ = Category.objects.get_or_create(name="Vape Kits", defaults={'description': 'Vaping devices'})
    cat_juice, _ = Category.objects.get_or_create(name="E-Liquids", defaults={'description': 'Flavored juices'})
    
    # Create Products
    # Product 1: Vape Logic
    # Cost: $20, Sell: $35 -> Base Profit $15
    p1 = Product.objects.create(
        name="Vape Kit X1",
        brand="GeekVape",
        category=cat_vape,
        purchase_price=Decimal('20.00'),
        selling_price=Decimal('35.00'),
        current_stock=50,
        low_stock_threshold=5,
        selling_unit="UNIT",
        is_active=True
    )
    print(f"Created Product: {p1.name} (Stock: {p1.current_stock}, Cost: ${p1.purchase_price}, Sell: ${p1.selling_price})")
    
    # Product 2: E-Liquid Logic
    # Cost: $5, Sell: $12 -> Base Profit $7
    p2 = Product.objects.create(
        name="Mango Ice 30ml",
        brand="Naked 100",
        category=cat_juice,
        purchase_price=Decimal('5.00'),
        selling_price=Decimal('12.00'),
        current_stock=100,
        low_stock_threshold=10,
        selling_unit="UNIT",
        is_active=True
    )
    print(f"Created Product: {p2.name} (Stock: {p2.current_stock}, Cost: ${p2.purchase_price}, Sell: ${p2.selling_price})")

    print("\n--- Reset & Seed Complete ---")

if __name__ == "__main__":
    run()
