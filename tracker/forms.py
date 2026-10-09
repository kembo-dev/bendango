from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .markets import DEFAULT_MARKET_CODE, GLOBAL_MARKET_CODE, market_choices
from .image_processing import prepare_photo
from .models import BusinessCategory, BusinessProfile, Currency, Offer, OfferBoostRequest


class CurrencyChoiceField(forms.ChoiceField):
    def to_python(self, value):
        return super().to_python(value).strip().upper()


class CurrencyConfiguredForm(forms.Form):
    currency = CurrencyChoiceField(label='Devise', widget=forms.Select(attrs={'class': 'field-input'}),
        error_messages={'invalid_choice': 'Choisissez une devise disponible dans la liste.'})

    def __init__(self, *args, **kwargs):
        # Uniquement une valeur provenant de l'objet édité côté serveur, jamais du POST.
        current_currency = kwargs.pop('current_currency', None)
        super().__init__(*args, **kwargs)
        choices = [(currency.code, str(currency)) for currency in Currency.objects.filter(is_active=True)]
        available_codes = {code for code, label in choices}
        if current_currency and current_currency not in available_codes:
            choices.append((current_currency, f'{current_currency} — Devise de cette annonce (conservée)'))
        self.fields['currency'].choices = choices or [('', 'Aucune devise disponible')]
        self.fields['currency'].help_text = ('Choisissez la devise de votre prix.' if choices else
            'La publication est temporairement indisponible : aucune devise n’est activée.')
        if self.initial.get('currency') not in {code for code, label in choices}:
            self.initial['currency'] = choices[0][0] if choices else ''



class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
            if self.required:
                raise forms.ValidationError("Ajoutez au moins une photo de votre annonce.")
            return []
        files = data if isinstance(data, (list, tuple)) else [data]
        if len(files) > 8:
            raise forms.ValidationError("Vous pouvez ajouter au maximum 8 images par envoi.")
        cleaned = []
        allowed_extensions = {'.jpg', '.jpeg', '.png', '.webp', '.gif'}
        for uploaded in files:
            if uploaded.size > 8 * 1024 * 1024:
                raise forms.ValidationError("Chaque image doit faire au maximum 8 Mo.")
            content_type = (getattr(uploaded, 'content_type', '') or '').lower()
            name = (uploaded.name or '').lower()
            if not content_type.startswith('image/') and not any(name.endswith(ext) for ext in allowed_extensions):
                raise forms.ValidationError("Seuls les fichiers image sont acceptés.")
            cleaned.append(prepare_photo(uploaded))
        return cleaned

class SearchOrScrapeForm(forms.Form):
    site = forms.CharField(
        label="Site e-commerce ou URL",
        required=False,
        initial="",
        help_text="Laisser vide pour rechercher uniquement par nom du produit sur Internet.",
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "placeholder": "Ex: amazon.fr ou https://www.amazon.fr (optionnel)",
            }
        ),
    )
    query = forms.CharField(
        label="Produit à rechercher",
        widget=forms.TextInput(
            attrs={
                "class": "field-input",
                "placeholder": "Ex: iPhone 15 128Go",
            }
        ),
    )
    market = forms.ChoiceField(
        label="Marché",
        choices=market_choices(),
        initial=DEFAULT_MARKET_CODE,
        widget=forms.Select(attrs={"class": "field-input"}),
        help_text="Choisissez le pays où Bendango doit privilégier les marchands et les offres.",
    )
    city = forms.CharField(
        label="Ville",
        required=False,
        max_length=120,
        widget=forms.TextInput(attrs={
            "class": "field-input",
            "placeholder": "Ex: Kinshasa",
        }),
        help_text="Optionnel : privilégie les offres locales de cette ville.",
    )
    offer_type = forms.ChoiceField(
        label="Type d'offre",
        required=False,
        choices=[("", "Tous les types")] + list(Offer.OFFER_TYPES),
        widget=forms.Select(attrs={"class": "field-input"}),
    )
    source = forms.ChoiceField(
        label="Source",
        required=False,
        choices=[
            ("", "Toutes les sources"),
            ("bendango", "Bendango"),
            ("web", "Web marchand"),
            ("social", "Réseaux sociaux"),
        ],
        widget=forms.Select(attrs={"class": "field-input"}),
    )
    business_category = forms.ChoiceField(
        label="Type de business",
        required=False,
        choices=[("", "Tous les business")],
        widget=forms.Select(attrs={"class": "field-input"}),
        help_text="Filtre les offres publiées par les business Bendango.",
    )
    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        try:
            categories = BusinessCategory.objects.filter(is_active=True).order_by("sort_order", "name")
            self.fields["business_category"].choices = [
                ("", "Tous les business"),
                *[(category.slug, category.name) for category in categories],
            ]
        except Exception:
            # Keep management commands usable before migrations/database availability.
            self.fields["business_category"].choices = [("", "Tous les business")]



