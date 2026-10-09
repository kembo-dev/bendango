"""Publishing for individuals, separate from the approved Pro administration."""
from django.contrib import messages
from django.contrib.auth.decorators import login_required
from django.db import transaction
from django.shortcuts import get_object_or_404, redirect, render
from django.views.decorators.http import require_POST

from .forms import MobilePublishForm
from .markets import DEFAULT_MARKET_CODE, get_market
from .models import BusinessProfile, Offer


def _allowed(profile):
    return profile is None or (profile.is_active and (profile.is_individual or profile.is_verified))


def _editor(request, offer=None):
    profile = BusinessProfile.objects.filter(user=request.user).first()
    if not _allowed(profile):
        messages.error(request, 'Votre profil ne permet pas de publier actuellement. Contactez l’équipe Bendango.')
        return redirect('my_announcements')
    initial = {'currency': get_market(profile.market_code if profile else DEFAULT_MARKET_CODE).currency,
               'whatsapp': profile.whatsapp or profile.phone if profile else '',
               'city': profile.city if profile else '',
               'market_code': profile.market_code if profile else DEFAULT_MARKET_CODE}
    if offer:
        initial.update({name: getattr(offer, name) for name in ('title', 'offer_type', 'description', 'price', 'currency', 'whatsapp', 'city', 'market_code')})
    form = MobilePublishForm(request.POST if request.method == 'POST' else None, request.FILES if request.method == 'POST' else None, initial=initial, editing=bool(offer), current_currency=offer.currency if offer else None)
    valid = request.method == 'POST' and form.is_valid()
    if valid and offer and offer.media.count() + len(form.cleaned_data['photos']) > 8:
        form.add_error('photos', 'Une annonce peut contenir au maximum 8 photos.')
        valid = False
    if valid:
        # Imported here to preserve the legacy Pro product/catalogue bridge.
        from .views import _attach_offer_media, _sync_offer_product_bridge
        with transaction.atomic():
            profile, _ = BusinessProfile.objects.get_or_create(user=request.user, defaults={
                'business_name': request.user.username[:180], 'business_type': 'Particulier',
                'is_individual': True, 'is_verified': False,
                'verification_level': BusinessProfile.VERIFY_UNVERIFIED,
                'market_code': form.cleaned_data['market_code'], 'city': form.cleaned_data['city'],
            })
            # Recheck after get_or_create: another request may have created/changed it.
            if not _allowed(profile):
                messages.error(request, 'Votre profil ne permet pas de publier actuellement.')
                return redirect('my_announcements')
            values = {name: form.cleaned_data[name] for name in ('title', 'offer_type', 'description', 'price', 'currency', 'whatsapp', 'city', 'market_code')}
            values['contact_method'] = 'whatsapp'
            if offer:
                for name, value in values.items():
                    setattr(offer, name, value)
                offer.save()
            else:
                offer = Offer.objects.create(business=profile, **values)
            _attach_offer_media(offer, form.cleaned_data['photos'])
            # Individuals never create a verified Retailer/PriceListing.
            if profile.is_verified and not profile.is_individual:
                _sync_offer_product_bridge(offer)
        messages.success(request, 'Votre annonce a été enregistrée.' if form.initial.get('title') else 'Votre annonce est publiée !')
        return redirect('my_announcements')
    return render(request, 'tracker/quick_publish.html', {
        'profile': profile, 'form': form, 'offer': offer, 'mobile_publish': True,
        'page_title': 'Modifier mon annonce' if offer else 'Publier une annonce',
        'submit_label': 'Enregistrer' if offer else 'Publier mon annonce', 'return_url': 'my_announcements',
    })


@login_required
def publish_offer(request):
    return _editor(request)


@login_required
def edit_announcement(request, offer_id):
    offer = get_object_or_404(Offer.objects.select_related('business'), pk=offer_id, business__user=request.user)
    return _editor(request, offer)


@login_required
def my_announcements(request):
    offers = Offer.objects.filter(business__user=request.user).select_related('business').prefetch_related('media').order_by('-created_at')
    return render(request, 'tracker/my_announcements.html', {'offers': offers})


@login_required
@require_POST
def toggle_announcement(request, offer_id):
    offer = get_object_or_404(Offer.objects.select_related('business'), pk=offer_id, business__user=request.user)
    if _allowed(offer.business):
        offer.is_active = not offer.is_active
        offer.save(update_fields=['is_active', 'updated_at'])
        if offer.price_listing_id:
            from .models import PriceListing
            PriceListing.objects.filter(pk=offer.price_listing_id).update(is_active=offer.is_active and offer.is_public)
    else:
        messages.error(request, 'Votre profil ne permet pas de réactiver une annonce actuellement.')
    return redirect('my_announcements')
