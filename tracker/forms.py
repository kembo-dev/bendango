from django import forms

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
    model_name = forms.CharField(
        label="Modèle LLM",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )

    def __init__(self, *args, **kwargs):
        super().__init__(*args, **kwargs)
        default_model = get_llm_config()["default_model"]
        self.fields["model_name"].initial = default_model
        self.fields["model_name"].help_text = f"Modèle actif : {default_model}"
