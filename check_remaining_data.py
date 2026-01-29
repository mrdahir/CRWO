#!/usr/bin/env python
"""
Script to check what data is still remaining
"""
import os
import sys
import django
from decimal import Decimal

# Setup Django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vape_shop.settings')
django.setup()

from core.models import Sale, SaleItem, DebtPayment, Product



product = Product.objects.get(name="kalyan 12k") # Or use .get(id=...)
print(f"Purchase Price in DB: ${product.purchase_price}")

