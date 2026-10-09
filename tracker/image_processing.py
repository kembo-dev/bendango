"""Validated photo renditions shared by uploads and existing local media."""
from io import BytesIO
import warnings
from pathlib import Path

from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError
from django.core.files.uploadedfile import SimpleUploadedFile

MAIN_EDGE = 1600
THUMB_EDGE = 320
WEBP_QUALITY = 85
MAX_PIXELS = 25_000_000


def _webp(image):
    output = BytesIO()
    image.save(output, format='WEBP', quality=WEBP_QUALITY, method=4)
    return output.getvalue()


def prepare_photo(source):
    """Return a bounded full photo and square preview, without EXIF or upscaling."""
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            source.seek(0)
            with Image.open(source) as original:
                if original.format not in {'JPEG', 'PNG', 'WEBP', 'GIF'} or original.width * original.height > MAX_PIXELS:
                    raise ValueError('unsupported photo')
                original.load()
                image = ImageOps.exif_transpose(original).convert('RGBA' if original.mode in {'RGBA', 'LA', 'P'} else 'RGB')
                image.thumbnail((MAIN_EDGE, MAIN_EDGE), Image.Resampling.LANCZOS)
                # Crop only the thumbnail. Small inputs are padded rather than enlarged.
                edge = min(THUMB_EDGE, *image.size)
                cropped = ImageOps.fit(image, (edge, edge), method=Image.Resampling.LANCZOS)
                thumbnail = Image.new('RGBA', (THUMB_EDGE, THUMB_EDGE), (0, 0, 0, 0))
                thumbnail.paste(cropped, ((THUMB_EDGE-edge)//2, (THUMB_EDGE-edge)//2))
                main = SimpleUploadedFile(Path(source.name).stem + '.webp', _webp(image), content_type='image/webp')
                main.offer_thumbnail = _webp(thumbnail)
                return main
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('Photo invalide : utilisez JPEG, PNG, WebP ou GIF, avec au maximum 25 mégapixels.')
