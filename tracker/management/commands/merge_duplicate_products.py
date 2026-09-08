from __future__ import annotations

from collections import defaultdict

from django.core.management.base import BaseCommand
from django.db import transaction

from tracker.models import PriceHistory, PriceListing, Product
from tracker.product_matching import match_product, normalize_product_name


VARIANT_TOKENS = {"pro", "max", "plus", "ultra", "mini", "lite", "fe", "se"}


def _variant_tokens(name: str) -> set[str]:
    return set(normalize_product_name(name).split()) & VARIANT_TOKENS


def _compatible(left: Product, right: Product, threshold: float = 0.88) -> bool:
    if left.sku_or_ean and right.sku_or_ean and left.sku_or_ean != right.sku_or_ean:
        return False
    if _variant_tokens(left.name) != _variant_tokens(right.name):
        return False
    result = match_product(left.name, right.name, threshold=threshold)
    return result.is_match and result.score >= threshold


def _choose_canonical(products: list[Product]) -> Product:
    return sorted(
        products,
        key=lambda p: (
            0 if p.sku_or_ean else 1,
            -p.listings.count(),
            len(p.name),
            p.id,
        ),
    )[0]


def _merge_listing_into(target_product: Product, listing: PriceListing) -> tuple[int, int]:
    existing = PriceListing.objects.filter(
        product=target_product,
        retailer=listing.retailer,
        url=listing.url,
    ).exclude(pk=listing.pk).first()

    if not existing:
        listing.product = target_product
        listing.save(update_fields=["product"])
        return 1, 0

    # Keep the freshest listing record and move history to it.
    keeper, duplicate = (listing, existing) if listing.scraped_at >= existing.scraped_at else (existing, listing)
    if keeper.product_id != target_product.id:
        keeper.product = target_product
        keeper.save(update_fields=["product"])
    PriceHistory.objects.filter(listing=duplicate).update(listing=keeper)
    duplicate.delete()
    return 0, 1


class Command(BaseCommand):
    help = "Detect and safely merge duplicate canonical products. Defaults to dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply merges. Without this flag, only report candidates.")
        parser.add_argument("--threshold", type=float, default=0.88, help="Minimum matching score for duplicate candidates.")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        threshold = options["threshold"]
        products = list(Product.objects.all().prefetch_related("listings"))
        groups: list[list[Product]] = []
        used: set[int] = set()

        for product in products:
            if product.id in used:
                continue
            group = [product]
            for candidate in products:
                if candidate.id == product.id or candidate.id in used:
                    continue
                if _compatible(product, candidate, threshold=threshold):
                    group.append(candidate)
            if len(group) > 1:
                for member in group:
                    used.add(member.id)
                groups.append(group)

        if not groups:
            self.stdout.write(self.style.SUCCESS("Aucun doublon sûr détecté."))
            return

        self.stdout.write(f"{len(groups)} groupe(s) de doublons sûrs détecté(s).")
        for group in groups:
            canonical = _choose_canonical(group)
            others = [p for p in group if p.id != canonical.id]
            self.stdout.write("")
            self.stdout.write(self.style.WARNING(f"Canonique #{canonical.id}: {canonical.name}"))
            for duplicate in others:
                self.stdout.write(f"  - #{duplicate.id}: {duplicate.name}")

            if not apply_changes:
                continue

            moved = 0
            collapsed = 0
            with transaction.atomic():
                for duplicate in others:
                    for listing in list(duplicate.listings.all()):
                        moved_count, collapsed_count = _merge_listing_into(canonical, listing)
                        moved += moved_count
                        collapsed += collapsed_count
                    if not canonical.sku_or_ean and duplicate.sku_or_ean:
                        canonical.sku_or_ean = duplicate.sku_or_ean
                        canonical.save(update_fields=["sku_or_ean", "updated_at"])
                    duplicate.delete()

            self.stdout.write(self.style.SUCCESS(f"  fusion appliquée: {moved} offre(s) déplacée(s), {collapsed} doublon(s) d'offre fusionné(s)."))

        if not apply_changes:
            self.stdout.write("")
            self.stdout.write(self.style.NOTICE("Dry-run uniquement. Relancez avec --apply pour appliquer les fusions."))
