from django.db import models
from django.contrib.auth.models import AbstractUser
from django.core.validators import MinValueValidator
from django.db.models import Sum, Q
from decimal import Decimal, ROUND_HALF_UP, InvalidOperation
import uuid

class User(AbstractUser):
    """Admin user model - all logged-in users are trusted admins"""
    phone = models.CharField(max_length=15, blank=True, null=True)
    date_created = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)

    class Meta:
        verbose_name = "Admin User"
        verbose_name_plural = "Admin Users"

    def __str__(self):
        return f"{self.get_full_name()} ({self.username})"


class CurrencySettings(models.Model):
    """Global currency exchange rate settings"""
    usd_to_sos_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=8000.00,
        verbose_name="USD to SOS Exchange Rate"
    )
    sos_to_usd_rate = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0.000125,
        verbose_name="SOS to USD Exchange Rate"
    )
    usd_to_etb_rate = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=100.00,
        verbose_name="USD to ETB Exchange Rate"
    )
    etb_to_usd_rate = models.DecimalField(
        max_digits=10,
        decimal_places=6,
        default=0.01,
        verbose_name="ETB to USD Exchange Rate"
    )
    date_updated = models.DateTimeField(auto_now=True)
    updated_by = models.ForeignKey(User, on_delete=models.SET_NULL, null=True)

    class Meta:
        verbose_name = "Currency Setting"
        verbose_name_plural = "Currency Settings"

    def __str__(self):
        return f"1 USD = {self.usd_to_sos_rate} SOS"

    def save(self, *args, **kwargs):
        # Auto-calculate SOS to USD rate when USD to SOS rate is updated
        if self.usd_to_sos_rate > 0:
            self.sos_to_usd_rate = Decimal('1.000000') / self.usd_to_sos_rate
        if self.usd_to_etb_rate > 0:
            self.etb_to_usd_rate = Decimal('1.000000') / self.usd_to_etb_rate
        super().save(*args, **kwargs)

    def convert_usd_to_sos(self, usd_amount):
        """Convert USD amount to SOS"""
        return usd_amount * self.usd_to_sos_rate

    def convert_usd_to_etb(self, usd_amount):
        """Convert USD amount to ETB"""
        return usd_amount * self.usd_to_etb_rate

    def convert_sos_to_usd(self, sos_amount):
        """Convert SOS amount to USD"""
        if self.usd_to_sos_rate > 0:
            return sos_amount / self.usd_to_sos_rate
        return Decimal('0.00')

    def convert_etb_to_usd(self, etb_amount):
        """Convert ETB amount to USD"""
        if self.usd_to_etb_rate > 0:
            return etb_amount / self.usd_to_etb_rate
        return Decimal('0.00')


class Category(models.Model):
    """Product categories"""
    name = models.CharField(max_length=100, unique=True)
    description = models.TextField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Category"
        verbose_name_plural = "Categories"

    def __str__(self):
        return self.name


