from django.core.management.base import BaseCommand
from django.db.models import Sum
from core.models import Customer, Sale, DebtPayment
from decimal import Decimal

class Command(BaseCommand):
    help = 'Check customer detail functionality and troubleshoot issues'

    def add_arguments(self, parser):
        parser.add_argument('customer_id', type=int, help='Customer ID to check')

    def handle(self, *args, **options):
        customer_id = options['customer_id']
        
        try:
            # Get customer
            customer = Customer.objects.get(id=customer_id)
            self.stdout.write(f"✅ Found customer: {customer.name} (ID: {customer.id})")
            self.stdout.write(f"Phone: {customer.phone}")
            self.stdout.write(f"Total debt: ${customer.total_debt}")
            self.stdout.write(f"Date created: {customer.date_created}")
            self.stdout.write(f"Last purchase: {customer.last_purchase_date}")
            
            # Check sales
            sales = Sale.objects.filter(customer=customer)
            self.stdout.write(f"\n📊 Sales Information:")
            self.stdout.write(f"Total sales: {sales.count()}")
            
            if sales.exists():
                total_spent = sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
                self.stdout.write(f"Total spent: ${total_spent}")
                
                # Check sale items
                total_products = 0
                for sale in sales:
                    sale_items = sale.items.all()
                    for item in sale_items:
                        total_products += item.quantity
                        self.stdout.write(f"  - Sale #{sale.id}: {item.product.name} x{item.quantity} = ${item.total_price}")
                
                self.stdout.write(f"Total products bought: {total_products}")
            else:
                self.stdout.write("No sales found for this customer")
            
            # Check payments
            payments = DebtPayment.objects.filter(customer=customer)
            self.stdout.write(f"\n💰 Payment Information:")
            self.stdout.write(f"Total payments: {payments.count()}")
            
            if payments.exists():
                total_paid = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
                self.stdout.write(f"Total debt paid: ${total_paid}")
                
                for payment in payments:
                    self.stdout.write(f"  - Payment: ${payment.amount} on {payment.date_created} by {payment.staff_member.username}")
            else:
                self.stdout.write("No payments found for this customer")
            
            # Calculate statistics
            self.stdout.write(f"\n📈 Customer Statistics:")
            total_spent = sales.aggregate(total=Sum('total_amount'))['total'] or Decimal('0.00')
            total_products_bought = sum(item.quantity for sale in sales for item in sale.items.all())
            total_debt_paid = payments.aggregate(total=Sum('amount'))['total'] or Decimal('0.00')
            current_debt = customer.total_debt
            lifetime_value = total_spent + current_debt
            
            self.stdout.write(f"Total spent: ${total_spent}")
            self.stdout.write(f"Total products bought: {total_products_bought}")
            self.stdout.write(f"Total debt paid: ${total_debt_paid}")
            self.stdout.write(f"Current debt: ${current_debt}")
            self.stdout.write(f"Lifetime value: ${lifetime_value}")
            
            # Check for any database issues
            self.stdout.write(f"\n🔍 Database Health Check:")
            
            # Check if customer has any orphaned sales
            orphaned_sales = Sale.objects.filter(customer=customer).exclude(id__in=sales.values_list('id', flat=True))
            if orphaned_sales.exists():
                self.stdout.write(f"⚠️  Found {orphaned_sales.count()} orphaned sales")
            else:
                self.stdout.write("✅ No orphaned sales found")
            
            # Check if customer has any orphaned payments
            orphaned_payments = DebtPayment.objects.filter(customer=customer).exclude(id__in=payments.values_list('id', flat=True))
            if orphaned_payments.exists():
                self.stdout.write(f"⚠️  Found {orphaned_payments.count()} orphaned payments")
            else:
                self.stdout.write("✅ No orphaned payments found")
            
            self.stdout.write(f"\n✅ Customer detail check completed successfully!")
            
        except Customer.DoesNotExist:
            self.stdout.write(f"❌ Customer with ID {customer_id} not found")
        except Exception as e:
            self.stdout.write(f"❌ Error checking customer: {e}")
            import traceback
            traceback.print_exc()
