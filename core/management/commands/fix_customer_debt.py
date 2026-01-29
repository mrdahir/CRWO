from django.core.management.base import BaseCommand
from django.db import transaction
from decimal import Decimal, InvalidOperation
from core.models import Customer, CurrencySettings


class Command(BaseCommand):
    help = 'Fix customer debt currency fields and ensure proper decimal values'

    def add_arguments(self, parser):
        parser.add_argument(
            '--dry-run',
            action='store_true',
            help='Show what would be fixed without making changes',
        )

    def handle(self, *args, **options):
        dry_run = options['dry_run']
        
        if dry_run:
            self.stdout.write(self.style.WARNING('DRY RUN MODE - No changes will be made'))
        
        # Get currency settings
        currency_settings = CurrencySettings.objects.first()
        if not currency_settings:
            self.stdout.write(self.style.ERROR('No currency settings found. Please set up currency settings first.'))
            return
        
        exchange_rate = currency_settings.usd_to_sos_rate
        self.stdout.write(f'Using exchange rate: 1 USD = {exchange_rate} SOS')
        
        # Get all customers
        customers = Customer.objects.all()
        fixed_count = 0
        error_count = 0
        
        for customer in customers:
            try:
                # Get current debt values
                total_debt = getattr(customer, 'total_debt', Decimal('0.00'))
                total_debt_usd = getattr(customer, 'total_debt_usd', None)
                total_debt_sos = getattr(customer, 'total_debt_sos', None)
                
                # Check if currency fields need fixing
                needs_fix = False
                
                # Fix total_debt_usd
                if total_debt_usd is None or total_debt_usd == 0:
                    if total_debt > 0:
                        total_debt_usd = total_debt
                        needs_fix = True
                        self.stdout.write(f'Customer {customer.name}: Setting total_debt_usd to {total_debt_usd}')
                else:
                    try:
                        # Ensure it's a valid decimal
                        total_debt_usd = Decimal(str(total_debt_usd))
                    except (ValueError, InvalidOperation):
                        total_debt_usd = total_debt
                        needs_fix = True
                        self.stdout.write(f'Customer {customer.name}: Fixed invalid total_debt_usd value')
                
                # Fix total_debt_sos
                if total_debt_sos is None or total_debt_sos == 0:
                    if total_debt > 0:
                        total_debt_sos = total_debt * exchange_rate
                        needs_fix = True
                        self.stdout.write(f'Customer {customer.name}: Setting total_debt_sos to {total_debt_sos}')
                else:
                    try:
                        # Ensure it's a valid decimal
                        total_debt_sos = Decimal(str(total_debt_sos))
                    except (ValueError, InvalidOperation):
                        total_debt_sos = total_debt * exchange_rate
                        needs_fix = True
                        self.stdout.write(f'Customer {customer.name}: Fixed invalid total_debt_sos value')
                
                # Fix total_debt if it's None or invalid
                if total_debt is None:
                    total_debt = Decimal('0.00')
                    needs_fix = True
                    self.stdout.write(f'Customer {customer.name}: Setting total_debt to 0.00')
                else:
                    try:
                        total_debt = Decimal(str(total_debt))
                    except (ValueError, InvalidOperation):
                        total_debt = Decimal('0.00')
                        needs_fix = True
                        self.stdout.write(f'Customer {customer.name}: Fixed invalid total_debt value')
                
                # Update customer if needed
                if needs_fix and not dry_run:
                    with transaction.atomic():
                        customer.total_debt = total_debt
                        customer.total_debt_usd = total_debt_usd
                        customer.total_debt_sos = total_debt_sos
                        customer.save()
                        fixed_count += 1
                        self.stdout.write(
                            self.style.SUCCESS(f'Fixed customer {customer.name}: USD={total_debt_usd}, SOS={total_debt_sos}')
                        )
                elif needs_fix:
                    fixed_count += 1
                    self.stdout.write(
                        self.style.WARNING(f'Would fix customer {customer.name}: USD={total_debt_usd}, SOS={total_debt_sos}')
                    )
                else:
                    self.stdout.write(f'Customer {customer.name}: No fixes needed')
                    
            except Exception as e:
                error_count += 1
                self.stdout.write(
                    self.style.ERROR(f'Error processing customer {customer.name}: {str(e)}')
                )
        
        # Summary
        self.stdout.write('\n' + '='*50)
        if dry_run:
            self.stdout.write(self.style.WARNING(f'DRY RUN COMPLETE: Would fix {fixed_count} customers, {error_count} errors'))
        else:
            self.stdout.write(self.style.SUCCESS(f'FIX COMPLETE: Fixed {fixed_count} customers, {error_count} errors'))
        
        # Show debt summary
        total_debt = Customer.get_total_debt()
        customers_with_debt = Customer.get_customers_with_debt().count()
        self.stdout.write(f'Total debt across all customers: ${total_debt}')
        self.stdout.write(f'Customers with debt: {customers_with_debt}')




