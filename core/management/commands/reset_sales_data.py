from django.core.management.base import BaseCommand
from django.db import transaction
from core.models import (
    SaleUSD, SaleSOS, Sale, SaleItemUSD, SaleItemSOS, SaleItem,
    DebtPaymentUSD, DebtPaymentSOS, DebtPayment,
    Customer, InventoryLog, AuditLog, Receipt,
    Product, User, CurrencySettings, Category
)
from decimal import Decimal


class Command(BaseCommand):
    help = 'Reset all sales, debt, and transaction data while preserving products, customers, and staff'

    def add_arguments(self, parser):
        parser.add_argument(
            '--confirm',
            action='store_true',
            help='Confirm that you want to reset all data',
        )

    def handle(self, *args, **options):
        if not options['confirm']:
            self.stdout.write(
                self.style.ERROR(
                    'This command will reset ALL sales, debt, and transaction data!\n'
                    'Products, customers, and staff will be preserved.\n'
                    'Use --confirm flag to proceed.'
                )
            )
            return

        with transaction.atomic():
            try:
                # Count records before deletion for reporting
                sales_usd_count = SaleUSD.objects.count()
                sales_sos_count = SaleSOS.objects.count()
                sales_legacy_count = Sale.objects.count()
                debt_payments_usd_count = DebtPaymentUSD.objects.count()
                debt_payments_sos_count = DebtPaymentSOS.objects.count()
                debt_payments_legacy_count = DebtPayment.objects.count()
                inventory_logs_count = InventoryLog.objects.count()
                audit_logs_count = AuditLog.objects.count()
                receipts_count = Receipt.objects.count()

                self.stdout.write('Starting data reset...')

                # 1. Delete all sales and sale items
                self.stdout.write('Deleting sales data...')
                SaleItemUSD.objects.all().delete()
                SaleItemSOS.objects.all().delete()
                SaleItem.objects.all().delete()
                SaleUSD.objects.all().delete()
                SaleSOS.objects.all().delete()
                Sale.objects.all().delete()

                # 2. Delete all debt payments
                self.stdout.write('Deleting debt payment records...')
                DebtPaymentUSD.objects.all().delete()
                DebtPaymentSOS.objects.all().delete()
                DebtPayment.objects.all().delete()

                # 3. Reset customer debt amounts to zero
                self.stdout.write('Resetting customer debt amounts...')
                customers_updated = Customer.objects.update(
                    total_debt_usd=Decimal('0.00'),
                    total_debt_sos=Decimal('0.00'),
                    last_purchase_date=None
                )

                # 4. Delete inventory logs
                self.stdout.write('Deleting inventory logs...')
                InventoryLog.objects.all().delete()

                # 5. Delete audit logs
                self.stdout.write('Deleting audit logs...')
                AuditLog.objects.all().delete()

                # 6. Delete receipts
                self.stdout.write('Deleting receipts...')
                Receipt.objects.all().delete()

                # 7. Verify essential data is preserved
                products_count = Product.objects.count()
                customers_count = Customer.objects.count()
                staff_count = User.objects.count()
                categories_count = Category.objects.count()
                currency_settings_count = CurrencySettings.objects.count()

                self.stdout.write(
                    self.style.SUCCESS(
                        f'\nData reset completed successfully!\n'
                        f'\nDeleted records:\n'
                        f'- USD Sales: {sales_usd_count}\n'
                        f'- SOS Sales: {sales_sos_count}\n'
                        f'- Legacy Sales: {sales_legacy_count}\n'
                        f'- USD Debt Payments: {debt_payments_usd_count}\n'
                        f'- SOS Debt Payments: {debt_payments_sos_count}\n'
                        f'- Legacy Debt Payments: {debt_payments_legacy_count}\n'
                        f'- Inventory Logs: {inventory_logs_count}\n'
                        f'- Audit Logs: {audit_logs_count}\n'
                        f'- Receipts: {receipts_count}\n'
                        f'- Updated Customers: {customers_updated}\n'
                        f'\nPreserved data:\n'
                        f'- Products: {products_count}\n'
                        f'- Customers: {customers_count}\n'
                        f'- Staff Members: {staff_count}\n'
                        f'- Categories: {categories_count}\n'
                        f'- Currency Settings: {currency_settings_count}\n'
                    )
                )

            except Exception as e:
                self.stdout.write(
                    self.style.ERROR(f'Error during data reset: {str(e)}')
                )
                raise

