from django import forms
from django.contrib.auth.forms import UserCreationForm
from django.contrib.auth.models import User

from .markets import DEFAULT_MARKET_CODE, market_choices
from .services import get_llm_config


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
