from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.core.exceptions import ValidationError
from django.utils import timezone
from .models import User, Product, Customer, Sale, SaleItem, SaleItemUSD, SaleItemSOS, SaleItemETB, InventoryLog, DebtPayment, CurrencySettings, DebtCorrection


class CustomUserCreationForm(UserCreationForm):
    """Admin user creation form"""
    phone = forms.CharField(max_length=15, required=False, help_text="Optional phone number")
    
    class Meta:
        model = User
        fields = ('username', 'first_name', 'last_name', 'email', 'phone', 'password1', 'password2')
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        # Add CSS classes to form fields
        for field_name, field in self.fields.items():
            if isinstance(field.widget, (forms.TextInput, forms.EmailInput, forms.PasswordInput)):
                field.widget.attrs.update({'class': 'form-control'})
            elif isinstance(field.widget, forms.CheckboxInput):
                field.widget.attrs.update({'class': 'form-check-input'})


class ProductForm(forms.ModelForm):
    """Product form with conditional purchase price field"""
    
    class Meta:
        model = Product
        fields = ['name', 'brand', 'category', 'purchase_price', 'selling_price', 'current_stock', 'low_stock_threshold', 'is_active']
        
    def __init__(self, *args, **kwargs):
        user = kwargs.pop('user', None)
        super().__init__(*args, **kwargs)
        
        # Hide purchase price from non-superusers
        if user and not user.is_superuser:
            if 'purchase_price' in self.fields:
                del self.fields['purchase_price']


class CustomerForm(forms.ModelForm):
    """Customer form with phone validation"""
    
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={'class': 'form-control'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            # Check if phone already exists (excluding current instance)
            existing_customer = Customer.objects.filter(phone=phone)
            if self.instance.pk:
                existing_customer = existing_customer.exclude(pk=self.instance.pk)
            
            if existing_customer.exists():
                raise ValidationError("A customer with this phone number already exists.")
        return phone


class CustomerEditForm(forms.ModelForm):
    """Customer edit form with enhanced validation"""
    
    class Meta:
        model = Customer
        fields = ['name', 'phone', 'is_active']
        widgets = {
            'name': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter customer name'
            }),
            'phone': forms.TextInput(attrs={
                'class': 'form-control',
                'placeholder': 'Enter phone number'
            }),
            'is_active': forms.CheckboxInput(attrs={'class': 'form-check-input'}),
        }
        
    def clean_phone(self):
        phone = self.cleaned_data.get('phone')
        if phone:
            # Check if phone already exists (excluding current instance)
            existing_customer = Customer.objects.filter(phone=phone)
            if self.instance.pk:
                existing_customer = existing_customer.exclude(pk=self.instance.pk)
            
            if existing_customer.exists():
                raise ValidationError("A customer with this phone number already exists.")
        return phone
    
    def clean_name(self):
        name = self.cleaned_data.get('name')
        if name:
            name = name.strip()
            if len(name) < 2:
                raise ValidationError("Customer name must be at least 2 characters long.")
        return name


class SaleForm(forms.ModelForm):
    """Sale form - simplified since we're handling items separately"""
    
    class Meta:
        model = Sale
        fields = ['customer', 'currency', 'amount_paid']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['customer'].queryset = Customer.objects.filter(is_active=True)
        # Set default values
        if not self.instance.pk:
            self.fields['amount_paid'].initial = 0


class SaleItemForm(forms.ModelForm):
    """Sale item form with stock validation"""
    
    class Meta:
        model = SaleItem
        fields = ['product', 'quantity', 'unit_price']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True, current_stock__gt=0)
        
    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        product = self.cleaned_data.get('product')
        
        if product and quantity:
            # Check if we're editing an existing item
            if self.instance.pk:
                # For existing items, check against current stock plus the existing quantity
                available_stock = product.current_stock + self.instance.quantity
                if quantity > available_stock:
                    raise ValidationError(f"Only {available_stock} units available in stock.")
            else:
                # For new items, check against current stock
                if quantity > product.current_stock:
                    raise ValidationError(f"Only {product.current_stock} units available in stock.")
            
            if quantity <= 0:
                raise ValidationError("Quantity must be greater than 0.")
                
        return quantity
    
    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        product = self.cleaned_data.get('product')
        
        if product and unit_price and product.selling_price:
            # Get the sale currency to determine how to validate
            sale = getattr(self.instance, 'sale', None)
            if sale:
                sale_currency = sale.currency
            else:
                # Default to USD if no sale context
                sale_currency = 'USD'
            
            if sale_currency == 'USD':
                # For USD sales, compare directly with minimum selling price
                if unit_price < product.selling_price:
                    raise ValidationError(f'Unit price (${unit_price}) cannot be below minimum selling price (${product.selling_price}). The minimum selling price acts as the floor price for this product.')
            else:  # SOS currency
                # For SOS sales, convert minimum selling price to SOS for comparison
                from .models import CurrencySettings
                currency_settings = CurrencySettings.objects.first()
                if currency_settings and currency_settings.usd_to_sos_rate > 0:
                    minimum_price_sos = product.selling_price * currency_settings.usd_to_sos_rate
                    if unit_price < minimum_price_sos:
                        raise ValidationError(f'Unit price ({unit_price} SOS) cannot be below minimum selling price ({minimum_price_sos:.2f} SOS). The minimum selling price acts as the floor price for this product.')
        
        return unit_price


