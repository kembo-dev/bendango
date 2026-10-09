"""Business-owned facts for the client administration dashboard."""
from django.db.models import Count, Q
from django.utils import timezone

from tracker.models import OfferBoostRequest, PriceListing, SearchRun


def dashboard_context(profile, user):
    offers = profile.offers.all()
    offer_stats = offers.aggregate(total=Count('pk'), public=Count('pk', filter=Q(is_active=True, is_public=True)),
                                   unpublished=Count('pk', filter=Q(is_active=False) | Q(is_public=False)))
    listings = PriceListing.objects.filter(retailer_id=profile.retailer_id) if profile.retailer_id else PriceListing.objects.none()
    product_stats = listings.aggregate(total=Count('pk'), unavailable=Count('pk', filter=Q(is_active=True, in_stock=False)))
    boosts = OfferBoostRequest.objects.filter(offer__business=profile).select_related('offer')
    now = timezone.now()
    active_boosts = boosts.filter(status=OfferBoostRequest.STATUS_APPROVED, starts_at__lte=now, ends_at__gt=now).values('offer_id').distinct().count()
    checklist = [
        {'label': 'Nom de l’entreprise', 'done': bool(profile.business_name.strip())},
        {'label': 'Présentation', 'done': bool(profile.description.strip())},
        {'label': 'Logo', 'done': bool(profile.logo_url.strip())},
        {'label': 'Ville', 'done': bool(profile.city.strip())},
        {'label': 'Adresse', 'done': bool(profile.address.strip())},
        {'label': 'Contact', 'done': bool(profile.phone.strip() or profile.whatsapp.strip() or profile.public_email.strip())},
    ]
    searches = SearchRun.objects.filter(user=user)
    return {
        'offer_count': offer_stats['total'],
        'published_offer_count': offer_stats['public'] if profile.is_active and profile.is_public else 0,
        'unpublished_offer_count': offer_stats['unpublished'],
        'product_count': product_stats['total'],
        'unavailable_product_count': product_stats['unavailable'],
        'active_boost_count': active_boosts,
        'pending_boost_count': boosts.filter(status=OfferBoostRequest.STATUS_PENDING).count(),
        'recent_offers': offers.prefetch_related('media').order_by('-updated_at')[:6],
        'recent_boosts': boosts.order_by('-created_at')[:4],
        'profile_checklist': checklist,
        'profile_completion': round(sum(item['done'] for item in checklist) / len(checklist) * 100),
        'recent_searches': searches.order_by('-created_at')[:3],
        'search_count': searches.count(),
    }
