from django.core.management.base import BaseCommand

from apps.inventory.services import balance_drift, rebuild_balances


class Command(BaseCommand):
    help = "Report (and with --fix, rebuild) the stock balance cache from the ledger."

    def add_arguments(self, parser):
        parser.add_argument("--fix", action="store_true")

    def handle(self, *args, fix=False, **options):
        drift = balance_drift()
        for item_id, location_id, cached, ledger in drift:
            self.stdout.write(f"item={item_id} location={location_id}: cache {cached} != ledger {ledger}")
        if not drift:
            self.stdout.write(self.style.SUCCESS("Cache matches ledger."))
        elif fix:
            self.stdout.write(self.style.SUCCESS(f"Rebuilt {rebuild_balances()} balance rows."))
        else:
            self.stdout.write(self.style.WARNING(f"{len(drift)} mismatches. Re-run with --fix."))
