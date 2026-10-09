"""Inspect or select a local LLM profile without contacting any provider."""

import os
from pathlib import Path
import re
import tempfile

from django.conf import settings
from django.core.exceptions import ImproperlyConfigured
from django.core.management.base import BaseCommand, CommandError

from config.llm import DISABLED_REFERENCE, load_config, model_reference, read_document
from tracker.services import LLMRequiredError, get_llm_model_reference


class Command(BaseCommand):
    help = 'Inspecte ou sélectionne un profil LLM local, sans appel API ni affichage de clé.'

    def add_arguments(self, parser):
        group = parser.add_mutually_exclusive_group()
        group.add_argument('--profile', help='Inspecter un profil sans changer la sélection.')
        group.add_argument('--use', help='Activer un profil dans le fichier local ignoré par Git.')
        parser.add_argument('--list', action='store_true', help='Lister les profils disponibles.')
        parser.add_argument('--check', action='store_true', help='Vérifier la configuration et la présence de la clé requise, sans réseau.')

    def handle(self, *args, **options):
        path = Path(settings.LLM_CONFIG_FILE)
        try:
            document = read_document(path)
            if options['list']:
                for name in ['legacy', *sorted(document['profiles'])]:
                    self.stdout.write(name)
                if not options['profile'] and not options['use'] and not options['check']:
                    return
            policy = document['policy']
            self.stdout.write(f"Mode : {policy['mode']}\nSecours : {policy['fallback_profile'] or 'aucun'}\nSecours distant autorisé : {policy['allow_paid_fallback']}")
            if not options['profile'] and not options['use'] and get_llm_model_reference() == DISABLED_REFERENCE:
                self.stdout.write(self.style.WARNING('Extraction sans LLM active. Vérifier le modèle, la clé ou le profil pour activer le complément.'))
                return
            name = options['use'] or options['profile']
            config = load_config(path, getattr(settings, 'LLM_CONFIG', {}), profile=name)
            if options['check'] and config['provider'] == 'openai-compatible' and config['require_api_key'] and not config['api_key']:
                raise CommandError('Clé API absente ; définir la variable api_key_env du profil dans .env.')
            if options['use']:
                if os.environ.get('LLM_PROFILE') and os.environ['LLM_PROFILE'] != config['profile']:
                    raise CommandError('LLM_PROFILE impose un autre profil ; modifier cette variable avant --use.')
                target = path.with_suffix('.local.toml')
                previous = target.read_text() if target.exists() else ''
                line = f'active_profile = "{config["profile"]}"'
                # active_profile belongs to the root table, before any profile section.
                parts = re.split(r'(?m)(?=^[ \t]*\[)', previous, maxsplit=1)
                head, tail = parts[0], parts[1] if len(parts) > 1 else ''
                if re.search(r'^[ \t]*active_profile\s*=', head, flags=re.M):
                    head = re.sub(r'^[ \t]*active_profile\s*=.*$', line, head, count=1, flags=re.M)
                else:
                    head = line + '\n' + head
                with tempfile.NamedTemporaryFile(mode='w', dir=target.parent, delete=False) as handle:
                    temporary = Path(handle.name)
                    handle.write(head + tail)
                try:
                    temporary.replace(target)
                finally:
                    temporary.unlink(missing_ok=True)
                self.stdout.write(self.style.SUCCESS('Préférence locale enregistrée. Les nouveaux appels utiliseront ce profil.'))
            self.stdout.write(f"Profil : {config['profile']}\nFournisseur : {config['provider']}\nModèle : {config['default_model']}\nRéférence : {model_reference(config)}\nTimeout : {config['timeout']} s\nLimite de sortie : {config['max_tokens']} tokens")
            if config['provider'] == 'openai-compatible':
                self.stdout.write('Clé API : ' + ('présente' if config['api_key'] else 'absente'))
            elif config['provider'] == 'bedrock':
                self.stdout.write('Authentification : chaîne de credentials AWS du SDK ; non testée sur réseau.')
            if options['check']:
                self.stdout.write(self.style.SUCCESS('Configuration valide. Aucun appel au fournisseur effectué.'))
        except (ImproperlyConfigured, LLMRequiredError) as error:
            raise CommandError(str(error)) from None
        except OSError:
            raise CommandError('Impossible de lire ou écrire la préférence LLM locale.') from None
