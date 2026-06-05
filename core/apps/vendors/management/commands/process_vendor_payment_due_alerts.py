from django.core.management.base import BaseCommand

from apps.vendors.tasks import process_vendor_payment_due_alerts


class Command(BaseCommand):
    help = "Create vendor payment due notifications for all shop tenants (daily cron job)."

    def add_arguments(self, parser):
        parser.add_argument(
            "--date",
            type=str,
            help="Override run date as YYYY-MM-DD (defaults to today in Asia/Kolkata).",
        )

    def handle(self, *args, **options):
        process_vendor_payment_due_alerts(for_date_iso=options.get("date"))
        self.stdout.write(self.style.SUCCESS("Vendor payment due alerts processed."))