class Product(models.Model):
    """Product model with purchase price hidden from non-superusers"""
    name = models.CharField(max_length=200)
    brand = models.CharField(max_length=100)
    category = models.ForeignKey(Category, on_delete=models.CASCADE)
    purchase_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Purchase Price (USD)"
    )
    selling_price = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        verbose_name="Selling Price (USD)"
    )
    UNIT_CHOICES = [
        ('UNIT', 'Unit'),
        ('METER', 'Meter'),
    ]
    selling_unit = models.CharField(max_length=10, choices=UNIT_CHOICES, default='UNIT')
    current_stock = models.DecimalField(max_digits=10, decimal_places=2, default=0.00)
    low_stock_threshold = models.DecimalField(max_digits=10, decimal_places=2, default=5.00)
    minimum_sale_length = models.DecimalField(
        max_digits=5,
        decimal_places=2,
        null=True,
        blank=True,
        help_text="Applies only to METER products"
    )
    date_added = models.DateTimeField(auto_now_add=True)
    date_updated = models.DateTimeField(auto_now=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Product"
        verbose_name_plural = "Products"

    def __str__(self):
        return f"{self.brand} - {self.name}"

    @property
    def profit_margin(self):
        """Calculate profit margin (superuser only)"""
        return self.selling_price - self.purchase_price

    @property
    def is_low_stock(self):
        """Check if product is low on stock"""
        return self.current_stock <= self.low_stock_threshold


class Customer(models.Model):
    """Customer model with separate USD and SOS debt tracking"""
    name = models.CharField(max_length=200, blank=True, null=True)
    phone = models.CharField(max_length=15, blank=True, null=True)
    total_debt_usd = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total debt in USD")
    total_debt_sos = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total debt in SOS")
    total_debt_etb = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Total debt in ETB")
    date_created = models.DateTimeField(auto_now_add=True)
    last_purchase_date = models.DateTimeField(null=True, blank=True)
    is_active = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Customer"
        verbose_name_plural = "Customers"

    def __str__(self):
        return f"{self.name} ({self.phone})"

    def update_debt(self, amount, currency='USD'):
        """Update customer's debt in the specified currency"""
        if currency == 'USD':
            self.total_debt_usd += amount
            if self.total_debt_usd < 0:
                self.total_debt_usd = Decimal('0.00')
        elif currency == 'SOS':
            self.total_debt_sos += amount
            if self.total_debt_sos < 0:
                self.total_debt_sos = Decimal('0.00')
        elif currency == 'ETB':
            self.total_debt_etb += amount
            if self.total_debt_etb < 0:
                self.total_debt_etb = Decimal('0.00')
        self.save()

    @property
    def total_debt(self):
        """Backward compatibility property - returns SOS debt (base currency)"""
        return self.total_debt_sos

    def get_debt_in_currency(self, currency='USD'):
        """Get customer's debt in specified currency"""
        if currency == 'USD':
            return self.total_debt_usd
        elif currency == 'SOS':
            return self.total_debt_sos
        elif currency == 'ETB':
            return self.total_debt_etb
        return Decimal('0.00')

    def get_total_debt_usd_equivalent(self):
        """Get total debt converted to USD equivalent"""
        currency_settings = CurrencySettings.objects.first()
        if currency_settings:
            sos_usd_equivalent = currency_settings.convert_sos_to_usd(self.total_debt_sos)
            etb_usd_equivalent = currency_settings.convert_etb_to_usd(self.total_debt_etb)
            return self.total_debt_usd + sos_usd_equivalent + etb_usd_equivalent
        return self.total_debt_usd

    def get_debt_status(self):
        """Get human-readable debt status based on USD equivalent"""
        total_usd = self.get_total_debt_usd_equivalent()
        if total_usd == 0:
            return "No Debt"
        elif total_usd <= 50:
            return "Low Debt"
        elif total_usd <= 200:
            return "Medium Debt"
        else:
            return "High Debt"

    @classmethod
    def get_total_debt_usd(cls):
        """Get total USD debt across all customers"""
        return cls.objects.aggregate(total=Sum('total_debt_usd'))['total'] or Decimal('0.00')

    @classmethod
    def get_total_debt_sos(cls):
        """Get total SOS debt across all customers"""
        return cls.objects.aggregate(total=Sum('total_debt_sos'))['total'] or Decimal('0.00')

    @classmethod
    def get_total_debt_etb(cls):
        """Get total ETB debt across all customers"""
        return cls.objects.aggregate(total=Sum('total_debt_etb'))['total'] or Decimal('0.00')

    @classmethod
    def get_total_debt(cls):
        """Backward compatibility method - returns total SOS debt (base currency)"""
        return cls.get_total_debt_sos()

    @classmethod
    def get_customers_with_debt(cls):
        """Get customers who have debt in either currency"""
        return cls.objects.filter(
            Q(total_debt_usd__gt=0) | Q(total_debt_sos__gt=0) | Q(total_debt_etb__gt=0)
        ).order_by('-total_debt_usd', '-total_debt_sos', '-total_debt_etb')


class SaleUSD(models.Model):
    """USD Sales transaction model - completely separate from SOS"""
    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, help_text="Optional - allows anonymous sales")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='usd_sales', help_text="Optional - admin user who created the sale")
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Total amount in USD")
    amount_paid = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Amount paid in USD")
    debt_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Debt amount in USD")
    date_created = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=True)

    class Meta:
        verbose_name = "USD Sale"
        verbose_name_plural = "USD Sales"

    def __str__(self):
        customer_name = self.customer.name if self.customer else "Anonymous"
        return f"USD Sale {self.transaction_id} - {customer_name}"

    def calculate_total(self):
        """Calculate and update the total amount for this sale"""
        total = self.items.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
        self.total_amount = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.save()
        return self.total_amount

    def clean(self):
        """Validate debt requirements"""
        from django.core.exceptions import ValidationError
        if self.total_amount is not None and self.amount_paid is not None:
            calculated_debt = max(Decimal('0.00'), self.total_amount - self.amount_paid)
            calculated_debt = calculated_debt.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if calculated_debt > 0 and not self.customer:
                raise ValidationError({
                    'customer': 'Credit sales require a customer. Please select a customer or pay the full amount.'
                })

    def save(self, *args, **kwargs):
        """Override save to automatically recalculate debt_amount"""
        if self.total_amount is not None and self.amount_paid is not None:
            debt = max(Decimal('0.00'), self.total_amount - self.amount_paid)
            self.debt_amount = debt.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def expected_profit_usd(self):
        """Calculate expected profit if paid in full at selling price (in USD)"""
        profit = Decimal('0.00')
        for item in self.items.all():
            margin = item.product.selling_price - item.product.purchase_price
            profit += margin * item.quantity
        return profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def actual_profit_usd(self):
        """Calculate actual profit based on amount paid (in USD)"""
        purchase_cost = Decimal('0.00')
        for item in self.items.all():
            purchase_cost += item.product.purchase_price * item.quantity
        profit = self.amount_paid - purchase_cost
        return profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def is_overpayment(self):
        """Check if this sale has overpayment"""
        return self.amount_paid > self.total_amount

    @property
    def overpayment_amount(self):
        """Calculate overpayment amount (in USD)"""
        if self.is_overpayment:
            amount = self.amount_paid - self.total_amount
            return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')


