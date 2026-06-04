from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0048_ensure_liveclass_table'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                ALTER TABLE accounts_courseresource
                ADD COLUMN IF NOT EXISTS "order" integer DEFAULT 0 NOT NULL;
            """,
            reverse_sql="""
                ALTER TABLE accounts_courseresource
                DROP COLUMN IF EXISTS "order";
            """,
        ),
    ]
