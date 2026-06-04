from django.db import migrations, models


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0048_course_accounts_co_status_e347e4_idx_and_more'),
    ]

    operations = [
        migrations.AddField(
            model_name='course',
            name='chapters',
            field=models.JSONField(blank=True, default=list, help_text='List of chapter names for this course'),
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='courseresource',
                    name='chapter',
                    field=models.CharField(blank=True, db_index=True, default='', max_length=255),
                ),
            ],
        ),
        migrations.SeparateDatabaseAndState(
            state_operations=[
                migrations.AddField(
                    model_name='lesson',
                    name='chapter',
                    field=models.CharField(blank=True, db_index=True, default='', max_length=255),
                ),
            ],
        ),
    ]