class SaleSOS(models.Model):
    """SOS Sales transaction model - completely separate from USD"""
    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, help_text="Optional - allows anonymous sales")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='sos_sales', help_text="Optional - admin user who created the sale")
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Total amount in SOS")
    amount_paid = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Amount paid in SOS")
    debt_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Debt amount in SOS")
    date_created = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=True)

    class Meta:
        verbose_name = "SOS Sale"
        verbose_name_plural = "SOS Sales"

    def __str__(self):
        customer_name = self.customer.name if self.customer else "Anonymous"
        return f"SOS Sale {self.transaction_id} - {customer_name}"

    def calculate_total(self):
        """Calculate and update the total amount for this sale"""
        total = self.items.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
        self.total_amount = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.save()
        return self.total_amount

    def clean(self):
        """Validate debt requirements"""
        from django.core.exceptions import ValidationError
        if self.total_amount is not None and self.amount_paid is not None:
            calculated_debt = max(Decimal('0.00'), self.total_amount - self.amount_paid)
            calculated_debt = calculated_debt.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if calculated_debt > 0 and not self.customer:
                raise ValidationError({
                    'customer': 'Credit sales require a customer. Please select a customer or pay the full amount.'
                })

    def save(self, *args, **kwargs):
        """Override save to automatically recalculate debt_amount"""
        if self.total_amount is not None and self.amount_paid is not None:
            debt = max(Decimal('0.00'), self.total_amount - self.amount_paid)
            self.debt_amount = debt.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def expected_profit_usd(self):
        """Calculate expected profit if paid in full at selling price (in USD)"""
        profit = Decimal('0.00')
        for item in self.items.all():
            margin = item.product.selling_price - item.product.purchase_price
            profit += margin * item.quantity
        return profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def actual_profit_usd(self):
        """Calculate actual profit based on amount paid (converted to USD)"""
        currency_settings = CurrencySettings.objects.first()
        usd_to_sos_rate = currency_settings.usd_to_sos_rate if currency_settings else Decimal('8000.00')
        purchase_cost = Decimal('0.00')
        for item in self.items.all():
            purchase_cost += item.product.purchase_price * item.quantity
        amount_paid_usd = self.amount_paid / usd_to_sos_rate if usd_to_sos_rate > 0 else Decimal('0.00')
        profit = amount_paid_usd - purchase_cost
        return profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def is_overpayment(self):
        """Check if this sale has overpayment"""
        return self.amount_paid > self.total_amount

    @property
    def overpayment_amount(self):
        """Calculate overpayment amount (in SOS)"""
        if self.is_overpayment:
            amount = self.amount_paid - self.total_amount
            return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')


class SaleETB(models.Model):
    """ETB Sales transaction model - completely separate from USD/SOS"""
    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, help_text="Optional - allows anonymous sales")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='etb_sales', help_text="Optional - admin user who created the sale")
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Total amount in ETB")
    amount_paid = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Amount paid in ETB")
    debt_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Debt amount in ETB")
    exchange_rate_at_sale = models.DecimalField(
        max_digits=10,
        decimal_places=2,
        default=185.00,
        validators=[MinValueValidator(Decimal('0.01'))],
        help_text="USD to ETB exchange rate at time of sale"
    )
    date_created = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=True)

    class Meta:
        verbose_name = "ETB Sale"
        verbose_name_plural = "ETB Sales"

    def __str__(self):
        customer_name = self.customer.name if self.customer else "Anonymous"
        return f"ETB Sale {self.transaction_id} - {customer_name}"

    def calculate_total(self):
        """Calculate and update the total amount for this sale"""
        total = self.items.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
        self.total_amount = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.save()
        return self.total_amount

    def clean(self):
        """Validate debt requirements"""
        from django.core.exceptions import ValidationError
        if self.total_amount is not None and self.amount_paid is not None:
            calculated_debt = max(Decimal('0.00'), self.total_amount - self.amount_paid)
            calculated_debt = calculated_debt.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            if calculated_debt > 0 and not self.customer:
                raise ValidationError({
                    'customer': 'Credit sales require a customer. Please select a customer or pay the full amount.'
                })

    def save(self, *args, **kwargs):
        """Override save to automatically recalculate debt_amount"""
        if self.total_amount is not None and self.amount_paid is not None:
            debt = max(Decimal('0.00'), self.total_amount - self.amount_paid)
            self.debt_amount = debt.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def expected_profit_usd(self):
        """Calculate expected profit if paid in full at selling price (in USD)"""
        profit = Decimal('0.00')
        for item in self.items.all():
            margin = item.product.selling_price - item.product.purchase_price
            profit += margin * item.quantity
        return profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def actual_profit_usd(self):
        """Calculate actual profit based on amount paid (converted to USD using stored rate)"""
        purchase_cost = Decimal('0.00')
        for item in self.items.all():
            purchase_cost += item.product.purchase_price * item.quantity
        rate = self.exchange_rate_at_sale if self.exchange_rate_at_sale else Decimal('100.00')
        amount_paid_usd = self.amount_paid / rate if rate > 0 else Decimal('0.00')
        profit = amount_paid_usd - purchase_cost
        return profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)

    @property
    def is_overpayment(self):
        """Check if this sale has overpayment"""
        return self.amount_paid > self.total_amount

    @property
    def overpayment_amount(self):
        """Calculate overpayment amount (in ETB)"""
        if self.is_overpayment:
            amount = self.amount_paid - self.total_amount
            return amount.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        return Decimal('0.00')


