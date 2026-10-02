from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .markets import DEFAULT_MARKET_CODE, market_choices
from .models import BusinessProfile, Offer
from .services import get_llm_config



class MultipleFileInput(forms.ClearableFileInput):
    allow_multiple_selected = True


class MultipleImageFileField(forms.FileField):
    widget = MultipleFileInput

    def clean(self, data, initial=None):
        if not data:
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
            cleaned.append(uploaded)
        return cleaned

class SearchOrScrapeForm(forms.Form):
    site = forms.CharField(
        label="Site e-commerce ou URL",
        required=False,
        initial="",
        help_text="Laisser vide pour rechercher uniquement par nom du produit sur Internet.",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ex: amazon.fr ou https://www.amazon.fr (optionnel)",
            }
        ),
    )
    query = forms.CharField(
        label="Produit à rechercher",
        widget=forms.TextInput(
            attrs={
                "class": "form-control",
                "placeholder": "Ex: iPhone 15 128Go",
            }
        ),
    )
    market = forms.ChoiceField(
        label="Marché",
        choices=market_choices(),
        initial=DEFAULT_MARKET_CODE,
        widget=forms.Select(attrs={"class": "form-select"}),
        help_text="Choisissez le pays où Bendango doit privilégier les marchands et les offres.",
    )
    model_name = forms.CharField(
        label="Modèle LLM",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        default_model = get_llm_config()["default_model"]
        self.fields["model_name"].initial = default_model
        self.fields["model_name"].help_text = f"Modèle actif : {default_model}"



class SignUpForm(UserCreationForm):
    email = forms.EmailField(
        required=True,
        widget=forms.EmailInput(attrs={'class': 'form-control', 'placeholder': 'vous@exemple.com'}),
    )

    class Meta:
        model = User
        fields = ('username', 'email', 'password1', 'password2')
        widgets = {
            'username': forms.TextInput(attrs={'class': 'form-control', 'placeholder': "Nom d'utilisateur"}),
        }

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        for name in ('password1', 'password2'):
            self.fields[name].widget.attrs.update({'class': 'form-control'})

    def clean_email(self):
        email = self.cleaned_data['email'].strip().lower()
        if User.objects.filter(email__iexact=email).exists():
            raise forms.ValidationError('Un compte utilise déjà cette adresse e-mail.')
        return email


class BusinessAccountRequestForm(forms.Form):
    business_name = forms.CharField(
        label="Nom de l'entreprise",
        max_length=180,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Kembo Corporation'}),
    )
    business_type = forms.CharField(
        label="Activité",
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: E-commerce, distribution, mode...'}),
    )
    website = forms.URLField(
        label='Site web',
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
    )
    phone = forms.CharField(
        label='Téléphone',
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+243...'}),
    )
    description = forms.CharField(
        label='Présentez votre business et votre besoin',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
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
            'business_name': forms.TextInput(attrs={'class': 'form-control'}),
            'category': forms.Select(attrs={'class': 'form-select'}),
            'business_type': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Pharmacie, hôtel, mode, services...'}),
            'website': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... (optionnel)'}),
            'phone': forms.TextInput(attrs={'class': 'form-control'}),
            'whatsapp': forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+243...'}),
            'public_email': forms.EmailInput(attrs={'class': 'form-control'}),
            'facebook_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://facebook.com/...'}),
            'instagram_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://instagram.com/...'}),
            'tiktok_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://tiktok.com/@...'}),
            'country': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: RDC'}),
            'city': forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Kinshasa'}),
            'market_code': forms.Select(attrs={'class': 'form-select'}, choices=market_choices()),
            'address': forms.TextInput(attrs={'class': 'form-control'}),
            'logo_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'cover_image_url': forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
            'description': forms.Textarea(attrs={'class': 'form-control', 'rows': 5}),
        }



class ProCatalogProductForm(forms.Form):
    name = forms.CharField(
        label='Nom du produit',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    brand = forms.CharField(
        label='Marque',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    model = forms.CharField(
        label='Modèle',
        max_length=150,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    sku_or_ean = forms.CharField(
        label='SKU / EAN',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    category = forms.CharField(
        label='Catégorie',
        max_length=100,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    image_url = forms.URLField(
        label='Image du produit',
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
    )
    price = forms.DecimalField(
        label='Prix',
        min_value=0.01,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01'}),
    )
    currency = forms.CharField(
        label='Devise',
        max_length=10,
        initial='USD',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'USD, EUR, CDF...'}),
    )
    in_stock = forms.BooleanField(
        label='En stock',
        required=False,
        initial=True,
        widget=forms.CheckboxInput(attrs={'class': 'form-check-input'}),
    )
    sale_url = forms.URLField(
        label='Lien de vente',
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://...'}),
    )

    def clean_currency(self):
        return self.cleaned_data['currency'].strip().upper()



class QuickOfferForm(forms.Form):
    offer_type = forms.ChoiceField(
        label="Type d'offre",
        choices=Offer.OFFER_TYPES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    title = forms.CharField(
        label='Nom / titre',
        max_length=255,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: Samsung A56, chambre standard, coiffure femme...'}),
    )
    price = forms.DecimalField(
        label='Prix',
        required=False,
        min_value=0.01,
        max_digits=14,
        decimal_places=2,
        widget=forms.NumberInput(attrs={'class': 'form-control', 'step': '0.01', 'placeholder': 'Laisser vide si sur demande'}),
    )
    currency = forms.CharField(
        label='Devise',
        max_length=10,
        initial='USD',
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'USD, CDF, EUR...'}),
    )
    price_unit = forms.CharField(
        label='Unité de prix',
        max_length=60,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': 'Ex: nuit, heure, unité, mois...'}),
    )
    photos = MultipleImageFileField(
        label='Photos depuis téléphone ou ordinateur',
        required=False,
        widget=MultipleFileInput(attrs={
            'class': 'form-control',
            'accept': 'image/*',
        }),
        help_text='Jusqu’à 8 images par envoi, 8 Mo maximum par image.',
    )
    primary_image_url = forms.URLField(
        label='URL image existante',
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'https://... (optionnel)'}),
        help_text="Facultatif : utile si l'image est déjà hébergée en ligne.",
    )
    availability = forms.ChoiceField(
        label='Disponibilité',
        choices=Offer.AVAILABILITY_CHOICES,
        initial='available',
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
    whatsapp = forms.CharField(
        label='WhatsApp',
        max_length=40,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control', 'placeholder': '+243...'}),
    )
    external_url = forms.URLField(
        label='Lien externe / site',
        required=False,
        widget=forms.URLInput(attrs={'class': 'form-control', 'placeholder': 'Optionnel'}),
    )
    description = forms.CharField(
        label='Description',
        required=False,
        widget=forms.Textarea(attrs={'class': 'form-control', 'rows': 4}),
    )

    def clean_currency(self):
        return self.cleaned_data['currency'].strip().upper()


class OfferEditForm(QuickOfferForm):
    category = forms.CharField(
        label='Catégorie',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    city = forms.CharField(
        label='Ville',
        max_length=120,
        required=False,
        widget=forms.TextInput(attrs={'class': 'form-control'}),
    )
    contact_method = forms.ChoiceField(
        label='Contact principal',
        choices=Offer.CONTACT_CHOICES,
        widget=forms.Select(attrs={'class': 'form-select'}),
    )
