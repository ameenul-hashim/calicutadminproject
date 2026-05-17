from django.core.management.base import BaseCommand
from django.db import connection

class Command(BaseCommand):
    help = 'Get estimated database sizes in KB for all tables'

    def handle(self, *args, **options):
        self.stdout.write(self.style.SUCCESS("📊 Database Size Report (PostgreSQL)\n"))
        
        if connection.vendor != 'postgresql':
            self.stdout.write(self.style.WARNING("This command is optimized for PostgreSQL. For SQLite, it will only list tables."))
            return

        with connection.cursor() as cursor:
            cursor.execute("""
                SELECT relname AS "table_name", 
                       pg_total_relation_size(relid) / 1024 AS "size_in_kb" 
                FROM pg_catalog.pg_statio_user_tables 
                ORDER BY pg_total_relation_size(relid) DESC;
            """)
            rows = cursor.fetchall()

        total_kb = 0
        self.stdout.write(f"{'TABLE NAME':<40} | {'SIZE (KB)':>10}")
        self.stdout.write("-" * 55)
        for row in rows:
            table_name, size_kb = row
            total_kb += size_kb
            self.stdout.write(f"{table_name:<40} | {size_kb:>10} KB")
        
        self.stdout.write("-" * 55)
        self.stdout.write(self.style.SUCCESS(f"Total Database Size Estimated: {total_kb} KB ({total_kb / 1024:.2f} MB)"))
