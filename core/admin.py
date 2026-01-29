from django.contrib import admin
from django.contrib.auth.admin import UserAdmin
from django.utils.html import format_html
from django.urls import reverse
from django.utils.safestring import mark_safe
from .models import (
    User, CurrencySettings, Category, Product, Customer, 
    Sale, SaleItem, InventoryLog, DebtPayment, Receipt, AuditLog,
    SaleUSD, SaleSOS, SaleETB, SaleItemUSD, SaleItemSOS, SaleItemETB,
    DebtPaymentUSD, DebtPaymentSOS, DebtPaymentETB, DebtCorrection
)


@admin.register(User)
class CustomUserAdmin(UserAdmin):
    list_display = ('username', 'get_full_name', 'phone', 'is_active', 'date_created')
    list_filter = ('is_superuser', 'is_active', 'date_created')
    search_fields = ('username', 'first_name', 'last_name', 'email', 'phone')
    ordering = ('-date_created',)
    
    fieldsets = (
        (None, {'fields': ('username', 'password')}),
        ('Personal info', {'fields': ('first_name', 'last_name', 'email', 'phone')}),
        ('Permissions', {
            'fields': ('is_active', 'is_superuser', 'groups', 'user_permissions'),
        }),
        ('Important dates', {'fields': ('last_login', 'date_joined')}),
    )
    
    add_fieldsets = (
        (None, {
            'classes': ('wide',),
            'fields': ('username', 'password1', 'password2', 'first_name', 'last_name', 'email', 'phone'),
        }),
    )


@admin.register(CurrencySettings)
class CurrencySettingsAdmin(admin.ModelAdmin):
    list_display = ('usd_to_sos_rate', 'sos_to_usd_rate', 'date_updated', 'updated_by')
    readonly_fields = ('sos_to_usd_rate', 'date_updated', 'updated_by')
    fieldsets = (
        ('Exchange Rates', {
            'fields': ('usd_to_sos_rate', 'sos_to_usd_rate'),
            'description': 'USD to SOS rate is editable. SOS to USD rate is automatically calculated.'
        }),
        ('System Info', {
            'fields': ('date_updated', 'updated_by'),
            'classes': ('collapse',)
        }),
    )
    
    def save_model(self, request, obj, form, change):
        obj.updated_by = request.user
        super().save_model(request, obj, form, change)


@admin.register(Category)
class CategoryAdmin(admin.ModelAdmin):
    list_display = ('name', 'description', 'date_created', 'product_count')
    search_fields = ('name', 'description')
    ordering = ('name',)
    
    def product_count(self, obj):
        return obj.product_set.count()
    product_count.short_description = 'Products'


