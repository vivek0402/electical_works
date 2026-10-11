from django.core.management.base import BaseCommand

from apps.inventory.services import balance_drift, rebuild_balances


class Command(BaseCommand):
    help = "Report (and with --fix, rebuild) the StockBalance cache from the stock ledger."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true", help="Rebuild the cache.")

    def handle(self, *args, fix=False, **options):
        drift = balance_drift()
        for item_id, location_id, bucket, cached, ledger in drift:
            self.stdout.write(
                f"item={item_id} location={location_id} {bucket}: cache {cached} != ledger {ledger}"
            )
        if not drift:
            self.stdout.write(self.style.SUCCESS("Cache matches ledger."))
            return
        if fix:
            rows = rebuild_balances()
            self.stdout.write(self.style.SUCCESS(f"Rebuilt {rows} balance rows."))
        else:
            self.stdout.write(self.style.WARNING(f"{len(drift)} mismatches. Re-run with --fix."))