class Sale(models.Model):
    """Legacy Sales transaction model - kept for backward compatibility"""
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('SOS', 'Somaliland Shilling'),
        ('ETB', 'Ethiopian Birr'),
    ]
    transaction_id = models.UUIDField(default=uuid.uuid4, unique=True, editable=False)
    customer = models.ForeignKey(Customer, on_delete=models.SET_NULL, null=True, blank=True, help_text="Optional - allows anonymous sales")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, related_name='legacy_sales', help_text="Optional - admin user who created the sale")
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='USD')
    total_amount = models.DecimalField(max_digits=20, decimal_places=2, help_text="Total amount in original currency")
    amount_paid = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Amount paid in original currency")
    debt_amount = models.DecimalField(max_digits=20, decimal_places=2, default=0.00, help_text="Debt amount in original currency")
    exchange_rate = models.DecimalField(max_digits=10, decimal_places=2)
    date_created = models.DateTimeField(auto_now_add=True)
    is_completed = models.BooleanField(default=True)

    class Meta:
        verbose_name = "Sale"
        verbose_name_plural = "Sales"

    def __str__(self):
        return f"Sale {self.transaction_id} - {self.customer.name if self.customer else 'Anonymous'}"

    def calculate_total(self):
        """Calculate and update the total amount for this sale"""
        total = self.items.aggregate(total=Sum('total_price'))['total'] or Decimal('0.00')
        self.total_amount = total.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.debt_amount = max(Decimal('0.00'), total - self.amount_paid).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        self.save()
        return self.total_amount

    def get_amount_in_currency(self, target_currency):
        """Get the total amount in the specified currency"""
        currency_settings = CurrencySettings.objects.first()
        if not currency_settings:
            return self.total_amount
        if target_currency == 'USD':
            return currency_settings.convert_sos_to_usd(self.total_amount)
        return self.total_amount

    def get_paid_amount_in_currency(self, target_currency):
        """Get the paid amount in the specified currency"""
        currency_settings = CurrencySettings.objects.first()
        if not currency_settings:
            return self.amount_paid
        if target_currency == 'USD':
            return currency_settings.convert_sos_to_usd(self.amount_paid)
        return self.amount_paid

    def get_debt_amount_in_currency(self, target_currency):
        """Get the debt amount in the specified currency"""
        currency_settings = CurrencySettings.objects.first()
        if not currency_settings:
            return self.debt_amount
        if target_currency == 'USD':
            return currency_settings.convert_sos_to_usd(self.debt_amount)
        return self.debt_amount

    @property
    def total_amount_sos(self):
        """Get total amount in SOS"""
        if self.currency == 'SOS':
            return self.total_amount
        currency_settings = CurrencySettings.objects.first()
        if currency_settings:
            return currency_settings.convert_usd_to_sos(self.total_amount)
        return Decimal('0.00')

    @property
    def total_amount_usd(self):
        """Get total amount in USD"""
        if self.currency == 'USD':
            return self.total_amount
        currency_settings = CurrencySettings.objects.first()
        if currency_settings:
            return currency_settings.convert_sos_to_usd(self.total_amount)
        return Decimal('0.00')

    @property
    def amount_paid_sos(self):
        """Get amount paid in SOS"""
        if self.currency == 'SOS':
            return self.amount_paid
        currency_settings = CurrencySettings.objects.first()
        if currency_settings:
            return currency_settings.convert_usd_to_sos(self.amount_paid)
        return Decimal('0.00')

    @property
    def amount_paid_usd(self):
        """Get amount paid in USD"""
        if self.currency == 'USD':
            return self.amount_paid
        currency_settings = CurrencySettings.objects.first()
        if currency_settings:
            return currency_settings.convert_sos_to_usd(self.amount_paid)
        return Decimal('0.00')

    @property
    def debt_amount_sos(self):
        """Get debt amount in SOS"""
        if self.currency == 'SOS':
            return self.debt_amount
        currency_settings = CurrencySettings.objects.first()
        if currency_settings:
            return currency_settings.convert_usd_to_sos(self.debt_amount)
        return Decimal('0.00')

    @property
    def debt_amount_usd(self):
        """Get debt amount in USD"""
        if self.currency == 'USD':
            return self.debt_amount
        currency_settings = CurrencySettings.objects.first()
        if currency_settings:
            return currency_settings.convert_sos_to_usd(self.debt_amount)
        return Decimal('0.00')

    def get_payment_status(self):
        """Get human-readable payment status"""
        if self.debt_amount == 0:
            return "Fully Paid"
        elif self.amount_paid == 0:
            return "No Payment"
        else:
            return f"Partial Payment"

    def save(self, *args, **kwargs):
        # Calculate debt amount before saving
        self.debt_amount = max(Decimal('0.00'), self.total_amount - self.amount_paid).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)


