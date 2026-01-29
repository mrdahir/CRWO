from django.core.management.base import BaseCommand
from django.contrib.auth import get_user_model
from core.models import Category, Product, CurrencySettings

User = get_user_model()

class Command(BaseCommand):
    help = 'Set up initial data for the Vape Shop Management System'

    def handle(self, *args, **options):
        self.stdout.write('Setting up initial data...')
        
        # Create superuser
        if not User.objects.filter(username='admin').exists():
            User.objects.create_superuser(
                username='admin',
                email='admin@vapeshop.com',
                password='admin123',
                first_name='Admin',
                last_name='User',
                can_sell=True,
                can_restock=True
            )
            self.stdout.write(self.style.SUCCESS('Superuser created: admin/admin123'))
        else:
            self.stdout.write('Superuser already exists')
        
        # Create currency settings
        if not CurrencySettings.objects.exists():
            CurrencySettings.objects.create(usd_to_sos_rate=8000.00)
            self.stdout.write(self.style.SUCCESS('Currency settings created'))
        else:
            self.stdout.write('Currency settings already exist')
        
        # Create categories
        categories_data = [
            {'name': 'E-liquid', 'description': 'Vape juice and e-liquids'},
            {'name': 'Device', 'description': 'Vape devices and mods'},
            {'name': 'Coil', 'description': 'Vape coils and atomizers'},
            {'name': 'Accessories', 'description': 'Vape accessories and parts'},
        ]
        
        for cat_data in categories_data:
            category, created = Category.objects.get_or_create(
                name=cat_data['name'],
                defaults={'description': cat_data['description']}
            )
            if created:
                self.stdout.write(f'Category created: {category.name}')
        
        # Create sample products
        products_data = [
            {
                'name': 'Mango E-liquid',
                'brand': 'VapeJuice Co',
                'category_name': 'E-liquid',
                'purchase_price': 5.00,
                'selling_price': 12.00,
                'current_stock': 50,
                'low_stock_threshold': 10
            },
            {
                'name': 'Strawberry E-liquid',
                'brand': 'VapeJuice Co',
                'category_name': 'E-liquid',
                'purchase_price': 5.00,
                'selling_price': 12.00,
                'current_stock': 45,
                'low_stock_threshold': 10
            },
            {
                'name': 'Vape Pen Pro',
                'brand': 'VapeTech',
                'category_name': 'Device',
                'purchase_price': 15.00,
                'selling_price': 35.00,
                'current_stock': 20,
                'low_stock_threshold': 5
            },
            {
                'name': 'Sub-Ohm Coil',
                'brand': 'CoilMaster',
                'category_name': 'Coil',
                'purchase_price': 2.00,
                'selling_price': 8.00,
                'current_stock': 100,
                'low_stock_threshold': 20
            },
            {
                'name': 'Vape Case',
                'brand': 'VapeAccessories',
                'category_name': 'Accessories',
                'purchase_price': 3.00,
                'selling_price': 10.00,
                'current_stock': 30,
                'low_stock_threshold': 8
            }
        ]
        
        for prod_data in products_data:
            category = Category.objects.get(name=prod_data['category_name'])
            product, created = Product.objects.get_or_create(
                name=prod_data['name'],
                brand=prod_data['brand'],
                defaults={
                    'category': category,
                    'purchase_price': prod_data['purchase_price'],
                    'selling_price': prod_data['selling_price'],
                    'current_stock': prod_data['current_stock'],
                    'low_stock_threshold': prod_data['low_stock_threshold']
                }
            )
            if created:
                self.stdout.write(f'Product created: {product.name}')
        
        self.stdout.write(self.style.SUCCESS('Initial data setup completed successfully!'))
        self.stdout.write('You can now login with: admin/admin123') 