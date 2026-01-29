from django.db import migrations

def migrate_staff_to_user(apps, schema_editor):
    SaleSOS = apps.get_model('core', 'SaleSOS')
    for sale in SaleSOS.objects.all():
        if sale.staff_member:
            sale.user = sale.staff_member
            sale.save()

def reverse_migration(apps, schema_editor):
    SaleSOS = apps.get_model('core', 'SaleSOS')
    for sale in SaleSOS.objects.all():
        if sale.user:
            sale.staff_member = sale.user
            sale.save()

class Migration(migrations.Migration):

    dependencies = [
        ('core', '0021_salesos_user_alter_salesos_staff_member'),
    ]

    operations = [
        migrations.RunPython(migrate_staff_to_user, reverse_migration),
    ]
