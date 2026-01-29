from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import Product, Sale, SaleItem, InventoryLog
from decimal import Decimal
from django.db.models import Sum, F


class Command(BaseCommand):
    help = 'Fix inventory discrepancies and verify database state'

    def add_arguments(self, parser):
        parser.add_argument(
            '--fix',
            action='store_true',
            help='Actually fix the inventory discrepancies',
        )
        parser.add_argument(
            '--verify-only',
            action='store_true',
            help='Only verify inventory without fixing',
        )

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS('Starting inventory verification...'))
        
        if options['verify_only']:
            self.verify_inventory()
        elif options['fix']:
            self.fix_inventory()
        else:
            self.verify_inventory()
            self.stdout.write(self.style.WARNING(
                '\nTo fix discrepancies, run: python manage.py fix_inventory --fix'
            ))

    def verify_inventory(self):
        """Verify inventory consistency"""
        self.stdout.write('\n=== INVENTORY VERIFICATION ===')
        
        # Check all products
        products = Product.objects.all()
        total_products = products.count()
        self.stdout.write(f'Total products: {total_products}')
        
        # Check low stock products
        low_stock = products.filter(current_stock__lte=F('low_stock_threshold'))
        self.stdout.write(f'Low stock products: {low_stock.count()}')
        
        # Check out of stock products
        out_of_stock = products.filter(current_stock=0)
        self.stdout.write(f'Out of stock products: {out_of_stock.count()}')
        
        # Check for negative stock (should not happen)
        negative_stock = products.filter(current_stock__lt=0)
        if negative_stock.exists():
            self.stdout.write(self.style.ERROR(f'Products with negative stock: {negative_stock.count()}'))
            for product in negative_stock:
                self.stdout.write(f'  - {product.name}: {product.current_stock}')
        
        # Verify sales vs inventory
        self.verify_sales_inventory()

    def verify_sales_inventory(self):
        """Verify that sales match inventory changes"""
        self.stdout.write('\n=== SALES INVENTORY VERIFICATION ===')
        
        # Get all sales
        sales = Sale.objects.all()
        total_sales = sales.count()
        self.stdout.write(f'Total sales: {total_sales}')
        
        # Check for sales without inventory logs
        sales_without_logs = []
        for sale in sales:
            for item in sale.items.all():
                logs = InventoryLog.objects.filter(
                    product=item.product,
                    related_sale=sale,
                    action='SALE'
                )
                if not logs.exists():
                    sales_without_logs.append((sale, item))
        
        if sales_without_logs:
            self.stdout.write(self.style.WARNING(
                f'Sales without inventory logs: {len(sales_without_logs)}'
            ))
            for sale, item in sales_without_logs[:5]:  # Show first 5
                self.stdout.write(f'  - Sale {sale.transaction_id}: {item.product.name} x{item.quantity}')
        else:
            self.stdout.write(self.style.SUCCESS('All sales have inventory logs'))

    def fix_inventory(self):
        """Fix inventory discrepancies"""
        self.stdout.write('\n=== FIXING INVENTORY ===')
        
        with transaction.atomic():
            # Fix negative stock
            negative_stock = Product.objects.filter(current_stock__lt=0)
            if negative_stock.exists():
                self.stdout.write(f'Fixing {negative_stock.count()} products with negative stock...')
                for product in negative_stock:
                    old_stock = product.current_stock
                    product.current_stock = 0
                    product.save()
                    
                    # Log the fix
                    InventoryLog.objects.create(
                        product=product,
                        action='ADJUSTMENT',
                        quantity_change=abs(old_stock),
                        old_quantity=old_stock,
                        new_quantity=0,
                        staff_member=None,  # System adjustment
                        notes=f'Automatically fixed negative stock from {old_stock} to 0'
                    )
                    self.stdout.write(f'  - Fixed {product.name}: {old_stock} -> 0')
            
            # Recalculate inventory from sales
            self.stdout.write('Recalculating inventory from sales...')
            for product in Product.objects.all():
                # Calculate what should be sold based on sales
                total_sold = SaleItem.objects.filter(product=product).aggregate(
                    total=Sum('quantity')
                )['total'] or 0
                
                # Get current inventory logs
                total_restocked = InventoryLog.objects.filter(
                    product=product,
                    action='RESTOCK'
                ).aggregate(
                    total=Sum('quantity_change')
                )['total'] or 0
                
                # Calculate expected stock
                expected_stock = total_restocked - total_sold
                
                if product.current_stock != expected_stock:
                    old_stock = product.current_stock
                    product.current_stock = expected_stock
                    product.save()
                    
                    # Log the adjustment
                    InventoryLog.objects.create(
                        product=product,
                        action='ADJUSTMENT',
                        quantity_change=expected_stock - old_stock,
                        old_quantity=old_stock,
                        new_quantity=expected_stock,
                        staff_member=None,  # System adjustment
                        notes=f'Automatically corrected stock from {old_stock} to {expected_stock} based on sales/restock data'
                    )
                    self.stdout.write(f'  - Corrected {product.name}: {old_stock} -> {expected_stock}')
        
        self.stdout.write(self.style.SUCCESS('Inventory fixes completed!'))
        self.stdout.write('Running verification...')
        self.verify_inventory()
