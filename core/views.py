from django.shortcuts import render, redirect, get_object_or_404
from django.contrib.auth.decorators import login_required
from django.views.decorators.http import require_http_methods
from django.contrib import messages
from django.http import JsonResponse, Http404
from django.db.models import Sum, Count, Q, F
from django.db.models.functions import Coalesce
from django.core.paginator import Paginator
from django.core.exceptions import ValidationError
from django.utils import timezone
from django.db import transaction
from datetime import datetime, timedelta
from decimal import Decimal, InvalidOperation, ROUND_HALF_UP
from functools import wraps
import json
import traceback
from .models import *
from .forms import *
from .models import SaleItemUSD, SaleItemSOS, SaleItemETB, Product, CurrencySettings # Import the necessary models
@login_required
def detailed_transaction_report(request):
    """
    Displays a detailed report of all sales transactions.
    Shows customer, product, quantity, selling price, purchase price, profit, currency, and date/time.
    Calculates profit based on actual selling price vs purchase price at the time of sale.
    Allocates transaction-level overpayment to items proportionally and shows final profit.
    """
    # Get filter parameters from the request
    days = int(request.GET.get('days', 7))  # Default to last 7 days
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    product_filter = request.GET.get('product', '') # Optional product filter
    currency_filter = request.GET.get('currency', '') # Optional currency filter ('USD', 'SOS', 'ETB', or 'All')

    # Calculate date range
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)

    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            # Handle invalid date format if necessary, maybe show an error message
            pass # Or set a default date range

    # Get currency settings for potential conversions (though we'll keep original currency for this report)
    currency_settings = CurrencySettings.objects.first()
    # Use default rates if settings not found
    current_usd_to_etb_rate = currency_settings.usd_to_etb_rate if currency_settings else Decimal('100.00')
    current_usd_to_sos_rate = currency_settings.usd_to_sos_rate if currency_settings else Decimal('8000.00')

    # Build querysets for each currency type
    base_filters = {
        'date_created__date__gte': start_date,
        'date_created__date__lte': end_date,
    }

    # --- USD Sales (Fetch the sale objects first to get amount_paid and total_amount) ---
    usd_sales = SaleUSD.objects.filter(**base_filters).select_related(
        'customer'
    ).prefetch_related('items__product').order_by('-date_created')

    if product_filter:
        # Filter sales containing the product, then process items later
        usd_sales = usd_sales.filter(items__product_id=product_filter)

    if currency_filter and currency_filter != 'ALL':
        if currency_filter != 'USD':
             usd_sales = usd_sales.none()

    # --- SOS Sales ---
    sos_sales = SaleSOS.objects.filter(**base_filters).select_related(
        'customer'
    ).prefetch_related('items__product').order_by('-date_created')

    if product_filter:
         sos_sales = sos_sales.filter(items__product_id=product_filter)

    if currency_filter and currency_filter != 'ALL':
         if currency_filter != 'SOS':
             sos_sales = sos_sales.none()

    # --- ETB Sales ---
    etb_sales = SaleETB.objects.filter(**base_filters).select_related(
        'customer'
    ).prefetch_related('items__product').order_by('-date_created')

    if product_filter:
         etb_sales = etb_sales.filter(items__product_id=product_filter)

    if currency_filter and currency_filter != 'ALL':
         if currency_filter != 'ETB':
             etb_sales = etb_sales.none()

    # Combine and format data for the template
    transaction_data = []

    # Process USD sales
    for sale in usd_sales:
        # If product filter was applied at the sale level, items are already filtered implicitly by prefetch_related
        # Otherwise, get all items for the sale
        items = list(sale.items.all())

        # Calculate transaction-level overpayment
        overpayment = max(Decimal('0.00'), sale.amount_paid - sale.total_amount)
        total_items_value = sale.total_amount

        for item in items:
            # Calculate item-level profit and surplus
            profit_per_unit = item.unit_price - item.product.purchase_price
            profit = profit_per_unit * item.quantity
            surplus_per_unit = item.unit_price - item.product.selling_price
            surplus = surplus_per_unit * item.quantity if surplus_per_unit > 0 else Decimal('0.00')

            # Allocate overpayment proportionally to this item's value
            item_overpayment = Decimal('0.00')
            if total_items_value > 0:
                 item_overpayment = (item.total_price / total_items_value) * overpayment

            # Final profit includes item profit + allocated overpayment
            final_profit = profit + item_overpayment

            # Calculate item profit WITHOUT overpayment (for the template condition)
            item_profit_without_overpayment = profit

            transaction_data.append({
                'customer_name': sale.customer.name if sale.customer else "Walk-in Customer",
                'customer_phone': sale.customer.phone if sale.customer else "",
                'product_name': item.product.name,
                'product_brand': item.product.brand,
                'quantity': item.quantity,
                'unit_price_sold': item.unit_price,
                'unit_purchase_price': item.product.purchase_price,
                'unit_minimum_selling_price': item.product.selling_price,
                'total_sale_amount': item.total_price, # unit_price_sold * quantity
                'profit': final_profit, # Includes item profit + allocated overpayment
                'item_profit_without_overpayment': item_profit_without_overpayment, # Add this new key
                'surplus': surplus,
                'allocated_overpayment': item_overpayment,
                'currency': 'USD',
                'sale_date': sale.date_created,
                'transaction_id': sale.transaction_id,
                'sale_amount_paid': sale.amount_paid, # Total amount paid for the entire sale
                'sale_total_amount': sale.total_amount, # Original total amount of the sale
            })

    # Process SOS sales
    for sale in sos_sales:
        items = list(sale.items.all())

        # Calculate transaction-level overpayment in SOS
        overpayment = max(Decimal('0.00'), sale.amount_paid - sale.total_amount)
        total_items_value = sale.total_amount

        for item in items:
            # Calculate item-level profit and surplus in SOS
            # Convert purchase price to SOS using CURRENT rate (as proxy for sale time)
            purchase_price_in_sos_current = item.product.purchase_price * current_usd_to_sos_rate
            profit_per_unit_sos = item.unit_price - purchase_price_in_sos_current
            profit = profit_per_unit_sos * item.quantity

            # Convert minimum selling price to SOS using CURRENT rate
            minimum_selling_price_in_sos_current = item.product.selling_price * current_usd_to_sos_rate
            surplus_per_unit_sos = item.unit_price - minimum_selling_price_in_sos_current
            surplus = surplus_per_unit_sos * item.quantity if surplus_per_unit_sos > 0 else Decimal('0.00')

            # Allocate overpayment proportionally to this item's value
            item_overpayment = Decimal('0.00')
            if total_items_value > 0:
                 item_overpayment = (item.total_price / total_items_value) * overpayment

            # Final profit includes item profit + allocated overpayment
            final_profit = profit + item_overpayment

            # Calculate item profit WITHOUT overpayment (for the template condition)
            item_profit_without_overpayment = profit

            transaction_data.append({
                'customer_name': sale.customer.name if sale.customer else "Walk-in Customer",
                'customer_phone': sale.customer.phone if sale.customer else "",
                'product_name': item.product.name,
                'product_brand': item.product.brand,
                'quantity': item.quantity,
                'unit_price_sold': item.unit_price, # Price at time of sale (Actual Selling Price in SOS)
                'unit_purchase_price': purchase_price_in_sos_current, # Converted using CURRENT rate
                'unit_minimum_selling_price': minimum_selling_price_in_sos_current, # Converted using CURRENT rate
                'total_sale_amount': item.total_price, # unit_price_sold * quantity
                'profit': final_profit, # Includes item profit + allocated overpayment
                'item_profit_without_overpayment': item_profit_without_overpayment, # Add this new key
                'surplus': surplus,
                'allocated_overpayment': item_overpayment,
                'currency': 'SOS',
                'sale_date': sale.date_created,
                'transaction_id': sale.transaction_id,
                'sale_amount_paid': sale.amount_paid,
                'sale_total_amount': sale.total_amount,
            })

    # Process ETB sales
    for sale in etb_sales:
        items = list(sale.items.all())

        # Calculate transaction-level overpayment in ETB
        overpayment = max(Decimal('0.00'), sale.amount_paid - sale.total_amount)
        total_items_value = sale.total_amount

        for item in items:
            # Calculate item-level profit and surplus in ETB using the rate at the time of the sale
            rate_at_sale = item.sale.exchange_rate_at_sale if item.sale.exchange_rate_at_sale else current_usd_to_etb_rate
            # Convert purchase price to ETB using rate at sale time
            purchase_price_in_etb_at_sale = item.product.purchase_price * rate_at_sale
            profit_per_unit_etb = item.unit_price - purchase_price_in_etb_at_sale
            profit = profit_per_unit_etb * item.quantity

            # Convert minimum selling price to ETB using rate at sale time
            minimum_selling_price_in_etb_at_sale = item.product.selling_price * rate_at_sale
            surplus_per_unit_etb = item.unit_price - minimum_selling_price_in_etb_at_sale
            surplus = surplus_per_unit_etb * item.quantity if surplus_per_unit_etb > 0 else Decimal('0.00')

            # Allocate overpayment proportionally to this item's value
            item_overpayment = Decimal('0.00')
            if total_items_value > 0:
                 item_overpayment = (item.total_price / total_items_value) * overpayment

            # Final profit includes item profit + allocated overpayment
            final_profit = profit + item_overpayment

            # Calculate item profit WITHOUT overpayment (for the template condition)
            item_profit_without_overpayment = profit

            transaction_data.append({
                'customer_name': sale.customer.name if sale.customer else "Walk-in Customer",
                'customer_phone': sale.customer.phone if sale.customer else "",
                'product_name': item.product.name,
                'product_brand': item.product.brand,
                'quantity': item.quantity,
                'unit_price_sold': item.unit_price, # Price at time of sale (Actual Selling Price in ETB)
                'unit_purchase_price': purchase_price_in_etb_at_sale, # Convert purchase price to ETB using rate at sale time
                'unit_minimum_selling_price': minimum_selling_price_in_etb_at_sale, # Convert minimum price to ETB using rate at sale time
                'total_sale_amount': item.total_price, # unit_price_sold * quantity
                'profit': final_profit, # Includes item profit + allocated overpayment
                'item_profit_without_overpayment': item_profit_without_overpayment, # Add this new key
                'surplus': surplus,
                'allocated_overpayment': item_overpayment,
                'currency': 'ETB',
                'sale_date': sale.date_created,
                'transaction_id': sale.transaction_id,
                'sale_amount_paid': sale.amount_paid,
                'sale_total_amount': sale.total_amount,
            })

    # Sort the combined list by date (most recent first)
    transaction_data.sort(key=lambda x: x['sale_date'], reverse=True)

    # Calculate totals for the filtered results
    total_quantity = sum(item['quantity'] for item in transaction_data)
    total_sale_amount_usd = Decimal('0.00')
    total_sale_amount_sos = Decimal('0.00')
    total_sale_amount_etb = Decimal('0.00')
    total_profit_usd = Decimal('0.00')
    total_profit_sos = Decimal('0.00')
    total_profit_etb = Decimal('0.00')
    total_surplus_usd = Decimal('0.00')
    total_surplus_sos = Decimal('0.00')
    total_surplus_etb = Decimal('0.00')
    total_allocated_overpayment_usd = Decimal('0.00')
    total_allocated_overpayment_sos = Decimal('0.00')
    total_allocated_overpayment_etb = Decimal('0.00')

    for item in transaction_data:
        if item['currency'] == 'USD':
            total_sale_amount_usd += item['total_sale_amount']
            total_profit_usd += item['profit']
            total_surplus_usd += item['surplus']
            total_allocated_overpayment_usd += item['allocated_overpayment']
        elif item['currency'] == 'SOS':
            total_sale_amount_sos += item['total_sale_amount']
            total_profit_sos += item['profit']
            total_surplus_sos += item['surplus']
            total_allocated_overpayment_sos += item['allocated_overpayment']
        elif item['currency'] == 'ETB':
            total_sale_amount_etb += item['total_sale_amount']
            total_profit_etb += item['profit']
            total_surplus_etb += item['surplus']
            total_allocated_overpayment_etb += item['allocated_overpayment']

    # Get products for the filter dropdown
    products = Product.objects.filter(is_active=True).order_by('name')

    context = {
        'transaction_data': transaction_data,
        'total_quantity': total_quantity,
        'total_sale_amount_usd': total_sale_amount_usd,
        'total_sale_amount_sos': total_sale_amount_sos,
        'total_sale_amount_etb': total_sale_amount_etb,
        'total_profit_usd': total_profit_usd,
        'total_profit_sos': total_profit_sos,
        'total_profit_etb': total_profit_etb,
        'total_surplus_usd': total_surplus_usd,
        'total_surplus_sos': total_surplus_sos,
        'total_surplus_etb': total_surplus_etb,
        'total_allocated_overpayment_usd': total_allocated_overpayment_usd,
        'total_allocated_overpayment_sos': total_allocated_overpayment_sos,
        'total_allocated_overpayment_etb': total_allocated_overpayment_etb,
        # Filters
        'days': days,
        'start_date': start_date.strftime('%Y-%m-%d'),
        'end_date': end_date.strftime('%Y-%m-%d'),
        'product_filter': product_filter,
        'currency_filter': currency_filter,
        'products': products,
    }
    return render(request, 'core/detailed_transaction_report.html', context)