class SaleItemUSD(models.Model):
    """Individual items in a USD sale"""
    sale = models.ForeignKey(SaleUSD, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=20, decimal_places=2, help_text="Quantity bought")
    unit_price = models.DecimalField(max_digits=20, decimal_places=2, help_text="Unit price in USD")
    total_price = models.DecimalField(max_digits=20, decimal_places=2, help_text="Total price in USD")

    class Meta:
        verbose_name = "USD Sale Item"
        verbose_name_plural = "USD Sale Items"

    def __str__(self):
        return f"{self.product.name} x{self.quantity} (USD)"

    def get_profit_usd(self):
        """Calculate profit for this sale item in USD using Decimal for precision"""
        try:
            base_profit_usd = self.get_base_profit_usd()
            premium_profit_usd = self.get_premium_profit_usd()
            total_profit_usd = base_profit_usd + premium_profit_usd
            return total_profit_usd
        except (ValueError, TypeError, AttributeError, InvalidOperation) as e:
            return Decimal('0.00')

    def get_base_profit_usd(self):
        """Calculate base profit (minimum price - purchase price)"""
        try:
            if not self.product.purchase_price or not self.product.selling_price or not self.quantity:
                return Decimal('0.00')
            purchase_price_usd = Decimal(str(self.product.purchase_price))
            minimum_price_usd = Decimal(str(self.product.selling_price))
            quantity = Decimal(str(self.quantity))
            base_profit_usd = (minimum_price_usd - purchase_price_usd) * quantity
            return base_profit_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, AttributeError, InvalidOperation) as e:
            return Decimal('0.00')

    def get_premium_profit_usd(self):
        """Calculate premium profit (actual price - minimum price + overpayment)"""
        try:
            if not self.unit_price or not self.product.selling_price or not self.quantity:
                return Decimal('0.00')
            unit_price_usd = Decimal(str(self.unit_price))
            minimum_price_usd = Decimal(str(self.product.selling_price))
            quantity = Decimal(str(self.quantity))
            price_premium = (unit_price_usd - minimum_price_usd) * quantity
            overpayment_premium = Decimal('0.00')
            if self.sale.amount_paid > self.sale.total_amount:
                overpayment = self.sale.amount_paid - self.sale.total_amount
                overpayment_premium = Decimal(str(overpayment))
            total_premium_profit = price_premium + overpayment_premium
            return total_premium_profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, AttributeError, InvalidOperation) as e:
            return Decimal('0.00')

    def get_profit(self):
        """Legacy method for backward compatibility - returns float"""
        return float(self.get_profit_usd())

    def clean(self):
        """Validate unit_price and unit type constraints"""
        from django.core.exceptions import ValidationError
        if not self.product:
            return
        if self.product.selling_unit == 'UNIT' or self.product.selling_unit == 'PIECE':
            if self.quantity % 1 != 0 or self.quantity < 1:
                raise ValidationError({
                    'quantity': f'Piece products require whole numbers ≥ 1. You entered {self.quantity}.'
                })
        elif self.product.selling_unit == 'METER':
            if self.product.minimum_sale_length and self.quantity < self.product.minimum_sale_length:
                raise ValidationError({
                    'quantity': f'Minimum length: {self.product.minimum_sale_length}m. You entered {self.quantity}m.'
                })
        if self.unit_price and self.product.selling_price:
            if self.unit_price < self.product.selling_price:
                raise ValidationError({
                    'unit_price': f'Unit price (${self.unit_price}) cannot be below minimum selling price (${self.product.selling_price}). The minimum selling price acts as the floor price for this product.'
                })

    def save(self, *args, **kwargs):
        # Calculate total price before saving
        self.total_price = (self.quantity * self.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.total_price and self.total_price != 0:
            return (self.get_profit() / float(self.total_price)) * 100
        return 0


class SaleItemSOS(models.Model):
    """Individual items in a SOS sale"""
    sale = models.ForeignKey(SaleSOS, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=20, decimal_places=2, help_text="Quantity bought")
    unit_price = models.DecimalField(max_digits=20, decimal_places=2, help_text="Unit price in SOS")
    total_price = models.DecimalField(max_digits=20, decimal_places=2, help_text="Total price in SOS")

    class Meta:
        verbose_name = "SOS Sale Item"
        verbose_name_plural = "SOS Sale Items"

    def __str__(self):
        return f"{self.product.name} x{self.quantity} (SOS)"

    def get_profit_usd(self):
        """Calculate profit for this sale item in USD using Decimal for precision"""
        try:
            base_profit_usd = self.get_base_profit_usd()
            premium_profit_usd = self.get_premium_profit_usd()
            total_profit_usd = base_profit_usd + premium_profit_usd
            return total_profit_usd
        except (ValueError, TypeError, AttributeError, InvalidOperation, ZeroDivisionError) as e:
            return Decimal('0.00')

    def get_base_profit_usd(self):
        """Calculate base profit (minimum price - purchase price)"""
        try:
            if not self.product.purchase_price or not self.product.selling_price or not self.quantity:
                return Decimal('0.00')
            purchase_price_usd = Decimal(str(self.product.purchase_price))
            minimum_price_usd = Decimal(str(self.product.selling_price))
            quantity = Decimal(str(self.quantity))
            base_profit_usd = (minimum_price_usd - purchase_price_usd) * quantity
            return base_profit_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, AttributeError, InvalidOperation) as e:
            return Decimal('0.00')

    def get_premium_profit_usd(self):
        """Calculate premium profit (actual price - minimum price + overpayment)"""
        try:
            if not self.unit_price or not self.product.selling_price or not self.quantity:
                return Decimal('0.00')
            currency_settings = CurrencySettings.objects.first()
            if not currency_settings or currency_settings.usd_to_sos_rate <= 0:
                return Decimal('0.00')
            unit_price_sos = Decimal(str(self.unit_price))
            minimum_price_usd = Decimal(str(self.product.selling_price))
            quantity = Decimal(str(self.quantity))
            actual_price_usd = (unit_price_sos * quantity) / currency_settings.usd_to_sos_rate
            minimum_revenue_usd = minimum_price_usd * quantity
            price_premium = actual_price_usd - minimum_revenue_usd
            overpayment_premium = Decimal('0.00')
            if self.sale.amount_paid > self.sale.total_amount:
                overpayment_sos = self.sale.amount_paid - self.sale.total_amount
                overpayment_premium = overpayment_sos / currency_settings.usd_to_sos_rate
            total_premium_profit = price_premium + overpayment_premium
            return total_premium_profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, AttributeError, InvalidOperation, ZeroDivisionError) as e:
            return Decimal('0.00')

    def get_profit(self):
        """Legacy method for backward compatibility - returns float"""
        return float(self.get_profit_usd())

    def clean(self):
        """Validate that unit_price is not below minimum selling price (converted to SOS)"""
        from django.core.exceptions import ValidationError
        if self.product and self.unit_price and self.product.selling_price:
            currency_settings = CurrencySettings.objects.first()
            if not currency_settings or currency_settings.usd_to_sos_rate <= 0:
                return
            minimum_price_sos = self.product.selling_price * currency_settings.usd_to_sos_rate
            if self.unit_price < minimum_price_sos:
                raise ValidationError({
                    'unit_price': f'Unit price ({self.unit_price} SOS) cannot be below minimum selling price ({minimum_price_sos:.2f} SOS). The minimum selling price acts as the floor price for this product.'
                })

    def save(self, *args, **kwargs):
        # Calculate total price before saving
        self.total_price = (self.quantity * self.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.total_price and self.total_price != 0:
            return (self.get_profit() / float(self.total_price)) * 100
        return 0


class SaleItemETB(models.Model):
    """Individual items in a ETB sale"""
    sale = models.ForeignKey(SaleETB, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=20, decimal_places=2, help_text="Quantity bought")
    unit_price = models.DecimalField(max_digits=20, decimal_places=2, help_text="Unit price in ETB")
    total_price = models.DecimalField(max_digits=20, decimal_places=2, help_text="Total price in ETB")

    class Meta:
        verbose_name = "ETB Sale Item"
        verbose_name_plural = "ETB Sale Items"

    def __str__(self):
        return f"{self.product.name} x{self.quantity} (ETB)"

    def get_profit_usd(self):
        """Calculate profit for this sale item in USD using Decimal for precision"""
        try:
            base_profit_usd = self.get_base_profit_usd()
            premium_profit_usd = self.get_premium_profit_usd()
            total_profit_usd = base_profit_usd + premium_profit_usd
            return total_profit_usd
        except (ValueError, TypeError, AttributeError, InvalidOperation, ZeroDivisionError) as e:
            return Decimal('0.00')

    def get_base_profit_usd(self):
        """Calculate base profit (minimum price - purchase price)"""
        try:
            if not self.product.purchase_price or not self.product.selling_price or not self.quantity:
                return Decimal('0.00')
            purchase_price_usd = Decimal(str(self.product.purchase_price))
            minimum_price_usd = Decimal(str(self.product.selling_price))
            quantity = Decimal(str(self.quantity))
            base_profit_usd = (minimum_price_usd - purchase_price_usd) * quantity
            return base_profit_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, AttributeError, InvalidOperation) as e:
            return Decimal('0.00')

    def get_premium_profit_usd(self):
        """Calculate premium profit (actual price - minimum price + overpayment)
        Uses the exchange rate stored at time of sale for accurate static profit.
        """
        try:
            if not self.unit_price or not self.product.selling_price or not self.quantity:
                return Decimal('0.00')
            exchange_rate = self.sale.exchange_rate_at_sale
            if not exchange_rate or exchange_rate <= 0:
                currency_settings = CurrencySettings.objects.first()
                if not currency_settings or currency_settings.usd_to_etb_rate <= 0:
                    return Decimal('0.00')
                exchange_rate = currency_settings.usd_to_etb_rate
            unit_price_etb = Decimal(str(self.unit_price))
            minimum_price_usd = Decimal(str(self.product.selling_price))
            quantity = Decimal(str(self.quantity))
            actual_price_usd = (unit_price_etb * quantity) / exchange_rate
            minimum_revenue_usd = minimum_price_usd * quantity
            price_premium = actual_price_usd - minimum_revenue_usd
            overpayment_premium = Decimal('0.00')
            if self.sale.amount_paid > self.sale.total_amount:
                overpayment_etb = self.sale.amount_paid - self.sale.total_amount
                overpayment_premium = overpayment_etb / exchange_rate
            total_premium_profit = price_premium + overpayment_premium
            return total_premium_profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, AttributeError, InvalidOperation, ZeroDivisionError) as e:
            return Decimal('0.00')

    def get_profit(self):
        """Legacy method for backward compatibility - returns float"""
        return float(self.get_profit_usd())

    def clean(self):
        """Validate unit_price and unit type constraints"""
        from django.core.exceptions import ValidationError
        if not self.product:
            return
        if self.product.selling_unit == 'UNIT' or self.product.selling_unit == 'PIECE':
            if self.quantity % 1 != 0 or self.quantity < 1:
                raise ValidationError({
                    'quantity': f'Piece products require whole numbers ≥ 1. You entered {self.quantity}.'
                })
        elif self.product.selling_unit == 'METER':
            if self.product.minimum_sale_length and self.quantity < self.product.minimum_sale_length:
                raise ValidationError({
                    'quantity': f'Minimum length: {self.product.minimum_sale_length}m. You entered {self.quantity}m.'
                })
        if self.unit_price and self.product.selling_price:
            currency_settings = CurrencySettings.objects.first()
            if not currency_settings or currency_settings.usd_to_etb_rate <= 0:
                return
            minimum_price_etb = self.product.selling_price * currency_settings.usd_to_etb_rate
            if self.unit_price < minimum_price_etb:
                raise ValidationError({
                    'unit_price': f'Unit price ({self.unit_price} ETB) cannot be below minimum selling price ({minimum_price_etb:.2f} ETB). The minimum selling price acts as the floor price for this product.'
                })

    def save(self, *args, **kwargs):
        # Calculate total price before saving
        self.total_price = (self.quantity * self.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.total_price and self.total_price != 0:
            return (self.get_profit() / float(self.total_price)) * 100
        return 0


class SaleItem(models.Model):
    """Legacy individual items in a sale"""
    sale = models.ForeignKey(Sale, on_delete=models.CASCADE, related_name='items')
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    quantity = models.DecimalField(max_digits=20, decimal_places=2)
    unit_price = models.DecimalField(max_digits=20, decimal_places=2)
    total_price = models.DecimalField(max_digits=20, decimal_places=2)

    class Meta:
        verbose_name = "Sale Item"
        verbose_name_plural = "Sale Items"

    def __str__(self):
        return f"{self.product.name} x{self.quantity}"

    def get_profit_usd(self):
        """Calculate profit for this sale item in USD using Decimal for precision"""
        try:
            base_profit_usd = self.get_base_profit_usd()
            premium_profit_usd = self.get_premium_profit_usd()
            total_profit_usd = base_profit_usd + premium_profit_usd
            return total_profit_usd
        except (ValueError, TypeError, AttributeError, InvalidOperation, ZeroDivisionError) as e:
            return Decimal('0.00')

    def get_base_profit_usd(self):
        """Calculate base profit (minimum price - purchase price)"""
        try:
            if not self.product.purchase_price or not self.product.selling_price or not self.quantity:
                return Decimal('0.00')
            purchase_price_usd = Decimal(str(self.product.purchase_price))
            minimum_price_usd = Decimal(str(self.product.selling_price))
            quantity = Decimal(str(self.quantity))
            base_profit_usd = (minimum_price_usd - purchase_price_usd) * quantity
            return base_profit_usd.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, AttributeError, InvalidOperation) as e:
            return Decimal('0.00')

    def get_premium_profit_usd(self):
        """Calculate premium profit (actual price - minimum price + overpayment)"""
        try:
            if not self.unit_price or not self.product.selling_price or not self.quantity:
                return Decimal('0.00')
            sale_currency = self.sale.currency
            minimum_price_usd = Decimal(str(self.product.selling_price))
            quantity = Decimal(str(self.quantity))
            if sale_currency == 'USD':
                unit_price_usd = Decimal(str(self.unit_price))
                price_premium = (unit_price_usd - minimum_price_usd) * quantity
                overpayment_premium = Decimal('0.00')
                if self.sale.amount_paid > self.sale.total_amount:
                    overpayment = self.sale.amount_paid - self.sale.total_amount
                    overpayment_premium = Decimal(str(overpayment))
                total_premium_profit = price_premium + overpayment_premium
                return total_premium_profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
            else:  # SOS currency
                currency_settings = CurrencySettings.objects.first()
                if not currency_settings or currency_settings.usd_to_sos_rate <= 0:
                    return Decimal('0.00')
                unit_price_sos = Decimal(str(self.unit_price))
                actual_price_usd = (unit_price_sos * quantity) / currency_settings.usd_to_sos_rate
                minimum_revenue_usd = minimum_price_usd * quantity
                price_premium = actual_price_usd - minimum_revenue_usd
                overpayment_premium = Decimal('0.00')
                if self.sale.amount_paid > self.sale.total_amount:
                    overpayment_sos = self.sale.amount_paid - self.sale.total_amount
                    overpayment_premium = overpayment_sos / currency_settings.usd_to_sos_rate
                total_premium_profit = price_premium + overpayment_premium
                return total_premium_profit.quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        except (ValueError, TypeError, AttributeError, InvalidOperation, ZeroDivisionError) as e:
            return Decimal('0.00')

    def get_profit(self):
        """Legacy method for backward compatibility - returns float"""
        return float(self.get_profit_usd())

    def clean(self):
        """Validate unit_price and unit type constraints"""
        from django.core.exceptions import ValidationError
        if not self.product:
            return
        if self.product.selling_unit == 'UNIT' or self.product.selling_unit == 'PIECE':
            if self.quantity % 1 != 0 or self.quantity < 1:
                raise ValidationError({
                    'quantity': f'Piece products require whole numbers ≥ 1. You entered {self.quantity}.'
                })
        elif self.product.selling_unit == 'METER':
            if self.product.minimum_sale_length and self.quantity < self.product.minimum_sale_length:
                raise ValidationError({
                    'quantity': f'Minimum length: {self.product.minimum_sale_length}m. You entered {self.quantity}m.'
                })
        if self.unit_price and self.product.selling_price:
            currency_settings = CurrencySettings.objects.first()
            if not currency_settings or currency_settings.usd_to_sos_rate <= 0:
                return
            minimum_price_sos = self.product.selling_price * currency_settings.usd_to_sos_rate
            if self.unit_price < minimum_price_sos:
                raise ValidationError({
                    'unit_price': f'Unit price ({self.unit_price} SOS) cannot be below minimum selling price ({minimum_price_sos:.2f} SOS). The minimum selling price acts as the floor price for this product.'
                })

    def save(self, *args, **kwargs):
        # Calculate total price before saving
        self.total_price = (self.quantity * self.unit_price).quantize(Decimal('0.01'), rounding=ROUND_HALF_UP)
        super().save(*args, **kwargs)

    @property
    def profit_margin(self):
        """Calculate profit margin percentage"""
        if self.total_price and self.total_price != 0:
            return (self.get_profit() / float(self.total_price)) * 100
        return 0


