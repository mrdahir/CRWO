import os
import django
os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'zvshop.settings')
django.setup()

from core.models import CurrencySettings, SaleUSD, SaleSOS, SaleETB
from django.utils import timezone
from decimal import Decimal

today = timezone.now().date()
cs = CurrencySettings.objects.first()

print("=" * 50)
print("CURRENCY SETTINGS")
print("=" * 50)
print(f"USD to ETB Rate: {cs.usd_to_etb_rate}")
print(f"USD to SOS Rate: {cs.usd_to_sos_rate}")
print()

print("=" * 50)
print("TODAY'S PROFIT BREAKDOWN")
print("=" * 50)

# USD sales profit
usd_profit = Decimal('0')
today_usd = SaleUSD.objects.filter(date_created__date=today)
print(f"\nUSD Sales (count: {today_usd.count()}):")
for sale in today_usd:
    for item in sale.items.all():
        profit = item.get_profit_usd()
        usd_profit += profit
        print(f"  - {item.product.name}: ${profit}")

# SOS sales profit
sos_profit = Decimal('0')
today_sos = SaleSOS.objects.filter(date_created__date=today)
print(f"\nSOS Sales (count: {today_sos.count()}):")
for sale in today_sos:
    for item in sale.items.all():
        profit = item.get_profit_usd()
        sos_profit += profit
        print(f"  - {item.product.name}: ${profit}")

# ETB sales profit  
etb_profit = Decimal('0')
today_etb = SaleETB.objects.filter(date_created__date=today)
print(f"\nETB Sales (count: {today_etb.count()}):")
for sale in today_etb:
    for item in sale.items.all():
        profit = item.get_profit_usd()
        etb_profit += profit
        print(f"  - {item.product.name}: ${profit}")

print()
print("=" * 50)
print("TOTALS")
print("=" * 50)
total_profit = usd_profit + sos_profit + etb_profit
print(f"USD Sales Profit: ${usd_profit}")
print(f"SOS Sales Profit: ${sos_profit}")
print(f"ETB Sales Profit: ${etb_profit}")
print(f"TOTAL PROFIT (USD): ${total_profit}")
print()
print(f"Converted to ETB (x{cs.usd_to_etb_rate}): {total_profit * cs.usd_to_etb_rate} ETB")
print(f"Expected (96 x 185): {96 * 185} ETB")
