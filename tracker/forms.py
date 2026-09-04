from django import forms


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
        label="Modèle Ollama",
        initial="qwen2.5-coder:7b",
        widget=forms.TextInput(attrs={"class": "form-control"}),
    )