class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'field-input', 'placeholder': 'vous@exemple.com'}),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'field-input', 'placeholder': "Nom d'utilisateur"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('password1', 'password2'):
            self.fields[name].widget.attrs.update({'class': 'field-input'})

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Un compte utilise déjà cette adresse e-mail.')
        return email


class BusinessAccountRequestForm(forms.Form):
    business_name = forms.CharField(
        label="Nom de l'entreprise",
        max_length=180,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Ex: Kembo Corporation'}),
    )
    business_type = forms.CharField(
        label="Activité",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Ex: E-commerce, distribution, mode...'}),
    )
    website = forms.URLField(
        label='Site web',
        required=False,
        widget=forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://...'}),
    )
    phone = forms.CharField(
        label='Téléphone',
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': '+243...'}),
    )
    description = forms.CharField(
        label='Présentez votre business et votre besoin',
        required=False,
        widget=forms.Textarea(attrs={'class': 'field-input', 'rows': 5}),
    )



class BusinessProfileForm(forms.ModelForm):
    class Meta:
        model = BusinessProfile
        fields = (
            'business_name',
            'category',
            'business_type',
            'website',
            'phone',
            'whatsapp',
            'public_email',
            'facebook_url',
            'instagram_url',
            'tiktok_url',
            'country',
            'city',
            'market_code',
            'address',
            'logo_url',
            'cover_image_url',
            'description',
        )
        labels = {
            'business_name': "Nom de l'entreprise",
            'category': 'Catégorie',
            'business_type': 'Activité',
            'website': 'Site web',
            'phone': 'Téléphone',
            'whatsapp': 'WhatsApp',
            'public_email': 'E-mail public',
            'facebook_url': 'Facebook',
            'instagram_url': 'Instagram',
            'tiktok_url': 'TikTok',
            'country': 'Pays',
            'city': 'Ville',
            'market_code': 'Marché principal',
            'address': 'Adresse',
            'logo_url': 'URL du logo',
            'cover_image_url': 'Image de couverture',
            'description': 'Description',
        }
        widgets = {
            'business_name': forms.TextInput(attrs={'class': 'field-input'}),
            'category': forms.Select(attrs={'class': 'field-input'}),
            'business_type': forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Ex: Pharmacie, hôtel, mode, services...'}),
            'website': forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://... (optionnel)'}),
            'phone': forms.TextInput(attrs={'class': 'field-input'}),
            'whatsapp': forms.TextInput(attrs={'class': 'field-input', 'placeholder': '+243...'}),
            'public_email': forms.EmailInput(attrs={'class': 'field-input'}),
            'facebook_url': forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://facebook.com/...'}),
            'instagram_url': forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://instagram.com/...'}),
            'tiktok_url': forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://tiktok.com/@...'}),
            'country': forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Ex: RDC'}),
            'city': forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Ex: Kinshasa'}),
            'market_code': forms.Select(attrs={'class': 'field-input'}, choices=market_choices()),
            'address': forms.TextInput(attrs={'class': 'field-input'}),
            'logo_url': forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://...'}),
            'cover_image_url': forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://...'}),
            'description': forms.Textarea(attrs={'class': 'field-input', 'rows': 5}),
        }