def superuser_required(view_func):
    """Decorator that requires user to be authenticated and superuser"""
    @wraps(view_func)
    def _wrapped_view(request, *args, **kwargs):
        if not request.user.is_authenticated:
            messages.error(request, "Authentication required.")
            return redirect('admin:login')
        if not request.user.is_superuser:
            messages.error(request, "Superuser privileges required.")
            return redirect('core:dashboard')
        return view_func(request, *args, **kwargs)
    return _wrapped_view


def log_audit_action(user, action, object_type, object_id, details, ip_address=None):
    """Log audit action - user can be None for anonymous operations"""
    try:
        AuditLog.objects.create(
            user=user,
            action=action,
            object_type=object_type,
            object_id=object_id,
            details=details,
            ip_address=ip_address
        )
    except Exception as e:
        # Don't fail the main operation if audit logging fails
        print(f"Audit log error: {e}")


@login_required
def home(request):
    """Home view that redirects all admins to dashboard"""
    return redirect('core:dashboard')


@login_required
def dashboard_view(request):
    """Main dashboard view with comprehensive metrics"""
    today = timezone.now().date()
    currency_settings = CurrencySettings.objects.first()
    
    # Default rates if settings missing
    usd_to_sos_rate = currency_settings.usd_to_sos_rate if currency_settings else Decimal('8000.00')
    usd_to_etb_rate = currency_settings.usd_to_etb_rate if currency_settings else Decimal('100.00')
    
    # === TOTAL SALES REVENUE (Full transaction value) ===
    today_sales_usd = SaleUSD.objects.filter(date_created__date=today).aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    
    today_sales_sos = SaleSOS.objects.filter(date_created__date=today).aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    
    today_sales_etb = SaleETB.objects.filter(date_created__date=today).aggregate(
        total=Sum('total_amount')
    )['total'] or Decimal('0.00')
    
    # Convert to ETB
    sales_usd_in_etb = today_sales_usd * usd_to_etb_rate
    sales_sos_in_etb = Decimal('0.00')
    if usd_to_sos_rate > 0:
        sales_sos_in_etb = (today_sales_sos / usd_to_sos_rate) * usd_to_etb_rate
    
    total_sales_revenue_etb = sales_usd_in_etb + sales_sos_in_etb + today_sales_etb
    
    # === CASH COLLECTED (Actual payments received) ===
    today_revenue_usd = SaleUSD.objects.filter(date_created__date=today).aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')
    
    today_revenue_sos = SaleSOS.objects.filter(date_created__date=today).aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')
    
    today_revenue_etb = SaleETB.objects.filter(date_created__date=today).aggregate(
        total=Sum('amount_paid')
    )['total'] or Decimal('0.00')
    
    # Conversions
    revenue_usd_in_etb = today_revenue_usd * usd_to_etb_rate
    revenue_sos_in_etb = Decimal('0.00')
    if usd_to_sos_rate > 0:
        revenue_sos_in_etb = (today_revenue_sos / usd_to_sos_rate) * usd_to_etb_rate
    
    cash_collected_etb = revenue_usd_in_etb + revenue_sos_in_etb + today_revenue_etb
    
    # === OUTSTANDING DEBT & COLLECTION RATE ===
    outstanding_debt_today_etb = total_sales_revenue_etb - cash_collected_etb
    collection_rate = Decimal('0.00')
    if total_sales_revenue_etb > 0:
        collection_rate = (cash_collected_etb / total_sales_revenue_etb * 100).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # Transaction Counts
    today_transactions = (
        SaleUSD.objects.filter(date_created__date=today).count() +
        SaleSOS.objects.filter(date_created__date=today).count() +
        SaleETB.objects.filter(date_created__date=today).count()
    )
    
    # === PROFIT CALCULATION (Superuser Only) ===
    expected_profit_etb = Decimal('0.00')
    actual_profit_etb = Decimal('0.00')
    profit_variance_etb = Decimal('0.00')
    bonus_profit_etb = Decimal('0.00')
    overpayment_count = 0
    total_overpayments_etb = Decimal('0.00')
    
    if request.user.is_superuser:
        # Get all sales for today with prefetched items
        usd_sales = SaleUSD.objects.filter(date_created__date=today).prefetch_related('items__product')
        sos_sales = SaleSOS.objects.filter(date_created__date=today).prefetch_related('items__product')
        etb_sales = SaleETB.objects.filter(date_created__date=today).prefetch_related('items__product')
        
        # Expected profit (if all sales paid in full)
        expected_profit_usd = sum(sale.expected_profit_usd for sale in usd_sales)
        expected_profit_usd += sum(sale.expected_profit_usd for sale in sos_sales)
        expected_profit_usd += sum(sale.expected_profit_usd for sale in etb_sales)
        expected_profit_etb = expected_profit_usd * usd_to_etb_rate
        
        # Actual profit (based on amount_paid)
        actual_profit_usd = sum(sale.actual_profit_usd for sale in usd_sales)
        actual_profit_usd += sum(sale.actual_profit_usd for sale in sos_sales)
        actual_profit_usd += sum(sale.actual_profit_usd for sale in etb_sales)
        actual_profit_etb = actual_profit_usd * usd_to_etb_rate
        
        # Profit variance
        profit_variance_etb = expected_profit_etb - actual_profit_etb
        
        # Overpayment tracking
        overpayment_usd = Decimal('0.00')
        for sale in usd_sales:
            if sale.is_overpayment:
                overpayment_count += 1
                overpayment_usd += sale.overpayment_amount
        
        for sale in sos_sales:
            if sale.is_overpayment:
                overpayment_count += 1
                if usd_to_sos_rate > 0:
                    overpayment_usd += sale.overpayment_amount / usd_to_sos_rate
        
        for sale in etb_sales:
            if sale.is_overpayment:
                overpayment_count += 1
                rate = sale.exchange_rate_at_sale if sale.exchange_rate_at_sale else usd_to_etb_rate
                if rate > 0:
                    overpayment_usd += sale.overpayment_amount / rate
        
        total_overpayments_etb = overpayment_usd * usd_to_etb_rate
        bonus_profit_etb = total_overpayments_etb
    
    # === DEBT CALCULATION (ETB Centric) ===
    total_debt_usd = Customer.get_total_debt_usd()
    total_debt_sos = Customer.get_total_debt_sos()
    total_debt_etb = Customer.get_total_debt_etb()
    
    # Convert all to ETB
    debt_usd_in_etb = total_debt_usd * usd_to_etb_rate
    debt_sos_in_etb = Decimal('0.00')
    if usd_to_sos_rate > 0:
        debt_sos_in_etb = (total_debt_sos / usd_to_sos_rate) * usd_to_etb_rate
    
    total_debt_combined_etb = debt_usd_in_etb + debt_sos_in_etb + total_debt_etb
    top_debtors = Customer.get_customers_with_debt()[:5]
    
    # === WEEKLY SALES CHART (ETB) ===
    weekly_labels = []
    weekly_data = []
    for i in range(6, -1, -1):
        date = today - timedelta(days=i)
        
        # USD -> ETB
        day_usd = SaleUSD.objects.filter(date_created__date=date).aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')
        val_usd_in_etb = day_usd * usd_to_etb_rate
        
        # SOS -> USD -> ETB
        day_sos = SaleSOS.objects.filter(date_created__date=date).aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')
        val_sos_in_etb = Decimal('0.00')
        if usd_to_sos_rate > 0:
            val_sos_in_etb = (day_sos / usd_to_sos_rate) * usd_to_etb_rate
        
        # ETB (Native)
        day_etb = SaleETB.objects.filter(date_created__date=date).aggregate(
            total=Sum('amount_paid')
        )['total'] or Decimal('0.00')
        
        total_day_etb = val_usd_in_etb + val_sos_in_etb + day_etb
        weekly_labels.append(date.strftime('%a'))
        weekly_data.append(float(total_day_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)))
    
    # === TOP SELLING PRODUCTS ===
    week_start = today - timedelta(days=7)
    
    # Get all sale items from the past week
    usd_items = SaleItemUSD.objects.filter(
        sale__date_created__date__gte=week_start
    ).select_related('product', 'sale')
    
    sos_items = SaleItemSOS.objects.filter(
        sale__date_created__date__gte=week_start
    ).select_related('product', 'sale')
    
    etb_items = SaleItemETB.objects.filter(
        sale__date_created__date__gte=week_start
    ).select_related('product', 'sale')
    
    # Aggregate by product
    product_revenue = {}
    
    # Process USD items
    for item in usd_items:
        product_id = item.product.id
        if product_id not in product_revenue:
            product_revenue[product_id] = {
                'product': item.product,
                'total_qty': Decimal('0'),
                'total_revenue_usd': Decimal('0'),
            }
        product_revenue[product_id]['total_qty'] += item.quantity
        product_revenue[product_id]['total_revenue_usd'] += item.total_price
    
    # Process SOS items
    for item in sos_items:
        product_id = item.product.id
        if product_id not in product_revenue:
            product_revenue[product_id] = {
                'product': item.product,
                'total_qty': Decimal('0'),
                'total_revenue_usd': Decimal('0'),
            }
        product_revenue[product_id]['total_qty'] += item.quantity
        if usd_to_sos_rate > 0:
            revenue_usd = item.total_price / usd_to_sos_rate
            product_revenue[product_id]['total_revenue_usd'] += revenue_usd
    
    # Process ETB items
    for item in etb_items:
        product_id = item.product.id
        if product_id not in product_revenue:
            product_revenue[product_id] = {
                'product': item.product,
                'total_qty': Decimal('0'),
                'total_revenue_usd': Decimal('0'),
            }
        product_revenue[product_id]['total_qty'] += item.quantity
        rate = item.sale.exchange_rate_at_sale if item.sale.exchange_rate_at_sale else usd_to_etb_rate
        if rate > 0:
            revenue_usd = item.total_price / rate
            product_revenue[product_id]['total_revenue_usd'] += revenue_usd
    
    # Convert to list and calculate ETB revenue
    for product_id, data in product_revenue.items():
        data['total_revenue_etb'] = (data['total_revenue_usd'] * usd_to_etb_rate).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        data['name'] = data['product'].name
    
    top_selling_items_data = list(product_revenue.values())
    top_selling_items_data.sort(key=lambda x: x['total_qty'], reverse=True)
    top_selling_items = top_selling_items_data[:5]
    
    # === RECENT ACTIVITY ===
    recent_activity = []
    
    def add_recent(queryset, currency, conversion_func):
        for sale in queryset[:10]:
            val_etb = conversion_func(sale)
            recent_activity.append({
                'id': sale.id,
                'customer': sale.customer if sale.customer else "Walk-in Customer",
                'user': sale.user,
                'amount_etb': val_etb,
                'original_amount': sale.total_amount,
                'currency': currency,
                'date_created': sale.date_created,
                'is_paid': sale.is_completed
            })
    
    # USD Sales
    add_recent(
        SaleUSD.objects.select_related('customer', 'user').order_by('-date_created'),
        'USD',
        lambda s: s.total_amount * usd_to_etb_rate
    )
    
    # SOS Sales
    add_recent(
        SaleSOS.objects.select_related('customer', 'user').order_by('-date_created'),
        'SOS',
        lambda s: (s.total_amount / usd_to_sos_rate * usd_to_etb_rate) if usd_to_sos_rate > 0 else Decimal('0.00')
    )
    
    # ETB Sales
    add_recent(
        SaleETB.objects.select_related('customer', 'user').order_by('-date_created'),
        'ETB',
        lambda s: s.total_amount
    )
    
    recent_activity.sort(key=lambda x: x['date_created'], reverse=True)
    recent_activity = recent_activity[:10]
    
    # === INVENTORY METRICS ===
    low_stock_products = Product.objects.filter(
        current_stock__lte=F('low_stock_threshold'),
        is_active=True
    ).order_by('current_stock')
    
    total_products = Product.objects.filter(is_active=True).count()
    low_stock_count = low_stock_products.count()
    out_of_stock_count = Product.objects.filter(current_stock=0, is_active=True).count()
    categories = Category.objects.all().order_by('name')
    
    context = {
        # Revenue Metrics
        'total_sales_revenue_etb': total_sales_revenue_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'cash_collected_etb': cash_collected_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'outstanding_debt_today_etb': outstanding_debt_today_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'collection_rate': collection_rate,
        'today_transactions': today_transactions,
        'today_revenue_etb': cash_collected_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),  # Legacy
        
        # Debt
        'total_debt_etb': total_debt_combined_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'customers_with_debt': Customer.get_customers_with_debt().count(),
        
        # Charts & Lists
        'weekly_labels': weekly_labels,
        'weekly_data': weekly_data,
        'top_selling_items': top_selling_items,
        'recent_activity': recent_activity,
        'top_debtors': top_debtors,
        
        # Inventory
        'total_products': total_products,
        'low_stock_count': low_stock_count,
        'out_of_stock_count': out_of_stock_count,
        'low_stock_products': low_stock_products,
        'categories': categories,
        
        # Settings
        'exchange_rate': usd_to_sos_rate,
        'usd_to_etb_rate': usd_to_etb_rate,
    }
    
    if request.user.is_superuser:
        context.update({
            # Profit Metrics
            'expected_profit_etb': expected_profit_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'actual_profit_etb': actual_profit_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'profit_variance_etb': profit_variance_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'bonus_profit_etb': bonus_profit_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'total_overpayments_etb': total_overpayments_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'overpayment_count': overpayment_count,
            'today_profit_in_etb': actual_profit_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),  # Legacy
        })
    
    return render(request, 'core/dashboard.html', context)