class InventoryLog(models.Model):
    """Log of all inventory changes"""
    ACTION_CHOICES = [
        ('RESTOCK', 'Restock'),
        ('SALE', 'Sale'),
        ('ADJUSTMENT', 'Manual Adjustment'),
    ]
    product = models.ForeignKey(Product, on_delete=models.CASCADE)
    action = models.CharField(max_length=20, choices=ACTION_CHOICES)
    quantity_change = models.DecimalField(max_digits=10, decimal_places=2)
    old_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    new_quantity = models.DecimalField(max_digits=10, decimal_places=2)
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='inventory_logs')
    notes = models.TextField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    related_sale = models.ForeignKey(Sale, on_delete=models.SET_NULL, null=True, blank=True)
    related_sale_usd = models.ForeignKey(SaleUSD, on_delete=models.SET_NULL, null=True, blank=True)
    related_sale_sos = models.ForeignKey(SaleSOS, on_delete=models.SET_NULL, null=True, blank=True)
    related_sale_etb = models.ForeignKey(SaleETB, on_delete=models.SET_NULL, null=True, blank=True)

    class Meta:
        verbose_name = "Inventory Log"
        verbose_name_plural = "Inventory Logs"

    def __str__(self):
        return f"{self.product.name} - {self.action} ({self.quantity_change:+.2f})"


