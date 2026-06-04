from django.db import migrations


class Migration(migrations.Migration):

    dependencies = [
        ('accounts', '0047_alter_courseresource_options'),
    ]

    operations = [
        migrations.RunSQL(
            sql="""
                CREATE TABLE IF NOT EXISTS accounts_liveclass (
                    id BIGSERIAL NOT NULL PRIMARY KEY,
                    course_id BIGINT NOT NULL REFERENCES accounts_course(id) DEFERRABLE INITIALLY DEFERRED,
                    title VARCHAR(255) NOT NULL,
                    meeting_link VARCHAR(200) NOT NULL,
                    date_time TIMESTAMP WITH TIME ZONE NOT NULL
                );
            """,
            reverse_sql="""
                DROP TABLE IF EXISTS accounts_liveclass;
            """,
        ),
    ]