@superuser_required
def sales_list(request):
    """List all sales with filtering and pagination"""
    # Get sales from all three models
    usd_sales = SaleUSD.objects.select_related('customer', 'user').order_by('-date_created')
    sos_sales = SaleSOS.objects.select_related('customer', 'user').order_by('-date_created')
    etb_sales = SaleETB.objects.select_related('customer', 'user').order_by('-date_created')
    legacy_sales = Sale.objects.select_related('customer', 'user').order_by('-date_created')
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        usd_sales = usd_sales.filter(
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search) |
            Q(transaction_id__icontains=search)
        )
        sos_sales = sos_sales.filter(
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search) |
            Q(transaction_id__icontains=search)
        )
        etb_sales = etb_sales.filter(
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search) |
            Q(transaction_id__icontains=search)
        )
        legacy_sales = legacy_sales.filter(
            Q(customer__name__icontains=search) |
            Q(customer__phone__icontains=search) |
            Q(transaction_id__icontains=search)
        )
    
    # Currency filter
    currency = request.GET.get('currency', '')
    if currency == 'USD':
        sos_sales = sos_sales.none()
        etb_sales = etb_sales.none()
        legacy_sales = legacy_sales.filter(currency='USD')
    elif currency == 'SOS':
        usd_sales = usd_sales.none()
        etb_sales = etb_sales.none()
        legacy_sales = legacy_sales.filter(currency='SOS')
    elif currency == 'ETB':
        usd_sales = usd_sales.none()
        sos_sales = sos_sales.none()
        legacy_sales = legacy_sales.filter(currency='ETB')
    
    # Combine all sales into a unified list
    all_sales = []
    
    for sale in usd_sales:
        all_sales.append({
            'id': sale.id,
            'transaction_id': sale.transaction_id,
            'customer': sale.customer,
            'user': sale.user,
            'currency': 'USD',
            'total_amount': sale.total_amount,
            'amount_paid': sale.amount_paid,
            'debt_amount': sale.debt_amount,
            'date_created': sale.date_created,
            'type': 'USD Sale'
        })
    
    for sale in sos_sales:
        all_sales.append({
            'id': sale.id,
            'transaction_id': sale.transaction_id,
            'customer': sale.customer,
            'user': sale.user,
            'currency': 'SOS',
            'total_amount': sale.total_amount,
            'amount_paid': sale.amount_paid,
            'debt_amount': sale.debt_amount,
            'date_created': sale.date_created,
            'type': 'SOS Sale'
        })
    
    for sale in etb_sales:
        all_sales.append({
            'id': sale.id,
            'transaction_id': sale.transaction_id,
            'customer': sale.customer,
            'user': sale.user,
            'currency': 'ETB',
            'total_amount': sale.total_amount,
            'amount_paid': sale.amount_paid,
            'debt_amount': sale.debt_amount,
            'date_created': sale.date_created,
            'type': 'ETB Sale'
        })
    
    for sale in legacy_sales:
        all_sales.append({
            'id': sale.id,
            'transaction_id': sale.transaction_id,
            'customer': sale.customer,
            'user': sale.user,
            'currency': sale.currency,
            'total_amount': sale.total_amount,
            'amount_paid': sale.amount_paid,
            'debt_amount': sale.debt_amount,
            'date_created': sale.date_created,
            'type': 'Legacy Sale'
        })
    
    # Sort by date (most recent first)
    all_sales.sort(key=lambda x: x['date_created'], reverse=True)
    
    # Pagination
    paginator = Paginator(all_sales, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'search': search,
        'currency': currency,
    }
    return render(request, 'core/sales_list.html', context)


def create_sale(request):
    """Create a new sale - allows unauthenticated access for walk-in sales"""
    if request.method == 'POST':
        try:
            is_ajax = request.headers.get('X-Requested-With') == 'XMLHttpRequest'
            
            # Parse form data
            customer_id = request.POST.get('customer')
            currency = request.POST.get('currency', 'USD')
            amount_paid_str = request.POST.get('amount_paid', '0.00')
            pno = request.POST.get('pno', '').strip()
            
            # Convert amount_paid safely
            try:
                amount_paid = Decimal(amount_paid_str).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            except (ValueError, InvalidOperation):
                amount_paid = Decimal('0.00')
            
            # Get currency settings
            currency_settings = CurrencySettings.objects.first()
            exchange_rate = currency_settings.usd_to_sos_rate if currency_settings else Decimal('8000.00')
            etb_exchange_rate = currency_settings.usd_to_etb_rate if currency_settings else Decimal('100.00')
            
            # Get customer (optional)
            customer = None
            if customer_id:
                try:
                    customer = Customer.objects.get(id=customer_id)
                except Customer.DoesNotExist:
                    pass
            
            # Create sale using appropriate model
            sale_user = request.user if request.user.is_authenticated else None
            
            with transaction.atomic():
                if currency == 'USD':
                    sale = SaleUSD.objects.create(
                        customer=customer,
                        user=sale_user,
                        amount_paid=amount_paid,
                        total_amount=Decimal('0.00'),
                        debt_amount=Decimal('0.00'),
                        pno=pno if pno else None
                    )
                elif currency == 'SOS':
                    sale = SaleSOS.objects.create(
                        customer=customer,
                        user=sale_user,
                        amount_paid=amount_paid,
                        total_amount=Decimal('0.00'),
                        debt_amount=Decimal('0.00'),
                        pno=pno if pno else None
                    )
                else:  # ETB
                    sale = SaleETB.objects.create(
                        customer=customer,
                        user=sale_user,
                        amount_paid=amount_paid,
                        total_amount=Decimal('0.00'),
                        debt_amount=Decimal('0.00'),
                        exchange_rate_at_sale=etb_exchange_rate,
                        pno=pno if pno else None
                    )
                
                # Process products
                total_amount = Decimal('0.00')
                products_processed = []
                product_index = 0
                
                while True:
                    product_id_key = f'products[{product_index}][id]'
                    quantity_key = f'products[{product_index}][quantity]'
                    
                    if product_id_key not in request.POST:
                        break
                    
                    product_id = request.POST[product_id_key]
                    quantity_str = request.POST[quantity_key]
                    
                    if product_id and quantity_str:
                        try:
                            product = Product.objects.get(id=product_id)
                            quantity = Decimal(quantity_str).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                            
                            if quantity > 0:
                                # Check stock availability
                                if product.current_stock < quantity:
                                    raise ValueError(f"Not enough stock for {product.name}. Available: {product.current_stock}, Requested: {quantity}")
                                
                                # Get custom unit price or use default
                                unit_price_key = f'products[{product_index}][unit_price]'
                                custom_unit_price = None
                                
                                if unit_price_key in request.POST:
                                    try:
                                        custom_unit_price = Decimal(request.POST[unit_price_key])
                                    except (ValueError, InvalidOperation):
                                        custom_unit_price = None
                                
                                # Set unit price based on currency
                                if currency == 'SOS':
                                    if custom_unit_price is not None:
                                        unit_price = custom_unit_price
                                    else:
                                        unit_price = product.selling_price * exchange_rate
                                elif currency == 'ETB':
                                    if custom_unit_price is not None:
                                        unit_price = custom_unit_price
                                    else:
                                        unit_price = product.selling_price * etb_exchange_rate
                                else:  # USD
                                    if custom_unit_price is not None:
                                        unit_price = custom_unit_price
                                    else:
                                        unit_price = product.selling_price
                                
                                # Validate against purchase price
                                if currency == 'SOS':
                                    min_price_sos = product.purchase_price * exchange_rate
                                    if unit_price < min_price_sos:
                                        raise ValueError(f"Cannot sell {product.name} at {unit_price:.0f} SOS (below purchase price of {min_price_sos:.0f} SOS)")
                                elif currency == 'ETB':
                                    min_price_etb = product.purchase_price * etb_exchange_rate
                                    if unit_price < min_price_etb:
                                        raise ValueError(f"Cannot sell {product.name} at {unit_price:.2f} ETB (below purchase price of {min_price_etb:.2f} ETB)")
                                else:  # USD
                                    if unit_price < product.purchase_price:
                                        raise ValueError(f"Cannot sell {product.name} at ${unit_price:.2f} USD (below purchase price of ${product.purchase_price:.2f} USD)")
                                
                                # Normalize values
                                unit_price = unit_price.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                total_price = (unit_price * quantity).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                                
                                # Create sale item
                                if currency == 'USD':
                                    sale_item = SaleItemUSD(
                                        sale=sale,
                                        product=product,
                                        quantity=quantity,
                                        unit_price=unit_price,
                                        total_price=total_price
                                    )
                                elif currency == 'SOS':
                                    sale_item = SaleItemSOS(
                                        sale=sale,
                                        product=product,
                                        quantity=quantity,
                                        unit_price=unit_price,
                                        total_price=total_price
                                    )
                                else:  # ETB
                                    sale_item = SaleItemETB(
                                        sale=sale,
                                        product=product,
                                        quantity=quantity,
                                        unit_price=unit_price,
                                        total_price=total_price
                                    )
                                
                                # Validate and save
                                sale_item.full_clean()
                                sale_item.save()
                                
                                total_amount += total_price
                                products_processed.append({
                                    'product': product.name,
                                    'quantity': quantity,
                                    'total_price': float(total_price)
                                })
                            
                        except Product.DoesNotExist:
                            raise ValueError(f"Product not found")
                        except ValueError as ve:
                            raise
                    else:
                        pass
                    
                    product_index += 1
                
                # Update sale totals
                sale.total_amount = total_amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                sale.save()
                
                # Update customer debt if applicable
                if sale.debt_amount > 0 and customer:
                    old_debt = Decimal('0.00')
                    if currency == 'USD':
                        old_debt = customer.total_debt_usd
                        customer.total_debt_usd += sale.debt_amount
                    elif currency == 'SOS':
                        old_debt = customer.total_debt_sos
                        customer.total_debt_sos += sale.debt_amount
                    elif currency == 'ETB':
                        old_debt = customer.total_debt_etb
                        customer.total_debt_etb += sale.debt_amount
                    
                    customer.save()
                    
                    # Log debt update
                    audit_user = request.user if request.user.is_authenticated else None
                    if audit_user:
                        log_audit_action(
                            audit_user, 'DEBT_ADDED', 'Customer', customer.id,
                            f'Added debt of {sale.debt_amount} {currency} for sale #{sale.transaction_id}',
                            request.META.get('REMOTE_ADDR')
                        )
                
                # Update inventory
                for item in sale.items.all():
                    product = item.product
                    old_stock = product.current_stock
                    product.current_stock -= item.quantity
                    product.save()
                    
                    # Log inventory change
                    log_data = {
                        'product': product,
                        'action': 'SALE',
                        'quantity_change': -item.quantity,
                        'old_quantity': old_stock,
                        'new_quantity': product.current_stock,
                        'user': request.user if request.user.is_authenticated else None,
                        'notes': f'Sold in Sale #{sale.transaction_id}'
                    }
                    
                    if currency == 'USD':
                        log_data['related_sale_usd'] = sale
                    elif currency == 'SOS':
                        log_data['related_sale_sos'] = sale
                    elif currency == 'ETB':
                        log_data['related_sale_etb'] = sale
                    
                    InventoryLog.objects.create(**log_data)
                
                # Validate sale
                try:
                    sale.full_clean()
                except ValidationError as e:
                    error_messages = []
                    for field, errors in e.error_dict.items():
                        error_messages.extend([f"{field}: {error}" for error in errors])
                    error_message = "; ".join(error_messages)
                    sale.delete()
                    raise ValueError(error_message)
                
                # Log audit action
                log_audit_action(
                    request.user if request.user.is_authenticated else None,
                    'SALE_CREATED', 'Sale', sale.id,
                    f'Created sale #{sale.transaction_id} for {sale.total_amount} {currency} with {len(products_processed)} items, Debt: {sale.debt_amount} {currency}',
                    request.META.get('REMOTE_ADDR')
                )
                
                # Return response
                success_message = f'Sale completed successfully! Transaction ID: {sale.transaction_id}'
                if is_ajax:
                    return JsonResponse({
                        'success': True,
                        'sale_id': sale.id,
                        'transaction_id': str(sale.transaction_id),
                        'message': success_message
                    })
                else:
                    messages.success(request, success_message)
                    return redirect('core:dashboard')
        
        except Exception as e:
            error_message = str(e)
            if is_ajax or request.headers.get('X-Requested-With') == 'XMLHttpRequest':
                return JsonResponse({
                    'success': False,
                    'error': error_message
                })
            else:
                messages.error(request, f'Error creating sale: {error_message}')
                return redirect('core:create_sale')
    
    # GET request
    currency_settings = CurrencySettings.objects.first()
    context = {
        'currency_settings': currency_settings,
    }
    return render(request, 'core/create_sale.html', context)


