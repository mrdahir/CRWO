import os

# Read the file
file_path = os.path.join('core', 'templates', 'core', 'dashboard.html')
with open(file_path, 'r', encoding='utf-8') as f:
    content = f.read()

# Fix split template tags
fixes = [
    # Fix revenue card (lines 217-218)
    (
        '                <div class="stat-value">{% if today_revenue < 10 %}${{ today_revenue|floatformat:2 }}{% else %}${{\n                        today_revenue|floatformat:0 }}{% endif %}</div>',
        '                <div class="stat-value">{% if today_revenue < 10 %}${{ today_revenue|floatformat:2 }}{% else %}${{ today_revenue|floatformat:0 }}{% endif %}</div>'
    ),
    # Fix profit card (lines 253-254)
    (
        '                    <div class="stat-value">{% if today_profit < 10 %}${{ today_profit|floatformat:2 }}{% else %}${{\n                            today_profit|floatformat:0 }}{% endif %} / {{ today_profit_in_etb|floatformat:0 }} ETB</div>',
        '                    <div class="stat-value">{% if today_profit < 10 %}${{ today_profit|floatformat:2 }}{% else %}${{ today_profit|floatformat:0 }}{% endif %} / {{ today_profit_in_etb|floatformat:0 }} ETB</div>'
    )
]

for old, new in fixes:
    content = content.replace(old, new)

# Write back
with open(file_path, 'w', encoding='utf-8') as f:
    f.write(content)

print("Dashboard template fixed successfully!")
