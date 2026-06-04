from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0051_merge_20260604_1538'),
    ]

    state_operations = [
        migrations.AddField(
            model_name='courseresource',
            name='order',
            field=models.PositiveIntegerField(default=1),
        ),
    ]

    operations = [
        migrations.SeparateDatabaseAndState(state_operations=state_operations),
    ]