@admin.register(Product)
class ProductAdmin(admin.ModelAdmin):
    list_display = ('name', 'brand', 'category', 'selling_price', 'current_stock', 'low_stock_threshold', 'is_low_stock', 'profit_margin', 'is_active')
    list_filter = ('category', 'brand', 'is_active')
    search_fields = ('name', 'brand', 'category__name')
    ordering = ('name',)
    readonly_fields = ('date_added', 'date_updated', 'profit_margin', 'is_low_stock')
    
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'brand', 'category', 'is_active')
        }),
        ('Pricing (Superuser Only)', {
            'fields': ('purchase_price', 'selling_price'),
            'classes': ('collapse',)
        }),
        ('Inventory', {
            'fields': ('current_stock', 'low_stock_threshold')
        }),
        ('System Info', {
            'fields': ('date_added', 'date_updated', 'profit_margin', 'is_low_stock'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            # Hide purchase price from non-superusers
            return qs.only('id', 'name', 'brand', 'category_id', 'selling_price', 'current_stock', 'low_stock_threshold', 'date_added', 'date_updated', 'is_active')
        return qs


class DebtCorrectionInline(admin.TabularInline):
    """Inline admin for debt corrections"""
    model = DebtCorrection
    extra = 0
    readonly_fields = ('date_created', 'adjustment_amount')
    fields = ('currency', 'old_debt_amount', 'new_debt_amount', 'adjustment_amount', 'reason', 'date_created')
    
    def has_add_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def has_change_permission(self, request, obj=None):
        return False  # Make corrections read-only in admin
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser


@admin.register(Customer)
class CustomerAdmin(admin.ModelAdmin):
    list_display = ('name', 'phone', 'total_debt_usd', 'total_debt_sos', 'debt_usd_equivalent', 'last_purchase_date', 'date_created', 'is_active')
    list_filter = ('is_active', 'date_created', 'last_purchase_date')
    search_fields = ('name', 'phone')
    ordering = ('-date_created',)
    readonly_fields = ('date_created', 'last_purchase_date', 'debt_usd_equivalent')
    inlines = [DebtCorrectionInline]
    fieldsets = (
        ('Basic Information', {
            'fields': ('name', 'phone', 'is_active')
        }),
        ('Debt Information', {
            'fields': ('total_debt_usd', 'total_debt_sos', 'debt_usd_equivalent'),
            'description': 'Separate USD and SOS debt tracking. Use the debt correction form for manual adjustments.'
        }),
        ('System Info', {
            'fields': ('date_created', 'last_purchase_date'),
            'classes': ('collapse',)
        }),
    )
    
    def debt_usd_equivalent(self, obj):
        """Display total debt in USD equivalent"""
        return f"${obj.get_total_debt_usd_equivalent():.2f}"
    debt_usd_equivalent.short_description = 'Total Debt (USD Eq.)'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related()
    
    def has_change_permission(self, request, obj=None):
        """Only allow superusers to edit customer debt"""
        return request.user.is_superuser


class SaleItemInline(admin.TabularInline):
    model = SaleItem
    extra = 0
    readonly_fields = ('total_price',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        if not request.user.is_superuser:
            # Hide purchase price from non-superusers
            return qs.select_related('product').only(
                'id', 'sale_id', 'product_id', 'quantity', 'unit_price', 'total_price',
                'product__name', 'product__brand'
            )
        return qs


@admin.register(Sale)
class SaleAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'customer', 'currency', 'total_amount', 'total_in_sos', 'debt_amount', 'date_created')
    list_filter = ('currency', 'date_created', 'is_completed')
    search_fields = ('transaction_id', 'customer__name', 'customer__phone')
    ordering = ('-date_created',)
    readonly_fields = ('transaction_id', 'debt_amount', 'date_created', 'total_in_sos', 'paid_in_sos', 'debt_in_sos')
    inlines = [SaleItemInline]
    
    fieldsets = (
        ('Transaction Info', {
            'fields': ('transaction_id', 'customer', 'currency', 'exchange_rate')
        }),
        ('Amounts (Original Currency)', {
            'fields': ('total_amount', 'amount_paid', 'debt_amount'),
            'description': 'All amounts stored in original currency'
        }),
        ('Converted Amounts (SOS)', {
            'fields': ('total_in_sos', 'paid_in_sos', 'debt_in_sos'),
            'classes': ('collapse',)
        }),
        ('Status', {
            'fields': ('is_completed',)
        }),
        ('System Info', {
            'fields': ('date_created',),
            'classes': ('collapse',)
        }),
    )
    
    def total_in_sos(self, obj):
        """Display total amount in SOS"""
        return f"{obj.get_amount_in_currency('SOS'):.0f} SOS"
    total_in_sos.short_description = 'Total (SOS)'
    
    def paid_in_sos(self, obj):
        """Display paid amount in SOS"""
        return f"{obj.get_paid_amount_in_currency('SOS'):.0f} SOS"
    paid_in_sos.short_description = 'Paid (SOS)'
    
    def debt_in_sos(self, obj):
        """Display debt amount in SOS"""
        return f"{obj.get_debt_amount_in_currency('SOS'):.0f} SOS"
    debt_in_sos.short_description = 'Debt (SOS)'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer', 'user')


@admin.register(SaleItem)
class SaleItemAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price', 'total_price')
    list_filter = ('sale__currency', 'sale__date_created')
    search_fields = ('sale__transaction_id', 'product__name', 'product__brand')
    ordering = ('-sale__date_created',)
    readonly_fields = ('total_price',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('sale', 'product')


class SaleItemUSDInline(admin.TabularInline):
    model = SaleItemUSD
    extra = 0
    readonly_fields = ('total_price',)
    fields = ('product', 'quantity', 'unit_price', 'total_price')


class SaleItemSOSInline(admin.TabularInline):
    model = SaleItemSOS
    extra = 0
    readonly_fields = ('total_price',)
    fields = ('product', 'quantity', 'unit_price', 'total_price')


class SaleItemETBInline(admin.TabularInline):
    model = SaleItemETB
    extra = 0
    readonly_fields = ('total_price',)
    fields = ('product', 'quantity', 'unit_price', 'total_price')


@admin.register(SaleUSD)
class SaleUSDAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'customer', 'total_amount', 'amount_paid', 'debt_amount', 'total_amount_etb', 'date_created', 'is_completed')
    list_filter = ('is_completed', 'date_created')
    search_fields = ('customer__name', 'customer__phone', 'transaction_id')
    ordering = ('-date_created',)
    readonly_fields = ('transaction_id', 'date_created', 'total_amount_etb', 'amount_paid_etb', 'debt_amount_etb')
    inlines = [SaleItemUSDInline]
    fieldsets = (
        ('Transaction Details', {
            'fields': ('transaction_id', 'customer', 'user')
        }),
        ('USD Amounts', {
            'fields': ('total_amount', 'amount_paid', 'debt_amount'),
            'description': 'All amounts in USD'
        }),
        ('ETB Equivalents', {
            'fields': ('total_amount_etb', 'amount_paid_etb', 'debt_amount_etb'),
            'description': 'Converted to ETB using current exchange rate',
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': ('date_created', 'is_completed'),
            'classes': ('collapse',)
        }),
    )
    
    def total_amount_etb(self, obj):
        """Display total amount in ETB"""
        from .models import CurrencySettings
        settings = CurrencySettings.objects.first()
        if settings:
            etb_amount = obj.total_amount * settings.usd_to_etb_rate
            return f"{etb_amount:,.2f} ETB"
        return "N/A"
    total_amount_etb.short_description = 'Total (ETB)'
    
    def amount_paid_etb(self, obj):
        """Display amount paid in ETB"""
        from .models import CurrencySettings
        settings = CurrencySettings.objects.first()
        if settings:
            etb_amount = obj.amount_paid * settings.usd_to_etb_rate
            return f"{etb_amount:,.2f} ETB"
        return "N/A"
    amount_paid_etb.short_description = 'Paid (ETB)'
    
    def debt_amount_etb(self, obj):
        """Display debt amount in ETB"""
        from .models import CurrencySettings
        settings = CurrencySettings.objects.first()
        if settings:
            etb_amount = obj.debt_amount * settings.usd_to_etb_rate
            return f"{etb_amount:,.2f} ETB"
        return "N/A"
    debt_amount_etb.short_description = 'Debt (ETB)'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer', 'user').prefetch_related('items')


@admin.register(SaleSOS)
class SaleSOSAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'customer', 'total_amount', 'amount_paid', 'debt_amount', 'total_amount_etb', 'date_created', 'is_completed')
    list_filter = ('is_completed', 'date_created')
    search_fields = ('customer__name', 'customer__phone', 'transaction_id')
    ordering = ('-date_created',)
    readonly_fields = ('transaction_id', 'date_created', 'total_amount_etb', 'amount_paid_etb', 'debt_amount_etb')
    inlines = [SaleItemSOSInline]
    fieldsets = (
        ('Transaction Details', {
            'fields': ('transaction_id', 'customer', 'user')
        }),
        ('SOS Amounts', {
            'fields': ('total_amount', 'amount_paid', 'debt_amount'),
            'description': 'All amounts in SOS'
        }),
        ('ETB Equivalents', {
            'fields': ('total_amount_etb', 'amount_paid_etb', 'debt_amount_etb'),
            'description': 'Converted to ETB using current exchange rate',
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': ('date_created', 'is_completed'),
            'classes': ('collapse',)
        }),
    )
    
    def total_amount_etb(self, obj):
        """Display total amount in ETB"""
        from .models import CurrencySettings
        settings = CurrencySettings.objects.first()
        if settings and settings.usd_to_sos_rate > 0:
            usd_amount = obj.total_amount / settings.usd_to_sos_rate
            etb_amount = usd_amount * settings.usd_to_etb_rate
            return f"{etb_amount:,.2f} ETB"
        return "N/A"
    total_amount_etb.short_description = 'Total (ETB)'
    
    def amount_paid_etb(self, obj):
        """Display amount paid in ETB"""
        from .models import CurrencySettings
        settings = CurrencySettings.objects.first()
        if settings and settings.usd_to_sos_rate > 0:
            usd_amount = obj.amount_paid / settings.usd_to_sos_rate
            etb_amount = usd_amount * settings.usd_to_etb_rate
            return f"{etb_amount:,.2f} ETB"
        return "N/A"
    amount_paid_etb.short_description = 'Paid (ETB)'
    
    def debt_amount_etb(self, obj):
        """Display debt amount in ETB"""
        from .models import CurrencySettings
        settings = CurrencySettings.objects.first()
        if settings and settings.usd_to_sos_rate > 0:
            usd_amount = obj.debt_amount / settings.usd_to_sos_rate
            etb_amount = usd_amount * settings.usd_to_etb_rate
            return f"{etb_amount:,.2f} ETB"
        return "N/A"
    debt_amount_etb.short_description = 'Debt (ETB)'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer', 'user').prefetch_related('items')


@admin.register(SaleETB)
class SaleETBAdmin(admin.ModelAdmin):
    list_display = ('transaction_id', 'customer', 'total_amount', 'amount_paid', 'debt_amount', 'date_created', 'is_completed')
    list_filter = ('is_completed', 'date_created')
    search_fields = ('customer__name', 'customer__phone', 'transaction_id')
    ordering = ('-date_created',)
    readonly_fields = ('transaction_id', 'date_created', 'exchange_rate_at_sale')
    inlines = [SaleItemETBInline]
    fieldsets = (
        ('Transaction Details', {
            'fields': ('transaction_id', 'customer', 'user')
        }),
        ('ETB Amounts', {
            'fields': ('total_amount', 'amount_paid', 'debt_amount'),
            'description': 'All amounts in ETB'
        }),
        ('Exchange Rate', {
            'fields': ('exchange_rate_at_sale',),
            'description': 'USD to ETB rate at time of sale (for profit calculation)',
            'classes': ('collapse',)
        }),
        ('System Info', {
            'fields': ('date_created', 'is_completed'),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer', 'user').prefetch_related('items')


@admin.register(SaleItemUSD)
class SaleItemUSDAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price', 'total_price')
    list_filter = ('sale__date_created',)
    search_fields = ('sale__transaction_id', 'product__name', 'product__brand')
    ordering = ('-sale__date_created',)
    readonly_fields = ('total_price',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('sale', 'product')


@admin.register(SaleItemSOS)
class SaleItemSOSAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price', 'total_price')
    list_filter = ('sale__date_created',)
    search_fields = ('sale__transaction_id', 'product__name', 'product__brand')
    ordering = ('-sale__date_created',)
    readonly_fields = ('total_price',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('sale', 'product')


@admin.register(SaleItemETB)
class SaleItemETBAdmin(admin.ModelAdmin):
    list_display = ('sale', 'product', 'quantity', 'unit_price', 'total_price')
    list_filter = ('sale__date_created',)
    search_fields = ('sale__transaction_id', 'product__name', 'product__brand')
    ordering = ('-sale__date_created',)
    readonly_fields = ('total_price',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('sale', 'product')


@admin.register(InventoryLog)
class InventoryLogAdmin(admin.ModelAdmin):
    list_display = ('product', 'action', 'quantity_change', 'old_quantity', 'new_quantity', 'date_created')
    list_filter = ('action', 'date_created', 'product__category')
    search_fields = ('product__name', 'product__brand', 'notes')
    ordering = ('-date_created',)
    readonly_fields = ('date_created',)
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('product', 'related_sale')


@admin.register(DebtPaymentUSD)
class DebtPaymentUSDAdmin(admin.ModelAdmin):
    list_display = ('customer', 'amount', 'date_created')
    list_filter = ('date_created',)
    search_fields = ('customer__name', 'customer__phone', 'notes')
    ordering = ('-date_created',)
    readonly_fields = ('date_created',)
    fieldsets = (
        ('Payment Information', {
            'fields': ('customer', 'amount', 'notes')
        }),
        ('System Info', {
            'fields': ('date_created',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer')


@admin.register(DebtPaymentSOS)
class DebtPaymentSOSAdmin(admin.ModelAdmin):
    list_display = ('customer', 'amount', 'date_created')
    list_filter = ('date_created',)
    search_fields = ('customer__name', 'customer__phone', 'notes')
    ordering = ('-date_created',)
    readonly_fields = ('date_created',)
    fieldsets = (
        ('Payment Information', {
            'fields': ('customer', 'amount', 'notes')
        }),
        ('System Info', {
            'fields': ('date_created',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer')


@admin.register(DebtPaymentETB)
class DebtPaymentETBAdmin(admin.ModelAdmin):
    list_display = ('customer', 'amount', 'date_created')
    list_filter = ('date_created',)
    search_fields = ('customer__name', 'customer__phone', 'notes')
    ordering = ('-date_created',)
    readonly_fields = ('date_created',)
    fieldsets = (
        ('Payment Information', {
            'fields': ('customer', 'amount', 'notes')
        }),
        ('System Info', {
            'fields': ('date_created',),
            'classes': ('collapse',)
        }),
    )
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer')


# Legacy DebtPayment admin for backward compatibility
@admin.register(DebtPayment)
class DebtPaymentAdmin(admin.ModelAdmin):
    list_display = ('customer', 'amount', 'original_currency', 'original_amount', 'amount_in_sos', 'date_created')
    list_filter = ('original_currency', 'date_created')
    search_fields = ('customer__name', 'customer__phone', 'notes')
    ordering = ('-date_created',)
    readonly_fields = ('date_created', 'amount_in_sos')
    fieldsets = (
        ('Payment Information', {
            'fields': ('customer', 'amount', 'original_currency', 'original_amount', 'notes')
        }),
        ('Converted Amounts', {
            'fields': ('amount_in_sos',),
            'description': 'Payment amount in SOS (converted from original currency)'
        }),
        ('System Info', {
            'fields': ('date_created',),
            'classes': ('collapse',)
        }),
    )
    
    def amount_in_sos(self, obj):
        """Display payment amount in SOS"""
        return f"{obj.get_amount_in_currency('SOS'):.0f} SOS"
    amount_in_sos.short_description = 'Amount (SOS)'
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer')


@admin.register(Receipt)
class ReceiptAdmin(admin.ModelAdmin):
    list_display = ('receipt_number', 'sale', 'date_created')
    list_filter = ('date_created',)
    search_fields = ('receipt_number', 'sale__transaction_id', 'sale__customer__name')
    ordering = ('-date_created',)
    readonly_fields = ('receipt_number', 'date_created')
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('sale', 'sale__customer')


@admin.register(AuditLog)
class AuditLogAdmin(admin.ModelAdmin):
    list_display = ('user', 'action', 'object_type', 'object_id', 'date_created', 'ip_address')
    list_filter = ('action', 'object_type', 'date_created')
    search_fields = ('user__username', 'user__first_name', 'user__last_name', 'details')
    ordering = ('-date_created',)
    readonly_fields = ('user', 'action', 'object_type', 'object_id', 'details', 'date_created', 'ip_address')
    
    def has_add_permission(self, request):
        return False
    
    def has_change_permission(self, request, obj=None):
        return False
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('user')


@admin.register(DebtCorrection)
class DebtCorrectionAdmin(admin.ModelAdmin):
    list_display = ('customer', 'currency', 'old_debt_amount', 'new_debt_amount', 'adjustment_amount', 'date_created')
    list_filter = ('currency', 'date_created')
    search_fields = ('customer__name', 'customer__phone', 'reason')
    ordering = ('-date_created',)
    readonly_fields = ('date_created', 'ip_address', 'adjustment_amount')
    fieldsets = (
        ('Correction Details', {
            'fields': ('customer', 'currency', 'old_debt_amount', 'new_debt_amount', 'adjustment_amount')
        }),
        ('Reason', {
            'fields': ('reason',)
        }),
        ('System Info', {
            'fields': ('date_created', 'ip_address'),
            'classes': ('collapse',)
        }),
    )
    
    def has_add_permission(self, request):
        return False  # Prevent adding corrections through admin
    
    def has_change_permission(self, request, obj=None):
        return False  # Make corrections read-only
    
    def has_delete_permission(self, request, obj=None):
        return request.user.is_superuser
    
    def get_queryset(self, request):
        qs = super().get_queryset(request)
        return qs.select_related('customer')