class ProCatalogProductForm(CurrencyConfiguredForm):
    name = forms.CharField(
        label='Nom du produit',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'field-input'}),
    )
    brand = forms.CharField(
        label='Marque',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input'}),
    )
    model = forms.CharField(
        label='Modèle',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input'}),
    )
    sku_or_ean = forms.CharField(
        label='SKU / EAN',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input'}),
    )
    category = forms.CharField(
        label='Catégorie',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input'}),
    )
    image_url = forms.URLField(
        label='Image du produit',
        required=False,
        widget=forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://...'}),
    )
    price = forms.DecimalField(
        label='Prix',
        min_value=0.01,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'field-input', 'step': '0.01'}),
    )
    in_stock = forms.BooleanField(
        label='En stock',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    sale_url = forms.URLField(
        label='Lien de vente',
        widget=forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://...'}),
    )

    def clean_currency(self):
        return self.cleaned_data['currency'].strip().upper()



class QuickOfferForm(CurrencyConfiguredForm):
    offer_type = forms.ChoiceField(
        label="Type d'offre",
        choices=Offer.OFFER_TYPES,
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    title = forms.CharField(
        label='Nom / titre',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Ex: Samsung A56, chambre standard, coiffure femme...'}),
    )
    price = forms.DecimalField(
        label='Prix',
        required=False,
        min_value=0.01,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'field-input', 'step': '0.01', 'placeholder': 'Laisser vide si sur demande'}),
    )
    price_unit = forms.CharField(
        label='Unité de prix',
        max_length=60,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Ex: nuit, heure, unité, mois...'}),
    )
    photos = MultipleImageFileField(
        label='Photos depuis téléphone ou ordinateur',
        required=False,
        widget=MultipleFileInput(attrs={
            'class': 'field-input',
            'accept': 'image/*',
        }),
        help_text='Jusqu’à 8 images par envoi, 8 Mo maximum par image.',
    )
    primary_image_url = forms.URLField(
        label='URL image existante',
        required=False,
        widget=forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'https://... (optionnel)'}),
        help_text="Facultatif : utile si l'image est déjà hébergée en ligne.",
    )
    availability = forms.ChoiceField(
        label='Disponibilité',
        choices=Offer.AVAILABILITY_CHOICES,
        initial='available',
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    whatsapp = forms.CharField(
        label='WhatsApp',
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': '+243...'}),
    )
    external_url = forms.URLField(
        label='Lien externe / site',
        required=False,
        widget=forms.URLInput(attrs={'class': 'field-input', 'placeholder': 'Optionnel'}),
    )
    description = forms.CharField(
        label='Description',
        required=False,
        widget=forms.Textarea(attrs={'class': 'field-input', 'rows': 4}),
    )

    def clean_currency(self):
        return self.cleaned_data['currency'].strip().upper()


class OfferBoostRequestForm(forms.Form):
    duration_days = forms.ChoiceField(
        label='Durée souhaitée',
        choices=OfferBoostRequest.DURATION_CHOICES,
        initial=7,
        widget=forms.Select(attrs={'class': 'field-input'}),
    )
    note = forms.CharField(
        label='Message pour l’administrateur',
        required=False,
        widget=forms.Textarea(attrs={
            'class': 'field-input',
            'rows': 4,
            'placeholder': 'Pourquoi souhaitez-vous mettre ce produit en avant ?',
        }),
    )


class OfferEditForm(QuickOfferForm):
    category = forms.CharField(
        label='Catégorie',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input'}),
    )
    city = forms.CharField(
        label='Ville',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': 'field-input'}),
    )
    contact_method = forms.ChoiceField(
        label='Contact principal',
        choices=Offer.CONTACT_CHOICES,
        widget=forms.Select(attrs={'class': 'field-input'}),
    )


class MobilePublishForm(QuickOfferForm):
    city = forms.CharField(label='Ville', max_length=120, required=True,
        widget=forms.TextInput(attrs={'class': 'field-input', 'placeholder': 'Ex : Kinshasa', 'autocomplete': 'address-level2'}))
    market_code = forms.ChoiceField(label='Pays', choices=[choice for choice in market_choices() if choice[0] != GLOBAL_MARKET_CODE], initial=DEFAULT_MARKET_CODE,
        widget=forms.Select(attrs={'class': 'field-input'}))

    def __init__(self, *args, **kwargs):
        editing = kwargs.pop('editing', False)
        super().__init__(*args, **kwargs)
        for name in ('primary_image_url', 'external_url', 'price_unit', 'availability'):
            self.fields.pop(name)
        self.fields['photos'].required = not editing
        self.fields['photos'].widget.attrs['accept'] = 'image/jpeg,image/png,image/webp,image/gif'
        self.fields['photos'].help_text = '8 photos maximum · 8 Mo par photo · JPEG, PNG, WebP ou GIF.'
        self.fields['whatsapp'].required = True
        self.fields['whatsapp'].widget.attrs.update({'type': 'tel', 'inputmode': 'tel', 'autocomplete': 'tel'})
        self.fields['price'].widget.attrs['inputmode'] = 'decimal'

    def clean_whatsapp(self):
        import re
        value = self.cleaned_data['whatsapp'].strip()
        if not re.fullmatch(r'\+?[0-9 ()-]{7,40}', value) or not 7 <= len(re.sub(r'\D', '', value)) <= 15:
            raise forms.ValidationError('Indiquez un numéro WhatsApp valide avec son indicatif pays.')
        return value
