# signals.py
from django.db.models.signals import post_save, post_delete
from django.dispatch import receiver
from django.db.models import Sum
from .models import Sale, SaleItem, Product, InventoryLog

@receiver(post_save, sender=SaleItem)
def update_sale_total_on_item_save(sender, instance, **kwargs):
    """Update sale total when sale items are added/changed"""
    sale = instance.sale
    total = sale.items.aggregate(total=Sum('total_price'))['total'] or 0
    if sale.total_amount != total:
        sale.total_amount = total
        sale.save()

@receiver(post_save, sender=Sale)
def update_customer_last_purchase(sender, instance, **kwargs):
    """Update customer's last purchase date"""
    if instance.customer and instance.date_created:
        instance.customer.last_purchase_date = instance.date_created
        instance.customer.save()