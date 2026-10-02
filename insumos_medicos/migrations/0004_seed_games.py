from decimal import Decimal

from django.db import migrations


def create_example_games(apps, schema_editor):
    Game = apps.get_model('academic', 'Game')
    Game.objects.get_or_create(
        title='Neon Drift',
        defaults={
            'platform': 'PC',
            'genre': 'Carreras',
            'price': Decimal('29.99'),
            'stock': 12,
        },
    )
    Game.objects.get_or_create(
        title='Kingdoms of Ash',
        defaults={
            'platform': 'PlayStation 5',
            'genre': 'Aventura',
            'price': Decimal('49.99'),
            'stock': 8,
        },
    )


def remove_example_games(apps, schema_editor):
    Game = apps.get_model('academic', 'Game')
    Game.objects.filter(title__in=['Neon Drift', 'Kingdoms of Ash']).delete()


class Migration(migrations.Migration):
    dependencies = [
        ('academic', '0003_game'),
    ]

    operations = [
        migrations.RunPython(create_example_games, remove_example_games),
    ]
