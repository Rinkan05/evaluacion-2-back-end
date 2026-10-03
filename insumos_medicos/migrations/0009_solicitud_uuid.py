import uuid

from django.db import migrations, models


def populate_order_uuids(apps, schema_editor):
    """Asigna UUID a las solicitudes existentes antes de imponer unicidad."""
    solicitud = apps.get_model('academic', 'Solicitud')
    for order in solicitud.objects.filter(uuid__isnull=True).iterator():
        order.uuid = uuid.uuid4()
        order.save(update_fields=['uuid'])


class Migration(migrations.Migration):

    dependencies = [
        ('academic', '0008_alter_customuser_rol'),
    ]

    operations = [
        migrations.AddField(
            model_name='solicitud',
            name='uuid',
            field=models.UUIDField(
                null=True,
                verbose_name='identificador único',
            ),
        ),
        migrations.RunPython(
            populate_order_uuids,
            reverse_code=migrations.RunPython.noop,
        ),
        migrations.AlterField(
            model_name='solicitud',
            name='uuid',
            field=models.UUIDField(
                default=uuid.uuid4,
                editable=False,
                unique=True,
                verbose_name='identificador único',
            ),
        ),
    ]
