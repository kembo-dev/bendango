from decimal import Decimal

from django.core.management import BaseCommand, call_command

from tracker.currency import convert_price
from tracker.product_matching import product_match_score


class Command(BaseCommand):
    help = "Run Bendango-specific local checks without calling external shops or LLMs."

    def handle(self, *args, **options):
        self.stdout.write("[1/4] Django system check")
        call_command("check")

        self.stdout.write("[2/4] Migration consistency")
        call_command("makemigrations", "--check", "--dry-run", verbosity=0)

        self.stdout.write("[3/4] Product matching smoke tests")
        checks = [
            ("iPhone 15 Pro 256GB", "Apple iPhone 15 Pro 256 Go", True),
            ("iPhone 15 Pro 256GB", "Coque iPhone 15 Pro 256GB", False),
            ("Galaxy S24 256GB", "Samsung Galaxy S24 128GB", False),
        ]
        for query, name, expected in checks:
            result = product_match_score(name, query)
            if result.is_match != expected:
                raise RuntimeError(f"Matching failure: {query!r} vs {name!r} -> {result}")

        self.stdout.write("[4/4] Currency normalization smoke test")
        if convert_price(Decimal("280000"), "CDF", "USD") != Decimal("100.00"):
            raise RuntimeError("Currency normalization check failed")

        self.stdout.write(self.style.SUCCESS("Bendango local health check: OK"))
