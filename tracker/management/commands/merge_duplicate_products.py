from __future__ import annotations

from django.core.management.base import BaseCommand
from django.db import transaction

from tracker.catalog_matching import has_variant_conflict
from tracker.models import PriceHistory, PriceListing, Product
from tracker.product_matching import match_product


def _compatible(left: Product, right: Product, threshold: float = 0.88) -> bool:
    if left.sku_or_ean and right.sku_or_ean and left.sku_or_ean != right.sku_or_ean:
        return False
    if has_variant_conflict(left.name, right.name):
        return False
    result = match_product(left.name, right.name, threshold=threshold)
    return result.is_match and result.score >= threshold


def _choose_canonical(products: list[Product]) -> Product:
    return sorted(products, key=lambda p: (0 if p.sku_or_ean else 1, -p.listings.count(), len(p.name), p.id))[0]


def _copy_product_metadata(target: Product, source: Product):
    fields = []
    for field in ("sku_or_ean", "brand", "model", "category", "image_url"):
        if not getattr(target, field) and getattr(source, field):
            setattr(target, field, getattr(source, field));fields.append(field)
    merged_attributes = dict(source.attributes or {})
    merged_attributes.update(target.attributes or {})
    if merged_attributes != (target.attributes or {}):
        target.attributes = merged_attributes;fields.append("attributes")
    if fields:
        target.save(update_fields=[*fields, "updated_at"])


def _merge_listing_into(target_product: Product, listing: PriceListing) -> tuple[int, int]:
    existing = PriceListing.objects.filter(product=target_product, retailer=listing.retailer, url=listing.url).exclude(pk=listing.pk).first()
    if not existing:
        PriceListing.objects.filter(pk=listing.pk).update(product=target_product)
        return 1, 0

    # Always keep the row already attached to the target product. This avoids
    # violating the unique constraint while histories are being consolidated.
    if listing.scraped_at > existing.scraped_at:
        PriceListing.objects.filter(pk=existing.pk).update(
            price=listing.price,
            currency=listing.currency,
            normalized_price=listing.normalized_price,
            normalized_currency=listing.normalized_currency,
            confidence_score=listing.confidence_score,
            match_score=listing.match_score,
            extraction_source=listing.extraction_source,
            in_stock=listing.in_stock,
            is_active=listing.is_active,
            scraped_at=listing.scraped_at,
        )
    PriceHistory.objects.filter(listing=listing).update(listing=existing)
    listing.delete()
    return 0, 1


def _build_safe_groups(products: list[Product], threshold: float) -> list[list[Product]]:
    groups = []
    used = set()
    for product in products:
        if product.id in used:
            continue
        group = [product]
        for candidate in products:
            if candidate.id == product.id or candidate.id in used:
                continue
            if all(_compatible(candidate, member, threshold=threshold) for member in group):
                group.append(candidate)
        if len(group) > 1:
            used.update(member.id for member in group)
            groups.append(group)
    return groups


class Command(BaseCommand):
    help = "Detect and safely merge duplicate canonical products. Defaults to dry-run."

    def add_arguments(self, parser):
        parser.add_argument("--apply", action="store_true", help="Apply merges. Without this flag, only report candidates.")
        parser.add_argument("--threshold", type=float, default=0.88, help="Minimum matching score for duplicate candidates.")

    def handle(self, *args, **options):
        apply_changes = options["apply"]
        threshold = options["threshold"]
        products = list(Product.objects.all().prefetch_related("listings"))
        groups = _build_safe_groups(products, threshold)
        if not groups:
            self.stdout.write(self.style.SUCCESS("Aucun doublon sûr détecté."));return

        self.stdout.write(f"{len(groups)} groupe(s) de doublons sûrs détecté(s).")
        for group in groups:
            canonical = _choose_canonical(group)
            others = [p for p in group if p.id != canonical.id]
            self.stdout.write("");self.stdout.write(self.style.WARNING(f"Canonique #{canonical.id}: {canonical.name}"))
            for duplicate in others:self.stdout.write(f"  - #{duplicate.id}: {duplicate.name}")
            if not apply_changes:continue

            moved = collapsed = 0
            with transaction.atomic():
                for duplicate in others:
                    _copy_product_metadata(canonical, duplicate)
                    for listing in list(duplicate.listings.all()):
                        moved_count, collapsed_count = _merge_listing_into(canonical, listing)
                        moved += moved_count;collapsed += collapsed_count
                    duplicate.delete()
            self.stdout.write(self.style.SUCCESS(f"  fusion appliquée: {moved} offre(s) déplacée(s), {collapsed} doublon(s) d'offre fusionné(s)."))

        if not apply_changes:
            self.stdout.write("");self.stdout.write(self.style.NOTICE("Dry-run uniquement. Relancez avec --apply pour appliquer les fusions."))