class DebtPaymentUSD(models.Model):
    """USD debt payments - completely separate from SOS"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Payment amount in USD")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='usd_debt_payments')
    date_created = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "USD Debt Payment"
        verbose_name_plural = "USD Debt Payments"

    def __str__(self):
        return f"{self.customer.name} - ${self.amount} USD"


class DebtPaymentSOS(models.Model):
    """SOS debt payments - completely separate from USD"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Payment amount in SOS")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='sos_debt_payments')
    date_created = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "SOS Debt Payment"
        verbose_name_plural = "SOS Debt Payments"

    def __str__(self):
        return f"{self.customer.name} - {self.amount} SOS"


class DebtPaymentETB(models.Model):
    """ETB debt payments - completely separate from USD/SOS"""
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Payment amount in ETB")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='etb_debt_payments')
    date_created = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "ETB Debt Payment"
        verbose_name_plural = "ETB Debt Payments"

    def __str__(self):
        return f"{self.customer.name} - {self.amount} ETB"


class DebtPayment(models.Model):
    """Legacy Customer debt payments - kept for backward compatibility"""
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('SOS', 'Somaliland Shilling'),
        ('ETB', 'Ethiopian Birr'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE)
    amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Payment amount in base currency (SOS)")
    original_currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES, default='SOS', help_text="Original payment currency")
    original_amount = models.DecimalField(max_digits=10, decimal_places=2, default=0.00, help_text="Original payment amount in original currency")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='legacy_debt_payments')
    date_created = models.DateTimeField(auto_now_add=True)
    notes = models.TextField(blank=True)

    class Meta:
        verbose_name = "Debt Payment"
        verbose_name_plural = "Debt Payments"

    def __str__(self):
        return f"{self.customer.name} - {self.original_currency} {self.original_amount}"

    def convert_to_sos_and_save_original(self, original_currency, original_amount):
        """Convert payment to SOS (base currency) and save original amounts"""
        currency_settings = CurrencySettings.objects.first()
        if not currency_settings:
            return
        self.original_currency = original_currency
        self.original_amount = original_amount
        if original_currency == 'USD':
            self.amount = currency_settings.convert_usd_to_sos(original_amount)
        else:
            self.amount = original_amount

    def get_amount_in_currency(self, target_currency):
        """Get the payment amount in the specified currency"""
        currency_settings = CurrencySettings.objects.first()
        if not currency_settings:
            return self.amount
        if target_currency == 'USD':
            return currency_settings.convert_sos_to_usd(self.amount)
        return self.amount