@login_required
def sale_detail(request, sale_id, currency=None):
    """Display detailed sale information"""
    sale = None
    sale_type = None
    
    # Try to find the sale in all models
    if currency == 'USD' or currency is None:
        try:
            sale = SaleUSD.objects.select_related('customer', 'user').prefetch_related('items__product').get(id=sale_id)
            sale_type = 'USD'
        except SaleUSD.DoesNotExist:
            pass
    
    if sale is None and (currency == 'SOS' or currency is None):
        try:
            sale = SaleSOS.objects.select_related('customer', 'user').prefetch_related('items__product').get(id=sale_id)
            sale_type = 'SOS'
        except SaleSOS.DoesNotExist:
            pass
    
    if sale is None and (currency == 'ETB' or currency is None):
        try:
            sale = SaleETB.objects.select_related('customer', 'user').prefetch_related('items__product').get(id=sale_id)
            sale_type = 'ETB'
        except SaleETB.DoesNotExist:
            pass
    
    if sale is None and (currency == 'Legacy' or currency is None):
        try:
            sale = Sale.objects.select_related('customer', 'user').prefetch_related('items__product').get(id=sale_id)
            sale_type = 'Legacy'
        except Sale.DoesNotExist:
            pass
    
    if sale is None:
        raise Http404("Sale not found")
    
    context = {
        'sale': sale,
        'sale_type': sale_type,
        'currency': sale_type,
    }
    return render(request, 'core/sale_detail.html', context)