class SaleItemUSDForm(forms.ModelForm):
    """Sale item form for USD sales with stock and price validation"""
    
    class Meta:
        model = SaleItemUSD
        fields = ['product', 'quantity', 'unit_price']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True, current_stock__gt=0)
        
    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        product = self.cleaned_data.get('product')
        
        if product and quantity:
            # Check if we're editing an existing item
            if self.instance.pk:
                # For existing items, check against current stock plus the existing quantity
                available_stock = product.current_stock + self.instance.quantity
                if quantity > available_stock:
                    raise ValidationError(f"Only {available_stock} units available in stock.")
            else:
                # For new items, check against current stock
                if quantity > product.current_stock:
                    raise ValidationError(f"Only {product.current_stock} units available in stock.")
            
            if quantity <= 0:
                raise ValidationError("Quantity must be greater than 0.")
                
        return quantity
    
    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        product = self.cleaned_data.get('product')
        
        if product and unit_price and product.selling_price:
            # For USD sales, compare directly with minimum selling price
            if unit_price < product.selling_price:
                raise ValidationError(f'Unit price (${unit_price}) cannot be below minimum selling price (${product.selling_price}). The minimum selling price acts as the floor price for this product.')
        
        return unit_price


class SaleItemSOSForm(forms.ModelForm):
    """Sale item form for SOS sales with stock and price validation"""
    
    class Meta:
        model = SaleItemSOS
        fields = ['product', 'quantity', 'unit_price']
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True, current_stock__gt=0)
        
    def clean_quantity(self):
        quantity = self.cleaned_data.get('quantity')
        product = self.cleaned_data.get('product')
        
        if product and quantity:
            # Check if we're editing an existing item
            if self.instance.pk:
                # For existing items, check against current stock plus the existing quantity
                available_stock = product.current_stock + self.instance.quantity
                if quantity > available_stock:
                    raise ValidationError(f"Only {available_stock} units available in stock.")
            else:
                # For new items, check against current stock
                if quantity > product.current_stock:
                    raise ValidationError(f"Only {product.current_stock} units available in stock.")
            
            if quantity <= 0:
                raise ValidationError("Quantity must be greater than 0.")
                
        return quantity
    
    def clean_unit_price(self):
        unit_price = self.cleaned_data.get('unit_price')
        product = self.cleaned_data.get('product')
        
        if product and unit_price and product.selling_price:
            # For SOS sales, convert minimum selling price to SOS for comparison
            from .models import CurrencySettings
            currency_settings = CurrencySettings.objects.first()
            if currency_settings and currency_settings.usd_to_sos_rate > 0:
                minimum_price_sos = product.selling_price * currency_settings.usd_to_sos_rate
                if unit_price < minimum_price_sos:
                    raise ValidationError(f'Unit price ({unit_price} SOS) cannot be below minimum selling price ({minimum_price_sos:.2f} SOS). The minimum selling price acts as the floor price for this product.')
        
        return unit_price


class InventoryAdjustmentForm(forms.ModelForm):
    """Inventory adjustment form for restocking"""
    
    class Meta:
        model = InventoryLog
        fields = ['product', 'quantity_change', 'notes']
        widgets = {
            'quantity_change': forms.NumberInput(attrs={'min': '1'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        self.fields['product'].queryset = Product.objects.filter(is_active=True)
        
    def clean_quantity_change(self):
        quantity_change = self.cleaned_data.get('quantity_change')
        if quantity_change <= 0:
            raise ValidationError("Quantity change must be positive for restocking.")
        return quantity_change


class DebtPaymentForm(forms.ModelForm):
    """Debt payment form with currency selection"""
    
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('SOS', 'Somaliland Shilling'),
        ('ETB', 'Ethiopian Birr'),
    ]
    
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        initial='USD',
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = DebtPayment
        fields = ['amount', 'pno', 'notes']  # Removed customer field since it's passed from view
        widgets = {
            'pno': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Enter Receipt Number (PNO)'}),
            'notes': forms.Textarea(attrs={'rows': 3}),
        }
        
    def clean_amount(self):
        amount = self.cleaned_data.get('amount')
        if amount <= 0:
            raise ValidationError("Payment amount must be greater than 0.")
        return amount
    
    def clean(self):
        cleaned_data = super().clean()
        amount = cleaned_data.get('amount')
        currency = cleaned_data.get('currency')
        
        # Get customer from the form's instance or from the view context
        customer = getattr(self, 'customer', None)
        if customer and amount and currency:
            if currency == 'USD':
                customer_debt = customer.total_debt_usd
            elif currency == 'SOS':  # SOS
                customer_debt = customer.total_debt_sos
            else:  # ETB
                customer_debt = customer.total_debt_etb
                
            if amount > customer_debt:
                raise ValidationError(f'Payment amount ({amount} {currency}) cannot exceed total debt ({customer_debt} {currency})')
        
        return cleaned_data
    
    def __init__(self, *args, **kwargs):
        # Extract customer from kwargs if provided
        self.customer = kwargs.pop('customer', None)
        super().__init__(*args, **kwargs)
        # Add CSS classes to form fields
        self.fields['amount'].widget.attrs.update({'class': 'form-control', 'step': '0.01', 'min': '0.01'})
        self.fields['notes'].widget.attrs.update({'class': 'form-control'})


class CustomerSearchForm(forms.Form):
    """Customer search form"""
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search by name or phone number...',
            'class': 'form-control'
        })
    )


