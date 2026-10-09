from django.core.management.base import BaseCommand, CommandError
from django.core.exceptions import ValidationError
from tracker.models import OfferMedia


class Command(BaseCommand):
    help = 'Create 1600px WebP photos and 320px thumbnails without overwriting stored sources.'

    def add_arguments(self, parser):
        parser.add_argument('--apply', action='store_true', help='Write renditions; default only counts pending photos.')
        parser.add_argument('--offer-id', type=int)

    def handle(self, *args, **options):
        media = OfferMedia.objects.exclude(file='').filter(thumbnail_file='')
        if options['offer_id']:
            media = media.filter(offer_id=options['offer_id'])
        if not options['apply']:
            self.stdout.write(f'{media.count()} photo(s) à optimiser. Ajouter --apply pour exécuter.')
            return
        count = errors = 0
        for item in media.iterator():
            try:
                count += int(item.optimize_existing())
            except (ValidationError, OSError):
                errors += 1
                self.stderr.write(f'Média #{item.pk} ignoré : source absente ou photo invalide.')
        self.stdout.write(f'{count} photo(s) optimisée(s), {errors} erreur(s). Sources conservées.')
        if errors:
            raise CommandError('Certaines photos nécessitent une vérification manuelle.')