@superuser_required
def inventory_list(request):
    """List all inventory items with filtering"""
    products = Product.objects.select_related('category').order_by('name')
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        products = products.filter(
            Q(name__icontains=search) |
            Q(brand__icontains=search) |
            Q(category__name__icontains=search)
        )
    
    # Category filter
    category = request.GET.get('category', '')
    if category:
        products = products.filter(category_id=category)
    
    # Low stock filter
    low_stock = request.GET.get('low_stock', '')
    if low_stock == 'true':
        products = products.filter(current_stock__lte=F('low_stock_threshold'))
    
    # Pagination
    paginator = Paginator(products, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Categories for filter
    categories = Category.objects.all()
    
    # Get low stock products for summary
    low_stock_products = Product.objects.filter(
        current_stock__lte=F('low_stock_threshold'),
        is_active=True
    )
    
    # Get out of stock count
    out_of_stock_count = Product.objects.filter(
        current_stock=0,
        is_active=True
    ).count()
    
    context = {
        'page_obj': page_obj,
        'search': search,
        'category': category,
        'low_stock': low_stock,
        'categories': categories,
        'low_stock_products': low_stock_products,
        'out_of_stock_count': out_of_stock_count,
    }
    return render(request, 'core/inventory_list.html', context)


@superuser_required
def add_sale_item(request, currency, sale_id):
    """Add an item to an existing sale"""
    sale = None
    item_model_class = None
    
    if currency == 'USD':
        sale = get_object_or_404(SaleUSD, id=sale_id)
        item_model_class = SaleItemUSD
    elif currency == 'SOS':
        sale = get_object_or_404(SaleSOS, id=sale_id)
        item_model_class = SaleItemSOS
    elif currency == 'ETB':
        sale = get_object_or_404(SaleETB, id=sale_id)
        item_model_class = SaleItemETB
    elif currency == 'Legacy':
        sale = get_object_or_404(Sale, id=sale_id)
        item_model_class = SaleItem
    else:
        messages.error(request, "Invalid currency.")
        return redirect('core:sales_list')
    
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = request.POST.get('quantity')
        
        try:
            product = get_object_or_404(Product, id=product_id)
            quantity = Decimal(quantity)
            
            if quantity <= 0:
                messages.error(request, "Quantity must be greater than zero.")
                return redirect('core:sale_detail', currency=currency, sale_id=sale.id)
            
            if product.current_stock < quantity:
                messages.error(request, f"Not enough stock. Available: {product.current_stock}")
                return redirect('core:sale_detail', currency=currency, sale_id=sale.id)
            
            # Check if this product is already in the sale
            sale_item, created = item_model_class.objects.get_or_create(
                sale=sale,
                product=product,
                defaults={
                    'quantity': quantity,
                    'unit_price': product.selling_price,
                    'total_price': product.selling_price * quantity
                }
            )
            
            if not created:
                # If item already exists, update quantity
                sale_item.quantity += quantity
                sale_item.total_price = sale_item.unit_price * sale_item.quantity
                sale_item.save()
            
            # Update inventory
            product.current_stock -= quantity
            product.save()
            
            # Update sale total
            sale.calculate_total()
            
            # Log inventory change
            InventoryLog.objects.create(
                product=product,
                action='SALE_ITEM_ADDED',
                quantity_change=-quantity,
                old_quantity=product.current_stock + quantity,
                new_quantity=product.current_stock,
                user=request.user,
                notes=f'Added to Sale #{sale.transaction_id}'
            )
            
            # Log audit action
            log_audit_action(
                request.user, 'SALE_ITEM_ADDED', 'SaleItem', sale_item.id,
                f'Added {quantity} x {product.name} to sale #{sale.transaction_id}',
                request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, f'Added {quantity} x {product.name} to sale successfully!')
        
        except (ValueError, Product.DoesNotExist, InvalidOperation) as e:
            messages.error(request, f"Invalid product or quantity: {str(e)}")
        
        return redirect('core:sale_detail', currency=currency, sale_id=sale.id)
    
    # For GET requests, redirect back to sale detail
    return redirect('core:sale_detail', currency=currency, sale_id=sale.id)


@superuser_required
def restock_inventory(request):
    """Restock inventory items"""
    if request.method == 'POST':
        product_id = request.POST.get('product_id')
        quantity = request.POST.get('quantity')
        notes = request.POST.get('notes', '')
        
        try:
            product = Product.objects.get(id=product_id)
            quantity = Decimal(quantity)
            
            if quantity <= 0:
                return JsonResponse({'success': False, 'error': 'Quantity must be positive'})
            
            with transaction.atomic():
                old_stock = product.current_stock
                product.current_stock += quantity
                product.save()
                
                # Log inventory change
                InventoryLog.objects.create(
                    product=product,
                    action='RESTOCK',
                    quantity_change=quantity,
                    old_quantity=old_stock,
                    new_quantity=product.current_stock,
                    user=request.user,
                    notes=notes
                )
                
                # Log audit action
                log_audit_action(
                    request.user, 'RESTOCK', 'Product', product.id,
                    f'Restocked {product.name} with {quantity} units',
                    request.META.get('REMOTE_ADDR')
                )
            
            return JsonResponse({'success': True})
        
        except (Product.DoesNotExist, ValueError, InvalidOperation) as e:
            return JsonResponse({'success': False, 'error': f'Invalid product or quantity: {str(e)}'})
    
    # GET request
    low_stock_products = Product.objects.filter(
        current_stock__lte=F('low_stock_threshold')
    ).order_by('current_stock')
    
    currency_settings = CurrencySettings.objects.first()
    
    context = {
        'low_stock_products': low_stock_products,
        'currency_settings': currency_settings,
    }
    return render(request, 'core/restock_inventory.html', context)


@superuser_required
def customers_list(request):
    """List all customers with filtering"""
    customers = Customer.objects.all().order_by('-date_created')
    
    # Search functionality
    search = request.GET.get('search', '')
    if search:
        customers = customers.filter(
            Q(name__icontains=search) |
            Q(phone__icontains=search)
        )
    
    # Debt filter
    debt_filter = request.GET.get('debt_filter', '')
    if debt_filter == 'has_debt':
        customers = customers.filter(
            Q(total_debt_usd__gt=0) | Q(total_debt_sos__gt=0) | Q(total_debt_etb__gt=0)
        )
    elif debt_filter == 'no_debt':
        customers = customers.filter(
            total_debt_usd=0, total_debt_sos=0, total_debt_etb=0
        )
    
    # Pagination
    paginator = Paginator(customers, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    # Summary statistics
    total_customers = Customer.objects.count()
    customers_with_debt = Customer.get_customers_with_debt().count()
    total_debt = Customer.get_total_debt_sos()
    
    context = {
        'customers': page_obj,
        'search': search,
        'debt_filter': debt_filter,
        'total_customers': total_customers,
        'customers_with_debt': customers_with_debt,
        'total_debt': total_debt,
    }
    return render(request, 'core/customers_list.html', context)


@superuser_required
def create_customer(request):
    """Create a new customer"""
    if request.method == 'POST':
        form = CustomerForm(request.POST)
        if form.is_valid():
            customer = form.save()
            
            # Log audit action
            log_audit_action(
                request.user, 'CUSTOMER_CREATED', 'Customer', customer.id,
                f'Created customer: {customer.name}',
                request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, f'Customer "{customer.name}" created successfully!')
            return redirect('core:customers_list')
    else:
        form = CustomerForm()
    
    context = {
        'form': form,
    }
    return render(request, 'core/create_customer.html', context)


@superuser_required
def edit_customer(request, customer_id):
    """Edit customer information"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == 'POST':
        form = CustomerEditForm(request.POST, instance=customer)
        if form.is_valid():
            # Store old values for audit log
            old_name = customer.name
            old_phone = customer.phone
            old_active = customer.is_active
            
            # Save the updated customer
            customer = form.save()
            
            # Log audit action with detailed changes
            changes = []
            if old_name != customer.name:
                changes.append(f"name: '{old_name}' → '{customer.name}'")
            if old_phone != customer.phone:
                changes.append(f"phone: '{old_phone}' → '{customer.phone}'")
            if old_active != customer.is_active:
                changes.append(f"active: {old_active} → {customer.is_active}")
            
            if changes:
                log_audit_action(
                    request.user, 'CUSTOMER_UPDATED', 'Customer', customer.id,
                    f'Updated customer: {", ".join(changes)}',
                    request.META.get('REMOTE_ADDR')
                )
            
            messages.success(request, f'Customer "{customer.name}" updated successfully!')
            return redirect('core:customer_detail', customer_id=customer.id)
    else:
        form = CustomerEditForm(instance=customer)
    
    context = {
        'customer': customer,
        'form': form,
    }
    return render(request, 'core/edit_customer.html', context)


@superuser_required
def customer_detail(request, customer_id):
    """Display detailed customer information"""
    try:
        customer = get_object_or_404(Customer, id=customer_id)
        
        # Get currency settings
        currency_settings = CurrencySettings.objects.first()
        if not currency_settings:
            currency_settings = CurrencySettings.objects.create()
        
        # Get sales from all models
        usd_sales = SaleUSD.objects.filter(customer=customer).select_related('user').prefetch_related('items')
        sos_sales = SaleSOS.objects.filter(customer=customer).select_related('user').prefetch_related('items')
        etb_sales = SaleETB.objects.filter(customer=customer).select_related('user').prefetch_related('items')
        legacy_sales = Sale.objects.filter(customer=customer).select_related('user').prefetch_related('items')
        
        # Combine and annotate sales
        all_sales_list = []
        
        for s in usd_sales:
            s.currency = 'USD'
            s.total_amount_usd = s.total_amount
            s.amount_paid_usd = s.amount_paid
            s.debt_amount_usd = s.debt_amount
            all_sales_list.append(s)
        
        for s in sos_sales:
            s.currency = 'SOS'
            s.total_amount_usd = currency_settings.convert_sos_to_usd(s.total_amount)
            s.amount_paid_usd = currency_settings.convert_sos_to_usd(s.amount_paid)
            s.debt_amount_usd = currency_settings.convert_sos_to_usd(s.debt_amount)
            all_sales_list.append(s)
        
        for s in etb_sales:
            s.currency = 'ETB'
            s.total_amount_usd = currency_settings.convert_etb_to_usd(s.total_amount)
            s.amount_paid_usd = currency_settings.convert_etb_to_usd(s.amount_paid)
            s.debt_amount_usd = currency_settings.convert_etb_to_usd(s.debt_amount)
            all_sales_list.append(s)
        
        for s in legacy_sales:
            if s.currency == 'SOS':
                s.total_amount_usd = currency_settings.convert_sos_to_usd(s.total_amount)
                s.amount_paid_usd = currency_settings.convert_sos_to_usd(s.amount_paid)
                s.debt_amount_usd = currency_settings.convert_sos_to_usd(s.debt_amount)
            elif s.currency == 'ETB':
                s.total_amount_usd = currency_settings.convert_etb_to_usd(s.total_amount)
                s.amount_paid_usd = currency_settings.convert_etb_to_usd(s.amount_paid)
                s.debt_amount_usd = currency_settings.convert_etb_to_usd(s.debt_amount)
            else:
                s.total_amount_usd = s.total_amount
                s.amount_paid_usd = s.amount_paid
                s.debt_amount_usd = s.debt_amount
            all_sales_list.append(s)
        
        # Sort sales by date
        all_sales_list.sort(key=lambda x: x.date_created, reverse=True)
        sales = all_sales_list
        
        # Get payments
        usd_payments = DebtPaymentUSD.objects.filter(customer=customer)
        sos_payments = DebtPaymentSOS.objects.filter(customer=customer)
        etb_payments = DebtPaymentETB.objects.filter(customer=customer)
        legacy_payments = DebtPayment.objects.filter(customer=customer)
        
        all_payments_list = []
        
        for p in usd_payments:
            p.original_currency = 'USD'
            p.original_amount = p.amount
            all_payments_list.append(p)
        
        for p in sos_payments:
            p.original_currency = 'SOS'
            p.original_amount = p.amount
            all_payments_list.append(p)
        
        for p in etb_payments:
            p.original_currency = 'ETB'
            p.original_amount = p.amount
            all_payments_list.append(p)
        
        for p in legacy_payments:
            if not hasattr(p, 'original_currency'):
                p.original_currency = 'USD'
            p.original_amount = p.amount
            all_payments_list.append(p)
        
        all_payments_list.sort(key=lambda x: x.date_created, reverse=True)
        payments = all_payments_list
        
        # Calculate metrics
        total_spent_usd = sum(s.total_amount_usd for s in sales)
        
        total_products_bought = 0
        for sale in sales:
            if hasattr(sale, 'items'):
                total_products_bought += sum(item.quantity for item in sale.items.all())
        
        total_debt_paid_usd = Decimal('0.00')
        for payment in payments:
            if payment.original_currency == 'USD':
                total_debt_paid_usd += payment.amount
            elif payment.original_currency == 'SOS':
                total_debt_paid_usd += currency_settings.convert_sos_to_usd(payment.amount)
            elif payment.original_currency == 'ETB':
                total_debt_paid_usd += currency_settings.convert_etb_to_usd(payment.amount)
        
        # Calculate current debt in USD
        current_debt_usd = customer.total_debt_usd
        current_debt_usd += currency_settings.convert_sos_to_usd(customer.total_debt_sos)
        current_debt_usd += currency_settings.convert_etb_to_usd(customer.total_debt_etb)
        
        # Payment frequency
        payment_frequency = "Never"
        if len(payments) > 0:
            payment_frequency = f"{len(payments)} payment(s)"
        
        # Calculate lifetime value
        lifetime_value_usd = total_spent_usd + current_debt_usd
        
        context = {
            'customer': customer,
            'sales': sales,
            'payments': payments,
            'total_spent': total_spent_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'total_products_bought': total_products_bought,
            'total_debt_paid': total_debt_paid_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'current_debt': current_debt_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'current_debt_sos': customer.total_debt_sos,
            'current_debt_etb': customer.total_debt_etb,
            'current_debt_usd': customer.total_debt_usd,
            'payment_frequency': payment_frequency,
            'lifetime_value': lifetime_value_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
            'sales_count': len(sales),
            'payments_count': len(payments),
        }
        
        return render(request, 'core/customer_detail.html', context)
    
    except Exception as e:
        print(f"Error in customer_detail view: {e}")
        traceback.print_exc()
        messages.error(request, f"Error loading customer details: {str(e)}")
        return redirect('core:customers_list')


@superuser_required
def record_debt_payment(request, customer_id):
    """Record a debt payment for a customer"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == 'POST':
        form = DebtPaymentForm(request.POST, customer=customer)
        if form.is_valid():
            payment = form.save(commit=False)
            payment.customer = customer
            payment.user = request.user
            
            # Get currency and amount
            currency = form.cleaned_data.get('currency', 'USD')
            original_amount = form.cleaned_data.get('amount')
            
            # Set payment amount
            payment.amount = original_amount
            payment.original_currency = currency
            payment.original_amount = original_amount
            
            # Validate payment amount against customer debt
            if currency == 'USD':
                customer_debt = customer.total_debt_usd
            elif currency == 'SOS':
                customer_debt = customer.total_debt_sos
            elif currency == 'ETB':
                customer_debt = customer.total_debt_etb
            else:
                customer_debt = Decimal('0.00')
            
            if payment.amount > customer_debt:
                messages.error(request, f'Payment amount ({payment.amount} {currency}) cannot exceed total debt ({customer_debt} {currency})')
                return redirect('core:record_debt_payment', customer_id=customer.id)
            
            with transaction.atomic():
                # Save the payment
                payment.save()
                
                # Update customer debt
                old_debt = Decimal('0.00')
                if currency == 'USD':
                    old_debt = customer.total_debt_usd
                    customer.total_debt_usd -= payment.amount
                    if customer.total_debt_usd < 0:
                        customer.total_debt_usd = Decimal('0.00')
                elif currency == 'SOS':
                    old_debt = customer.total_debt_sos
                    customer.total_debt_sos -= payment.amount
                    if customer.total_debt_sos < 0:
                        customer.total_debt_sos = Decimal('0.00')
                elif currency == 'ETB':
                    old_debt = customer.total_debt_etb
                    customer.total_debt_etb -= payment.amount
                    if customer.total_debt_etb < 0:
                        customer.total_debt_etb = Decimal('0.00')
                
                customer.save()
                
                # Apply payment to sales with debt (oldest first)
                remaining_payment = payment.amount
                
                if currency == 'USD':
                    sales_model = SaleUSD
                elif currency == 'SOS':
                    sales_model = SaleSOS
                elif currency == 'ETB':
                    sales_model = SaleETB
                else:
                    sales_model = Sale
                
                if sales_model == Sale:
                    customer_sales_with_debt = sales_model.objects.filter(
                        customer=customer,
                        debt_amount__gt=0,
                        currency=currency
                    ).order_by('date_created')
                else:
                    customer_sales_with_debt = sales_model.objects.filter(
                        customer=customer,
                        debt_amount__gt=0
                    ).order_by('date_created')
                
                for sale in customer_sales_with_debt:
                    if remaining_payment <= 0:
                        break
                    
                    if sale.debt_amount <= remaining_payment:
                        sale.amount_paid += sale.debt_amount
                        remaining_payment -= sale.debt_amount
                        sale.save()
                    else:
                        sale.amount_paid += remaining_payment
                        remaining_payment = Decimal('0.00')
                        sale.save()
                
                # Get new debt amount
                if currency == 'USD':
                    new_debt = customer.total_debt_usd
                elif currency == 'SOS':
                    new_debt = customer.total_debt_sos
                elif currency == 'ETB':
                    new_debt = customer.total_debt_etb
                else:
                    new_debt = Decimal('0.00')
                
                # Log audit action
                log_audit_action(
                    request.user, 'DEBT_PAID', 'Customer', customer.id,
                    f'Recorded payment of {payment.amount} {currency}. Debt reduced from {old_debt} to {new_debt} {currency}',
                    request.META.get('REMOTE_ADDR')
                )
                
                messages.success(request, f'Payment of {payment.amount} {currency} recorded successfully! Debt reduced to {new_debt} {currency}')
                return redirect('core:customer_detail', customer_id=customer.id)
    else:
        form = DebtPaymentForm(customer=customer)
    
    # Calculate debt for display
    current_debt_usd = customer.total_debt_usd
    current_debt_sos = customer.total_debt_sos
    
    context = {
        'customer': customer,
        'form': form,
        'current_debt_usd': current_debt_usd,
        'current_debt_sos': current_debt_sos,
        'current_debt_etb': customer.total_debt_etb,
    }
    return render(request, 'core/record_debt_payment.html', context)


@superuser_required
def correct_customer_debt(request, customer_id):
    """Manually correct customer debt"""
    customer = get_object_or_404(Customer, id=customer_id)
    
    if request.method == 'POST':
        form = DebtCorrectionForm(request.POST, customer=customer)
        if form.is_valid():
            currency = form.cleaned_data['currency']
            new_debt_amount = form.cleaned_data['new_debt_amount']
            reason = form.cleaned_data['reason']
            old_debt_amount = form.cleaned_data['old_debt_amount']
            adjustment_amount = form.cleaned_data['adjustment_amount']
            
            with transaction.atomic():
                # Create debt correction record
                debt_correction = DebtCorrection.objects.create(
                    customer=customer,
                    currency=currency,
                    old_debt_amount=old_debt_amount,
                    new_debt_amount=new_debt_amount,
                    adjustment_amount=adjustment_amount,
                    reason=reason,
                    user=request.user,
                    ip_address=request.META.get('REMOTE_ADDR')
                )
                
                # Update customer debt
                if currency == 'USD':
                    customer.total_debt_usd = new_debt_amount
                elif currency == 'SOS':
                    customer.total_debt_sos = new_debt_amount
                elif currency == 'ETB':
                    customer.total_debt_etb = new_debt_amount
                
                customer.save()
                
                # Log audit action
                log_audit_action(
                    request.user, 'DEBT_CORRECTED', 'Customer', customer.id,
                    f'Manual debt correction: {currency} {old_debt_amount} → {new_debt_amount} (adjustment: {adjustment_amount:+.2f}). Reason: {reason}',
                    request.META.get('REMOTE_ADDR')
                )
                
                messages.success(
                    request,
                    f'Debt corrected successfully! {currency} debt changed from {old_debt_amount} to {new_debt_amount} (adjustment: {adjustment_amount:+.2f})'
                )
                return redirect('core:customer_detail', customer_id=customer.id)
    else:
        form = DebtCorrectionForm(customer=customer)
    
    # Get current debt amounts
    current_debt_usd = customer.total_debt_usd
    current_debt_sos = customer.total_debt_sos
    
    # Get recent debt corrections
    recent_corrections = customer.debt_corrections.all()[:5]
    
    context = {
        'customer': customer,
        'form': form,
        'current_debt_usd': current_debt_usd,
        'current_debt_sos': current_debt_sos,
        'current_debt_etb': customer.total_debt_etb,
        'recent_corrections': recent_corrections,
    }
    return render(request, 'core/correct_customer_debt.html', context)


@superuser_required
def currency_settings_view(request):
    """Manage currency exchange rates"""
    currency_settings = CurrencySettings.objects.first()
    
    if request.method == 'POST':
        form = CurrencySettingsForm(request.POST, instance=currency_settings)
        if form.is_valid():
            settings = form.save(commit=False)
            settings.updated_by = request.user
            settings.save()
            
            # Log audit action
            log_audit_action(
                request.user, 'CURRENCY_UPDATED', 'CurrencySettings', settings.id,
                f'Updated exchange rate to {settings.usd_to_sos_rate}',
                request.META.get('REMOTE_ADDR')
            )
            
            messages.success(request, 'Currency settings updated successfully!')
            return redirect('core:currency_settings')
    else:
        form = CurrencySettingsForm(instance=currency_settings)
    
    context = {
        'form': form,
        'currency_settings': currency_settings,
    }
    return render(request, 'core/currency_settings.html', context)


# ========================================
# API ENDPOINTS
# ========================================

@login_required
def api_search_products(request):
    """API endpoint to search products"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        products = Product.objects.filter(is_active=True)[:10]
    else:
        products = Product.objects.filter(
            Q(name__icontains=query) |
            Q(brand__icontains=query) |
            Q(category__name__icontains=query),
            is_active=True
        )[:10]
    
    # Get currency settings
    currency_settings = CurrencySettings.objects.first()
    
    data = []
    for product in products:
        selling_price_usd = float(product.selling_price)
        selling_price_sos = float(currency_settings.convert_usd_to_sos(product.selling_price)) if currency_settings else 0
        selling_price_etb = float(currency_settings.convert_usd_to_etb(product.selling_price)) if currency_settings else 0
        
        data.append({
            'id': product.id,
            'name': product.name,
            'brand': product.brand,
            'category': product.category.name,
            'purchase_price': float(product.purchase_price) if product.purchase_price else 0,
            'selling_price': selling_price_usd,
            'selling_price_usd': selling_price_usd,
            'selling_price_sos': selling_price_sos,
            'selling_price_etb': selling_price_etb,
            'current_stock': float(product.current_stock),
            'low_stock_threshold': float(product.low_stock_threshold),
            'selling_unit': product.selling_unit,
            'minimum_sale_length': float(product.minimum_sale_length) if product.minimum_sale_length else None,
        })
    
    return JsonResponse(data, safe=False)


@login_required
def api_search_customers(request):
    """API endpoint to search customers"""
    query = request.GET.get('q', '').strip()
    
    if len(query) < 2:
        customers = Customer.objects.all()[:10]
    else:
        customers = Customer.objects.filter(
            Q(name__icontains=query) |
            Q(phone__icontains=query)
        )[:10]
    
    data = []
    for customer in customers:
        data.append({
            'id': customer.id,
            'name': customer.name,
            'phone': customer.phone,
            'pno': customer.pno or '',
            'total_debt': float(customer.total_debt_sos),
            'last_purchase_date': customer.last_purchase_date.isoformat() if customer.last_purchase_date else None,
        })
    
    return JsonResponse(data, safe=False)


@login_required
def api_create_customer(request):
    """API endpoint to create a customer"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        data = json.loads(request.body)
        name = data.get('name', '').strip()
        phone = data.get('phone', '').strip()
        pno = data.get('pno', '').strip()
        
        if not name or not phone:
            return JsonResponse({'success': False, 'error': 'Name and phone are required'}, status=400)
        
        # Check if phone already exists
        if Customer.objects.filter(phone=phone).exists():
            return JsonResponse({'success': False, 'error': 'Phone number already exists'}, status=400)
        
        customer = Customer.objects.create(
            name=name,
            phone=phone,
            pno=pno if pno else None,
        )
        
        # Log audit action
        log_audit_action(
            request.user, 'CUSTOMER_CREATED', 'Customer', customer.id,
            f'Created customer via API: {customer.name}',
            request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'pno': customer.pno or '',
            }
        })
    
    except json.JSONDecodeError:
        return JsonResponse({'success': False, 'error': 'Invalid JSON data'}, status=400)
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
def api_create_product(request):
    """API endpoint to create a product"""
    if request.method != 'POST':
        return JsonResponse({'success': False, 'error': 'Method not allowed'}, status=405)
    
    try:
        name = request.POST.get('name', '').strip()
        brand = request.POST.get('brand', '').strip()
        category_id = request.POST.get('category', '').strip()
        purchase_price = request.POST.get('purchase_price', '').strip()
        selling_price = request.POST.get('selling_price', '').strip()
        current_stock = request.POST.get('current_stock', '0').strip()
        low_stock_threshold = request.POST.get('low_stock_threshold', '5').strip()
        is_active = request.POST.get('is_active') == 'on'
        
        # Validate required fields
        if not all([name, brand, category_id, purchase_price, selling_price]):
            return JsonResponse({'success': False, 'error': 'All required fields must be filled'}, status=400)
        
        # Validate numeric fields
        try:
            purchase_price = Decimal(purchase_price)
            selling_price = Decimal(selling_price)
            current_stock = int(current_stock)
            low_stock_threshold = int(low_stock_threshold)
        except (ValueError, InvalidOperation):
            return JsonResponse({'success': False, 'error': 'Invalid numeric values'}, status=400)
        
        # Get category
        try:
            category = Category.objects.get(id=category_id)
        except Category.DoesNotExist:
            return JsonResponse({'success': False, 'error': 'Invalid category'}, status=400)
        
        # Create product
        try:
            product = Product.objects.create(
                name=name,
                brand=brand,
                category=category,
                purchase_price=purchase_price,
                selling_price=selling_price,
                current_stock=current_stock,
                low_stock_threshold=low_stock_threshold,
                is_active=is_active
            )
        except Exception as e:
            return JsonResponse({'success': False, 'error': f'Product creation failed: {str(e)}'}, status=400)
        
        # Log audit action
        log_audit_action(
            request.user, 'PRODUCT_CREATED', 'Product', product.id,
            f'Created product: {product.name}',
            request.META.get('REMOTE_ADDR')
        )
        
        return JsonResponse({
            'success': True,
            'product': {
                'id': product.id,
                'name': product.name,
                'brand': product.brand,
                'category': product.category.name,
                'selling_price': float(product.selling_price),
                'current_stock': product.current_stock,
                'low_stock_threshold': product.low_stock_threshold,
            }
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@superuser_required
def api_get_product_details(request, product_id):
    """API endpoint to get product details"""
    try:
        product = Product.objects.get(id=product_id)
        
        data = {
            'id': product.id,
            'name': product.name,
            'brand': product.brand,
            'category': product.category.name,
            'selling_price': float(product.selling_price),
            'current_stock': product.current_stock,
            'low_stock_threshold': product.low_stock_threshold,
        }
        
        # Only include purchase price for superusers
        if request.user.is_superuser:
            data['purchase_price'] = float(product.purchase_price)
        
        return JsonResponse(data)
    
    except Product.DoesNotExist:
        return JsonResponse({'error': 'Product not found'}, status=404)


@superuser_required
def debug_user(request):
    """Debug view to check user info"""
    user_info = {
        'username': request.user.username,
        'full_name': request.user.get_full_name(),
        'is_superuser': request.user.is_superuser,
        'date_joined': request.user.date_joined.isoformat(),
    }
    return JsonResponse(user_info)


@superuser_required
def debug_inventory(request):
    """Debug view to check inventory status"""
    products = Product.objects.all().order_by('name')
    
    data = []
    for product in products:
        data.append({
            'id': product.id,
            'name': product.name,
            'brand': product.brand,
            'current_stock': product.current_stock,
            'low_stock_threshold': product.low_stock_threshold,
            'is_low_stock': product.is_low_stock,
            'selling_price': float(product.selling_price),
            'purchase_price': float(product.purchase_price),
        })
    
    return JsonResponse({'products': data})
@login_required
def debug_customer_template(request, customer_id):  # RENAMED
    customer = get_object_or_404(Customer, id=customer_id)
    transactions = customer.transaction_set.all().order_by('-date')
    context = {
        'customer': customer,
        'transactions': transactions,
    }
    return render(request, 'core/debug_customer.html', context)

# Keep the SECOND debug_customer function (JSON API version) as is:
@login_required
def debug_customer(request, customer_id):  # This is the one your URL uses
    """Debug view to check customer status and debt"""
    try:
        customer = Customer.objects.get(id=customer_id)
        sales = Sale.objects.filter(customer=customer)
        payments = DebtPayment.objects.filter(customer=customer)
        data = {
            'customer': {
                'id': customer.id,
                'name': customer.name,
                'phone': customer.phone,
                'total_debt': float(customer.total_debt_sos),
                'date_created': customer.date_created.isoformat(),
                'last_purchase_date': customer.last_purchase_date.isoformat() if customer.last_purchase_date else None,
            },
            'sales': [{
                'id': sale.id,
                'transaction_id': str(sale.transaction_id),
                'total_amount': float(sale.total_amount),
                'amount_paid': float(sale.amount_paid),
                'debt_amount': float(sale.debt_amount),
                'date_created': sale.date_created.isoformat(),
            } for sale in sales],
            'payments': [{
                'id': payment.id,
                'amount': float(payment.amount),
                'date_created': payment.date_created.isoformat(),
                'notes': payment.notes,
            } for payment in payments],
            'total_sales': sales.count(),
            'total_payments': payments.count(),
        }
        return JsonResponse(data)
    except Customer.DoesNotExist:
        return JsonResponse({'error': 'Customer not found'}, status=404)
    except Exception as e:
        return JsonResponse({'error': str(e)}, status=500)

@login_required
def offline_view(request):
    """Offline fallback page"""
    return render(request, 'core/offline.html')


@superuser_required
def edit_sale(request, currency, sale_id):
    """Edit an existing sale"""
    if not request.user.is_superuser:
        messages.error(request, "Access denied. Only superusers can edit sales.")
        return redirect('core:sales_list')
    
    # Get the appropriate model
    if currency == 'USD':
        model_class = SaleUSD
    elif currency == 'SOS':
        model_class = SaleSOS
    elif currency == 'ETB':
        model_class = SaleETB
    else:
        messages.error(request, "Invalid currency specified.")
        return redirect('core:sales_list')
    
    sale = get_object_or_404(model_class, id=sale_id)
    
    if request.method == 'POST':
        new_customer_id = request.POST.get('customer', '').strip()
        new_amount_paid = request.POST.get('amount_paid')
        
        try:
            with transaction.atomic():
                # Store old values
                old_debt = sale.debt_amount
                old_customer = sale.customer
                
                # Update amount paid
                if new_amount_paid:
                    sale.amount_paid = Decimal(new_amount_paid).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
                    sale.save()
                
                new_debt = sale.debt_amount
                
                # Customer logic: Required ONLY if debt exists
                if new_debt > Decimal('0.01'):  # Small threshold for floating-point
                    if not new_customer_id:
                        messages.error(request, "Customer is required when the sale has outstanding debt.")
                        return redirect('core:edit_sale', currency=currency, sale_id=sale.id)
                    
                    new_customer = Customer.objects.get(id=new_customer_id)
                    current_customer_id = old_customer.id if old_customer else None
                    
                    # Handle customer assignment/change
                    if not current_customer_id or int(new_customer_id) != current_customer_id:
                        if not old_customer:
                            # Add debt to new customer
                            new_customer.update_debt(new_debt, currency)
                            sale.customer = new_customer
                        else:
                            # Transfer debt from old to new customer
                            old_customer.update_debt(-old_debt, currency)
                            new_customer.update_debt(new_debt, currency)
                            sale.customer = new_customer
                    else:
                        # Same customer, debt amount changed
                        if old_customer and new_debt != old_debt:
                            debt_diff = new_debt - old_debt
                            old_customer.update_debt(debt_diff, currency)
                else:
                    # Fully paid - clear customer
                    if old_customer:
                        old_customer.update_debt(-old_debt, currency)
                    sale.customer = None
                
                sale.save()
                
                messages.success(request, "Sale updated successfully.")
                return redirect('core:sale_detail', sale_id=sale.id, currency=currency)
        
        except Exception as e:
            messages.error(request, f"Error updating sale: {e}")
            return redirect('core:edit_sale', currency=currency, sale_id=sale.id)
    
    # GET request - prepare context
    customers = Customer.objects.all().order_by('name')
    currency_settings = CurrencySettings.objects.first()
    
    usd_to_etb_rate = currency_settings.usd_to_etb_rate if currency_settings else Decimal('100.00')
    usd_to_sos_rate = currency_settings.usd_to_sos_rate if currency_settings else Decimal('8000.00')
    
    if currency == 'ETB' and hasattr(sale, 'exchange_rate_at_sale') and sale.exchange_rate_at_sale:
        etb_exchange_rate = sale.exchange_rate_at_sale
    else:
        etb_exchange_rate = usd_to_etb_rate
    
    # Recalculate total from items
    if hasattr(sale, 'items'):
        calculated_total = sale.items.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
        if calculated_total != sale.total_amount:
            sale.total_amount = calculated_total
            sale.save()
    
    sale.refresh_from_db()
    calculated_debt = max(Decimal('0.00'), sale.total_amount - sale.amount_paid).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
    
    # Convert to ETB
    if currency == 'USD':
        total_amount_etb = sale.total_amount * usd_to_etb_rate
        amount_paid_etb = sale.amount_paid * usd_to_etb_rate
        debt_amount_etb = calculated_debt * usd_to_etb_rate
    elif currency == 'SOS':
        if usd_to_sos_rate > 0:
            total_amount_usd = sale.total_amount / usd_to_sos_rate
            amount_paid_usd = sale.amount_paid / usd_to_sos_rate
            debt_amount_usd = calculated_debt / usd_to_sos_rate
            total_amount_etb = total_amount_usd * usd_to_etb_rate
            amount_paid_etb = amount_paid_usd * usd_to_etb_rate
            debt_amount_etb = debt_amount_usd * usd_to_etb_rate
        else:
            total_amount_etb = Decimal('0.00')
            amount_paid_etb = Decimal('0.00')
            debt_amount_etb = Decimal('0.00')
    else:  # ETB
        total_amount_etb = sale.total_amount
        amount_paid_etb = sale.amount_paid
        debt_amount_etb = calculated_debt
    
    context = {
        'sale': sale,
        'currency': currency,
        'customers': customers,
        'total_amount_etb': total_amount_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'amount_paid_etb': amount_paid_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'debt_amount_etb': debt_amount_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'total_amount_original': sale.total_amount,
        'amount_paid_original': sale.amount_paid,
        'debt_amount_original': calculated_debt,
        'usd_to_etb_rate': usd_to_etb_rate,
        'usd_to_sos_rate': usd_to_sos_rate,
        'etb_exchange_rate': etb_exchange_rate,
    }
    
    return render(request, 'core/edit_sale.html', context)


# ========================================
# NEW VIEWS: Sales History, Revenue Details, Customer Debt Management
# ========================================

@login_required
def sales_history_view(request):
    """Display sales history with filtering and pagination"""
    days = int(request.GET.get('days', 30))
    currency_filter = request.GET.get('currency', '')
    customer_search = request.GET.get('customer', '')
    transaction_search = request.GET.get('transaction', '')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    # Calculate date range
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    # Get currency settings
    currency_settings = CurrencySettings.objects.first()
    usd_to_etb_rate = currency_settings.usd_to_etb_rate if currency_settings else Decimal('100.00')
    usd_to_sos_rate = currency_settings.usd_to_sos_rate if currency_settings else Decimal('8000.00')
    
    # Query sales
    usd_sales = SaleUSD.objects.filter(
        date_created__date__gte=start_date,
        date_created__date__lte=end_date,
    ).select_related('customer', 'user')
    
    sos_sales = SaleSOS.objects.filter(
        date_created__date__gte=start_date,
        date_created__date__lte=end_date,
    ).select_related('customer', 'user')
    
    etb_sales = SaleETB.objects.filter(
        date_created__date__gte=start_date,
        date_created__date__lte=end_date,
    ).select_related('customer', 'user')
    
    # Apply currency filter
    if currency_filter == 'USD':
        sos_sales = sos_sales.none()
        etb_sales = etb_sales.none()
    elif currency_filter == 'SOS':
        usd_sales = usd_sales.none()
        etb_sales = etb_sales.none()
    elif currency_filter == 'ETB':
        usd_sales = usd_sales.none()
        sos_sales = sos_sales.none()
    
    # Apply customer search
    if customer_search:
        usd_sales = usd_sales.filter(Q(customer__name__icontains=customer_search) | Q(customer__phone__icontains=customer_search))
        sos_sales = sos_sales.filter(Q(customer__name__icontains=customer_search) | Q(customer__phone__icontains=customer_search))
        etb_sales = etb_sales.filter(Q(customer__name__icontains=customer_search) | Q(customer__phone__icontains=customer_search))
    
    # Apply transaction ID search
    if transaction_search:
        usd_sales = usd_sales.filter(transaction_id__icontains=transaction_search)
        sos_sales = sos_sales.filter(transaction_id__icontains=transaction_search)
        etb_sales = etb_sales.filter(transaction_id__icontains=transaction_search)
    
    # Combine all sales
    all_sales = []
    
    for sale in usd_sales:
        amount_for_conversion = sale.total_amount if sale.total_amount > 0 else sale.amount_paid
        all_sales.append({
            'id': sale.id,
            'transaction_id': sale.transaction_id,
            'customer': sale.customer,
            'user': sale.user,
            'currency': 'USD',
            'total_amount': sale.total_amount,
            'amount_paid': sale.amount_paid,
            'debt_amount': sale.debt_amount,
            'date_created': sale.date_created,
            'is_completed': sale.is_completed,
            'amount_etb': amount_for_conversion * usd_to_etb_rate,
        })
    
    for sale in sos_sales:
        amount_for_conversion = sale.total_amount if sale.total_amount > 0 else sale.amount_paid
        amount_etb = (amount_for_conversion / usd_to_sos_rate) * usd_to_etb_rate if usd_to_sos_rate > 0 else Decimal('0.00')
        all_sales.append({
            'id': sale.id,
            'transaction_id': sale.transaction_id,
            'customer': sale.customer,
            'user': sale.user,
            'currency': 'SOS',
            'total_amount': sale.total_amount,
            'amount_paid': sale.amount_paid,
            'debt_amount': sale.debt_amount,
            'date_created': sale.date_created,
            'is_completed': sale.is_completed,
            'amount_etb': amount_etb,
        })
    
    for sale in etb_sales:
        amount_for_conversion = sale.total_amount if sale.total_amount > 0 else sale.amount_paid
        all_sales.append({
            'id': sale.id,
            'transaction_id': sale.transaction_id,
            'customer': sale.customer,
            'user': sale.user,
            'currency': 'ETB',
            'total_amount': sale.total_amount,
            'amount_paid': sale.amount_paid,
            'debt_amount': sale.debt_amount,
            'date_created': sale.date_created,
            'is_completed': sale.is_completed,
            'amount_etb': amount_for_conversion,
        })
    
    # Sort by date
    all_sales.sort(key=lambda x: x['date_created'], reverse=True)
    
    # Pagination
    paginator = Paginator(all_sales, 20)
    page_number = request.GET.get('page')
    page_obj = paginator.get_page(page_number)
    
    context = {
        'page_obj': page_obj,
        'days': days,
        'currency_filter': currency_filter,
        'customer_search': customer_search,
        'transaction_search': transaction_search,
        'total_sales': len(all_sales),
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'core/sales_history.html', context)


@login_required
def revenue_details_view(request):
    """Display revenue breakdown with itemized sales"""
    days = int(request.GET.get('days', 7))
    category_filter = request.GET.get('category', '')
    sort_by = request.GET.get('sort', 'revenue')
    start_date_str = request.GET.get('start_date')
    end_date_str = request.GET.get('end_date')
    
    end_date = timezone.now().date()
    start_date = end_date - timedelta(days=days)
    
    if start_date_str and end_date_str:
        try:
            start_date = datetime.strptime(start_date_str, "%Y-%m-%d").date()
            end_date = datetime.strptime(end_date_str, "%Y-%m-%d").date()
        except ValueError:
            pass
    
    # Get currency settings
    currency_settings = CurrencySettings.objects.first()
    usd_to_etb_rate = currency_settings.usd_to_etb_rate if currency_settings else Decimal('100.00')
    usd_to_sos_rate = currency_settings.usd_to_sos_rate if currency_settings else Decimal('8000.00')
    
    # Query sale items
    usd_items = SaleItemUSD.objects.filter(
        sale__date_created__date__gte=start_date,
        sale__date_created__date__lte=end_date,
    ).select_related('product', 'sale', 'product__category')
    
    sos_items = SaleItemSOS.objects.filter(
        sale__date_created__date__gte=start_date,
        sale__date_created__date__lte=end_date,
    ).select_related('product', 'sale', 'product__category')
    
    etb_items = SaleItemETB.objects.filter(
        sale__date_created__date__gte=start_date,
        sale__date_created__date__lte=end_date,
    ).select_related('product', 'sale', 'product__category')
    
    if category_filter:
        usd_items = usd_items.filter(product__category_id=category_filter)
        sos_items = sos_items.filter(product__category_id=category_filter)
        etb_items = etb_items.filter(product__category_id=category_filter)
    
    # Aggregate by product
    product_revenue = {}
    
    for item in usd_items:
        product_id = item.product.id
        if product_id not in product_revenue:
            product_revenue[product_id] = {
                'product': item.product,
                'total_qty': Decimal('0'),
                'total_revenue_etb': Decimal('0'),
                'items': []
            }
        product_revenue[product_id]['total_qty'] += item.quantity
        product_revenue[product_id]['total_revenue_etb'] += item.total_price * usd_to_etb_rate
        product_revenue[product_id]['items'].append({
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_price': item.total_price,
            'currency': 'USD',
            'date': item.sale.date_created
        })
    
    for item in sos_items:
        product_id = item.product.id
        if product_id not in product_revenue:
            product_revenue[product_id] = {
                'product': item.product,
                'total_qty': Decimal('0'),
                'total_revenue_etb': Decimal('0'),
                'items': []
            }
        product_revenue[product_id]['total_qty'] += item.quantity
        revenue_etb = (item.total_price / usd_to_sos_rate) * usd_to_etb_rate if usd_to_sos_rate > 0 else Decimal('0')
        product_revenue[product_id]['total_revenue_etb'] += revenue_etb
        product_revenue[product_id]['items'].append({
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_price': item.total_price,
            'currency': 'SOS',
            'date': item.sale.date_created
        })
    
    for item in etb_items:
        product_id = item.product.id
        if product_id not in product_revenue:
            product_revenue[product_id] = {
                'product': item.product,
                'total_qty': Decimal('0'),
                'total_revenue_etb': Decimal('0'),
                'items': []
            }
        product_revenue[product_id]['total_qty'] += item.quantity
        product_revenue[product_id]['total_revenue_etb'] += item.total_price
        product_revenue[product_id]['items'].append({
            'quantity': item.quantity,
            'unit_price': item.unit_price,
            'total_price': item.total_price,
            'currency': 'ETB',
            'date': item.sale.date_created
        })
    
    # Convert to list and sort
    revenue_items = list(product_revenue.values())
    
    if sort_by == 'quantity':
        revenue_items.sort(key=lambda x: x['total_qty'], reverse=True)
    elif sort_by == 'date':
        revenue_items.sort(key=lambda x: max([i['date'] for i in x['items']]), reverse=True)
    else:
        revenue_items.sort(key=lambda x: x['total_revenue_etb'], reverse=True)
    
    # Calculate totals
    total_revenue_etb = sum(item['total_revenue_etb'] for item in revenue_items)
    total_items_sold = sum(item['total_qty'] for item in revenue_items)
    avg_sale_value = total_revenue_etb / len(revenue_items) if revenue_items else Decimal('0')
    
    categories = Category.objects.all().order_by('name')
    
    context = {
        'revenue_items': revenue_items,
        'total_revenue_etb': total_revenue_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'total_items_sold': total_items_sold,
        'avg_sale_value': avg_sale_value.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'days': days,
        'category_filter': category_filter,
        'sort_by': sort_by,
        'categories': categories,
        'start_date': start_date,
        'end_date': end_date,
    }
    return render(request, 'core/revenue_details.html', context)


@login_required
def customers_debt_view(request):
    """Display customers with debt and handle debt additions/payments"""
    if request.method == 'POST':
        action = request.POST.get('action')
        customer_id = request.POST.get('customer_id')
        amount = Decimal(request.POST.get('amount', '0'))
        currency = request.POST.get('currency', 'USD')
        notes = request.POST.get('notes', '')
        
        customer = get_object_or_404(Customer, id=customer_id)
        
        if action == 'add_debt':
            with transaction.atomic():
                if currency == 'USD':
                    customer.total_debt_usd += amount
                elif currency == 'SOS':
                    customer.total_debt_sos += amount
                elif currency == 'ETB':
                    customer.total_debt_etb += amount
                customer.save()
                
                log_audit_action(
                    request.user, 'DEBT_ADDED', 'Customer', customer.id,
                    f'Added debt of {amount} {currency}. Notes: {notes}',
                    request.META.get('REMOTE_ADDR')
                )
                
                messages.success(request, f'Debt of {amount} {currency} added successfully to {customer.name}!')
        
        elif action == 'record_payment':
            # Get customer debt
            if currency == 'USD':
                customer_debt = customer.total_debt_usd
            elif currency == 'SOS':
                customer_debt = customer.total_debt_sos
            elif currency == 'ETB':
                customer_debt = customer.total_debt_etb
            else:
                customer_debt = Decimal('0')
            
            if amount > customer_debt:
                messages.error(request, f'Payment amount ({amount} {currency}) cannot exceed total debt ({customer_debt} {currency})')
                return redirect('core:customers_debt')
            
            with transaction.atomic():
                old_debt = customer_debt
                
                if currency == 'USD':
                    customer.total_debt_usd -= amount
                    if customer.total_debt_usd < 0:
                        customer.total_debt_usd = Decimal('0.00')
                elif currency == 'SOS':
                    customer.total_debt_sos -= amount
                    if customer.total_debt_sos < 0:
                        customer.total_debt_sos = Decimal('0.00')
                elif currency == 'ETB':
                    customer.total_debt_etb -= amount
                    if customer.total_debt_etb < 0:
                        customer.total_debt_etb = Decimal('0.00')
                
                customer.save()
                
                # Apply payment to sales
                remaining_payment = amount
                
                if currency == 'USD':
                    sales_model = SaleUSD
                elif currency == 'SOS':
                    sales_model = SaleSOS
                elif currency == 'ETB':
                    sales_model = SaleETB
                else:
                    sales_model = None
                
                if sales_model:
                    customer_sales_with_debt = sales_model.objects.filter(
                        customer=customer,
                        debt_amount__gt=0
                    ).order_by('date_created')
                    
                    for sale in customer_sales_with_debt:
                        if remaining_payment <= 0:
                            break
                        
                        if sale.debt_amount <= remaining_payment:
                            sale.amount_paid += sale.debt_amount
                            remaining_payment -= sale.debt_amount
                            sale.save()
                        else:
                            sale.amount_paid += remaining_payment
                            remaining_payment = Decimal('0.00')
                            sale.save()
                
                # Create debt payment record
                if currency == 'USD':
                    DebtPaymentUSD.objects.create(
                        customer=customer,
                        user=request.user,
                        amount=amount,
                        notes=notes
                    )
                elif currency == 'SOS':
                    DebtPaymentSOS.objects.create(
                        customer=customer,
                        user=request.user,
                        amount=amount,
                        notes=notes
                    )
                elif currency == 'ETB':
                    DebtPaymentETB.objects.create(
                        customer=customer,
                        user=request.user,
                        amount=amount,
                        notes=notes
                    )
                
                new_debt = customer_debt - amount
                
                log_audit_action(
                    request.user, 'DEBT_PAID', 'Customer', customer.id,
                    f'Recorded payment of {amount} {currency}. Debt reduced from {old_debt} to {new_debt} {currency}. Notes: {notes}',
                    request.META.get('REMOTE_ADDR')
                )
                
                messages.success(request, f'Payment of {amount} {currency} recorded successfully! Debt reduced to {new_debt} {currency}')
        
        return redirect('core:customers_debt')
    
    # GET request
    customers_with_debt = Customer.get_customers_with_debt()
    
    # Attach detailed outstanding sales to each customer
    for customer in customers_with_debt:
        outstanding_sales = []
        
        # USD Sales
        usd_sales = SaleUSD.objects.filter(
            customer=customer, 
            debt_amount__gt=0
        ).prefetch_related('items', 'items__product').order_by('-date_created')
        
        for sale in usd_sales:
            sale.currency_code = 'USD'
            sale.items_summary = ", ".join([f"{item.product.name} ({item.quantity})" for item in sale.items.all()])
            outstanding_sales.append(sale)
            
        # SOS Sales
        sos_sales = SaleSOS.objects.filter(
            customer=customer, 
            debt_amount__gt=0
        ).prefetch_related('items', 'items__product').order_by('-date_created')
        
        for sale in sos_sales:
            sale.currency_code = 'SOS'
            sale.items_summary = ", ".join([f"{item.product.name} ({item.quantity})" for item in sale.items.all()])
            outstanding_sales.append(sale)
            
        # ETB Sales
        etb_sales = SaleETB.objects.filter(
            customer=customer, 
            debt_amount__gt=0
        ).prefetch_related('items', 'items__product').order_by('-date_created')
        
        for sale in etb_sales:
            sale.currency_code = 'ETB'
            sale.items_summary = ", ".join([f"{item.product.name} ({item.quantity})" for item in sale.items.all()])
            outstanding_sales.append(sale)
            
        # Sort all outstanding sales by date (newest first)
        outstanding_sales.sort(key=lambda x: x.date_created, reverse=True)
        customer.outstanding_sales = outstanding_sales

    currency_settings = CurrencySettings.objects.first()
    
    usd_to_etb_rate = currency_settings.usd_to_etb_rate if currency_settings else Decimal('100.00')
    usd_to_sos_rate = currency_settings.usd_to_sos_rate if currency_settings else Decimal('8000.00')
    
    total_debt_usd = Customer.get_total_debt_usd()
    total_debt_sos = Customer.get_total_debt_sos()
    total_debt_etb = Customer.get_total_debt_etb()
    
    debt_usd_in_etb = total_debt_usd * usd_to_etb_rate
    debt_sos_in_etb = (total_debt_sos / usd_to_sos_rate) * usd_to_etb_rate if usd_to_sos_rate > 0 else Decimal('0.00')
    total_debt_combined_etb = debt_usd_in_etb + debt_sos_in_etb + total_debt_etb
    
    all_customers = Customer.objects.filter(is_active=True).order_by('name')
    
    context = {
        'customers_with_debt': customers_with_debt,
        'all_customers': all_customers,
        'total_debt_etb': total_debt_combined_etb.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP),
        'total_debt_usd': total_debt_usd,
        'total_debt_sos': total_debt_sos,
        'total_debt_etb_currency': total_debt_etb,
        'customers_count': customers_with_debt.count(),
    }
    return render(request, 'core/customers_debt.html', context)


# ========================================
# PRODUCT UPDATE/DELETE API ENDPOINTS
# ========================================

@login_required
@require_http_methods(['POST'])
def api_update_product(request, product_id):
    """API endpoint to update product"""
    try:
        product = get_object_or_404(Product, id=product_id)
        
        name = request.POST.get('name', '').strip()
        purchase_price = request.POST.get('purchase_price', '')
        selling_price_usd = request.POST.get('selling_price_usd', '')
        
        # Validate name
        if not name:
            return JsonResponse({'success': False, 'error': 'Product name is required'}, status=400)
        
        # Check for duplicate name
        if Product.objects.filter(name__iexact=name).exclude(id=product_id).exists():
            return JsonResponse({'success': False, 'error': f'A product named "{name}" already exists'}, status=400)
        
        # Update product
        product.name = name
        
        if purchase_price:
            try:
                product.purchase_price = Decimal(purchase_price)
            except:
                return JsonResponse({'success': False, 'error': 'Invalid purchase price'}, status=400)
        
        if selling_price_usd:
            try:
                product.selling_price = Decimal(selling_price_usd)
            except:
                return JsonResponse({'success': False, 'error': 'Invalid USD selling price'}, status=400)
        
        product.save()
        
        # Log audit action
        log_audit_action(
            request.user, 'PRODUCT_UPDATED', 'Product', product.id,
            f'Updated product: {product.name}',
            request.META.get('REMOTE_ADDR')
        )
        
        # Get currency settings
        currency_settings = CurrencySettings.objects.first()
        
        # Calculate derived prices
        selling_price_usd = product.selling_price
        selling_price_sos = currency_settings.convert_usd_to_sos(selling_price_usd) if currency_settings else Decimal('0.00')
        selling_price_etb = currency_settings.convert_usd_to_etb(selling_price_usd) if currency_settings else Decimal('0.00')
        
        return JsonResponse({
            'success': True,
            'message': f'Product "{product.name}" updated successfully',
            'product': {
                'id': product.id,
                'name': product.name,
                'purchase_price': str(product.purchase_price),
                'selling_price_usd': str(selling_price_usd),
                'selling_price_sos': str(selling_price_sos),
                'selling_price_etb': str(selling_price_etb),
            }
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)


@login_required
@superuser_required
@require_http_methods(['POST'])
def api_delete_product(request, product_id):
    """API endpoint to delete a product (superuser only)"""
    try:
        product = get_object_or_404(Product, id=product_id)
        product_name = product.name
        
        # Check if product has been used in sales
        has_sales_usd = SaleItemUSD.objects.filter(product=product).exists()
        has_sales_sos = SaleItemSOS.objects.filter(product=product).exists()
        has_sales_etb = SaleItemETB.objects.filter(product=product).exists()
        
        if has_sales_usd or has_sales_sos or has_sales_etb:
            return JsonResponse({
                'success': False,
                'error': f'Cannot delete "{product_name}" because it has been used in sales. Consider marking it as inactive instead.'
            }, status=400)
        
        # Log audit action before deletion
        log_audit_action(
            request.user, 'PRODUCT_DELETED', 'Product', product.id,
            f'Deleted product: {product_name}',
            request.META.get('REMOTE_ADDR')
        )
        
        product.delete()
        
        return JsonResponse({
            'success': True,
            'message': f'Product "{product_name}" deleted successfully'
        })
    
    except Exception as e:
        return JsonResponse({'success': False, 'error': str(e)}, status=500)