class ProductSearchForm(forms.Form):
    """Product search form"""
    search = forms.CharField(
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={
            'placeholder': 'Search products...',
            'class': 'form-control'
        })
    )
    category = forms.ModelChoiceField(
        queryset=None,
        required=False,
        empty_label="All Categories",
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        from .models import Category
        self.fields['category'].queryset = Category.objects.all()


class CurrencySettingsForm(forms.ModelForm):
    """Currency settings form"""
    
    class Meta:
        model = CurrencySettings
        fields = ['usd_to_sos_rate', 'usd_to_etb_rate']
        widgets = {
            'usd_to_sos_rate': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.01',
                'class': 'form-control',
                'placeholder': '8000.00'
            }),
            'usd_to_etb_rate': forms.NumberInput(attrs={
                'step': '0.01',
                'min': '0.01',
                'class': 'form-control',
                'placeholder': '100.00'
            })
        }
        
    def clean_usd_to_etb_rate(self):
        rate = self.cleaned_data.get('usd_to_etb_rate')
        if rate <= 0:
            raise ValidationError("Exchange rate must be greater than 0.")
        return rate
        
    def clean_usd_to_sos_rate(self):
        rate = self.cleaned_data.get('usd_to_sos_rate')
        if rate <= 0:
            raise ValidationError("Exchange rate must be greater than 0.")
        return rate


class DebtCorrectionForm(forms.ModelForm):
    """Form for manual debt correction/adjustment"""
    
    CURRENCY_CHOICES = [
        ('USD', 'US Dollar'),
        ('SOS', 'Somaliland Shilling'),
        ('ETB', 'Ethiopian Birr'),
    ]
    
    currency = forms.ChoiceField(
        choices=CURRENCY_CHOICES,
        widget=forms.Select(attrs={'class': 'form-control'})
    )
    
    class Meta:
        model = DebtCorrection
        fields = ['currency', 'new_debt_amount', 'reason']
        widgets = {
            'new_debt_amount': forms.NumberInput(attrs={
                'class': 'form-control',
                'step': '0.01',
                'min': '0.00'
            }),
            'reason': forms.Textarea(attrs={
                'class': 'form-control',
                'rows': 4,
                'placeholder': 'Please provide a detailed reason for this debt correction...'
            })
        }
    
    def __init__(self, *args, **kwargs):
        self.customer = kwargs.pop('customer', None)
        super().__init__(*args, **kwargs)
        
        if self.customer:
            # Set initial values based on current customer debt
            self.fields['currency'].initial = 'USD'  # Default to USD
            self.fields['new_debt_amount'].initial = self.customer.total_debt_usd
    
    def clean_new_debt_amount(self):
        new_amount = self.cleaned_data.get('new_debt_amount')
        if new_amount < 0:
            raise ValidationError("Debt amount cannot be negative.")
        return new_amount
    
    def clean(self):
        cleaned_data = super().clean()
        currency = cleaned_data.get('currency')
        new_amount = cleaned_data.get('new_debt_amount')
        
        if self.customer and currency and new_amount is not None:
            # Get current debt amount for the selected currency
            if currency == 'USD':
                current_debt = self.customer.total_debt_usd
            elif currency == 'SOS':  # SOS
                current_debt = self.customer.total_debt_sos
            else:  # ETB
                current_debt = self.customer.total_debt_etb
            
            # Calculate the adjustment amount
            adjustment = new_amount - current_debt
            
            # Store the adjustment amount for use in the view
            cleaned_data['adjustment_amount'] = adjustment
            cleaned_data['old_debt_amount'] = current_debt
        
        return cleaned_data