"""Navigation publique du marché, sans lancer une recherche externe."""
from urllib.parse import urlencode

from django.db.models import Q

from .markets import GLOBAL_MARKET_CODE, market_choices
from .models import Offer


SELLERS = [('', 'Tous les vendeurs'), ('pro_verified', 'Pro validés'),
           ('individual', 'Particuliers'), ('pro_unverified', 'Pro non validés')]


def browse_filters(request):
    countries = {code for code, label in market_choices() if code != GLOBAL_MARKET_CODE}
    return {
        'browse_type': request.GET.get('browse_type', '') if request.GET.get('browse_type') in dict(Offer.OFFER_TYPES) else '',
        'seller': request.GET.get('seller', '') if request.GET.get('seller') in dict(SELLERS) else '',
        'browse_market': request.GET.get('browse_market', '') if request.GET.get('browse_market') in countries else '',
        'browse_city': request.GET.get('browse_city', '').strip()[:120],
    }


def filter_offers(queryset, filters):
    if filters['browse_type']:
        queryset = queryset.filter(offer_type=filters['browse_type'])
    if filters['browse_market']:
        queryset = queryset.filter(market_code=filters['browse_market'])
    if filters['browse_city']:
        queryset = queryset.filter(Q(city__icontains=filters['browse_city']) | Q(city='', business__city__icontains=filters['browse_city']))
    if filters['seller'] == 'individual':
        queryset = queryset.filter(business__is_individual=True)
    elif filters['seller'] in ('pro_verified', 'pro_unverified'):
        queryset = queryset.filter(business__is_individual=False, business__is_verified=filters['seller'] == 'pro_verified')
    return queryset


def marketplace_context(request, page):
    if page is None:
        return {'marketplace': False}
    filters = browse_filters(request)
    def link(**changes):
        return '/?' + urlencode({key: value for key, value in {**filters, **changes}.items() if value})
    labels = {'product': 'Produits', 'service': 'Services', 'accommodation': 'Logements', 'restaurant': 'À table', 'health': 'Santé', 'transport': 'Transport', 'real_estate': 'Immobilier', 'other': 'Autres'}
    categories = [('', 'Tout le marché'), *((code, labels.get(code, label)) for code, label in Offer.OFFER_TYPES)]
    return {
        'marketplace': True,
        'browse': filters,
        'market_categories': [{'code': code, 'label': label, 'active': code == filters['browse_type'], 'url': link(browse_type=code)} for code, label in categories],
        'market_sellers': [{'label': label, 'active': code == filters['seller'], 'url': link(seller=code)} for code, label in SELLERS],
        'market_countries': [(code, label) for code, label in market_choices() if code != GLOBAL_MARKET_CODE],
        'market_offers': [item for item in page if item['kind'] == 'offer'],
        'market_searches': [item for item in page if item['kind'] == 'search'],
        'market_offer_count': sum(item['kind'] == 'offer' for item in page.paginator.object_list),
        'marketplace_query': urlencode({key: value for key, value in filters.items() if value}),
        'browse_filtered': any(filters.values()),
    }
