import os
import django
from decimal import Decimal

os.environ.setdefault('DJANGO_SETTINGS_MODULE', 'vape_shop.settings')
django.setup()

from core.forms import DebtPaymentForm
from core.models import Customer

def verify_strict_compliance():
    print("--- Verifying PNO Strict Compliance ---")
    
    # Create valid data
    customer = Customer.objects.first()
    if not customer:
        print("SKIP: No customers found to test with.")
        return

    valid_data = {
        'amount': '10.00',
        'pno': 'REC-001',
        'notes': 'Test payment',
        'currency': 'USD'
    }
    
    # Test 1: Valid Submission
    form = DebtPaymentForm(data=valid_data)
    # We need to inject customer since __init__ expects it or view handles it
    # The form expects 'customer' in kwargs for validation logic in clean()
    form = DebtPaymentForm(data=valid_data, customer=customer)
    
    if form.is_valid():
        print("✅ Test 1 Passed: Form accepts valid PNO.")
    else:
        print(f"❌ Test 1 Failed: {form.errors}")

    # Test 2: Missing PNO (Empty string)
    invalid_data = valid_data.copy()
    invalid_data['pno'] = ''
    form_missing = DebtPaymentForm(data=invalid_data, customer=customer)
    
    if not form_missing.is_valid():
        if 'pno' in form_missing.errors:
            print("✅ Test 2 Passed: Form rejects empty PNO.")
            print(f"   Error: {form_missing.errors['pno']}")
        else:
            print(f"❌ Test 2 Failed: Form invalid but not for PNO? {form_missing.errors}")
    else:
        print("❌ Test 2 Failed: Form accepted empty PNO!")

    # Test 3: Null PNO (None) - Form usually treats missing key as None/Empty
    invalid_data_none = valid_data.copy()
    del invalid_data_none['pno']
    form_none = DebtPaymentForm(data=invalid_data_none, customer=customer)
    
    if not form_none.is_valid():
        if 'pno' in form_none.errors:
            print("✅ Test 3 Passed: Form rejects missing PNO key.")
        else:
            print(f"❌ Test 3 Failed: {form_none.errors}")
    else:
        print("❌ Test 3 Failed: Form accepted missing PNO key!")

if __name__ == '__main__':
    verify_strict_compliance()