class Receipt(models.Model):
    """Digital receipts stored in database"""
    sale = models.OneToOneField(Sale, on_delete=models.CASCADE)
    receipt_number = models.CharField(max_length=20, unique=True)
    content = models.TextField()
    date_created = models.DateTimeField(auto_now_add=True)

    class Meta:
        verbose_name = "Receipt"
        verbose_name_plural = "Receipts"

    def __str__(self):
        return f"Receipt {self.receipt_number}"


class DebtCorrection(models.Model):
    """Model to track manual debt corrections/adjustments"""
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('SOS', 'Somaliland Shilling'),
        ('ETB', 'Ethiopian Birr'),
    ]
    customer = models.ForeignKey(Customer, on_delete=models.CASCADE, related_name='debt_corrections')
    currency = models.CharField(max_length=3, choices=CURRENCY_CHOICES)
    old_debt_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Previous debt amount")
    new_debt_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="New debt amount")
    adjustment_amount = models.DecimalField(max_digits=10, decimal_places=2, help_text="Amount of adjustment (positive or negative)")
    reason = models.TextField(help_text="Reason for the debt correction")
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, related_name='debt_corrections')
    date_created = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "Debt Correction"
        verbose_name_plural = "Debt Corrections"
        ordering = ['-date_created']

    def __str__(self):
        return f"{self.customer.name} - {self.currency} {self.adjustment_amount:+.2f} ({self.date_created.strftime('%Y-%m-%d')})"

    def save(self, *args, **kwargs):
        # Calculate adjustment amount if not provided
        if not self.adjustment_amount:
            self.adjustment_amount = self.new_debt_amount - self.old_debt_amount
        super().save(*args, **kwargs)


class AuditLog(models.Model):
    """System audit log for all critical actions"""
    ACTION_CHOICES = [
        ('SALE_CREATED', 'Sale Created'),
        ('INVENTORY_ADJUSTED', 'Inventory Adjusted'),
        ('DEBT_PAID', 'Debt Payment'),
        ('DEBT_ADDED', 'Debt Added'),
        ('DEBT_CORRECTED', 'Debt Corrected'),
        ('DEBT_MANUALLY_ADJUSTED', 'Debt Manually Adjusted'),
        ('CUSTOMER_ADDED', 'Customer Added'),
        ('CURRENCY_UPDATED', 'Currency Rate Updated'),
    ]
    user = models.ForeignKey(User, on_delete=models.SET_NULL, null=True, blank=True, help_text="Admin user who performed the action (null for anonymous/system actions)")
    action = models.CharField(max_length=50, choices=ACTION_CHOICES)
    object_type = models.CharField(max_length=50)
    object_id = models.CharField(max_length=50)
    details = models.TextField(blank=True)
    date_created = models.DateTimeField(auto_now_add=True)
    ip_address = models.GenericIPAddressField(null=True, blank=True)

    class Meta:
        verbose_name = "Audit Log"
        verbose_name_plural = "Audit Logs"
        ordering = ['-date_created']

    def __str__(self):
        username = self.user.username if self.user else "System"
        return f"{username} - {self.action} - {self.date_created}"