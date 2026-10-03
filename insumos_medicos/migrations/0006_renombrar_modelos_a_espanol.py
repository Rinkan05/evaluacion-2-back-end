from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0005_customuser_cart_cartitem_category_dispatch_order_and_more'),
    ]

    operations = [
        migrations.RenameModel(
            old_name='Category',
            new_name='Categoria',
        ),
        migrations.RenameModel(
            old_name='Supply',
            new_name='Insumo',
        ),
        migrations.RenameModel(
            old_name='Cart',
            new_name='Carro',
        ),
        migrations.RenameModel(
            old_name='CartItem',
            new_name='ItemCarro',
        ),
        migrations.RenameModel(
            old_name='Order',
            new_name='Solicitud',
        ),
        migrations.RenameModel(
            old_name='OrderItem',
            new_name='DetalleSolicitud',
        ),
        migrations.RenameModel(
            old_name='Dispatch',
            new_name='Despacho',
        ),
    ]
