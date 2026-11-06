"""Validate and re-encode raster images; never trust extension, MIME or filenames."""
import hashlib
import warnings
from io import BytesIO
from PIL import Image, ImageOps, UnidentifiedImageError
from django.core.exceptions import ValidationError

MAX_UPLOAD = 5 * 1024 * 1024

def clean_image(data, *, logo=False):
    if not data or len(data) > MAX_UPLOAD:
        raise ValidationError('Gambar wajib diisi dan maksimal 5 MB.')
    try:
        with warnings.catch_warnings():
            warnings.simplefilter('error', Image.DecompressionBombWarning)
            with Image.open(BytesIO(data)) as original:
                if original.format not in ('PNG', 'JPEG', 'WEBP'):
                    raise ValidationError('Gunakan gambar JPEG, PNG, atau WebP.')
                if logo and original.format != 'PNG':
                    raise ValidationError('Gunakan logo PNG dengan latar transparan.')
                if original.width * original.height > 20_000_000:
                    raise ValidationError('Resolusi gambar terlalu besar (maksimal 20 megapiksel).')
                original.load()
                image = ImageOps.exif_transpose(original).convert('RGBA' if logo else 'RGB')
                if logo and image.getchannel('A').getextrema()[0] == 255:
                    raise ValidationError('Logo masih memiliki latar penuh. Unggah PNG dengan area transparan.')
                if logo and image.getchannel('A').getextrema()[1] == 0:
                    raise ValidationError('Logo kosong atau sepenuhnya transparan.')
                image.thumbnail((1200, 1200) if logo else (2400, 2400))
                image.info.clear()
                output = BytesIO()
                if logo:
                    image.save(output, 'PNG', optimize=True)
                else:
                    image.save(output, 'JPEG', quality=88)
    except (UnidentifiedImageError, OSError, ValueError, Image.DecompressionBombError, Image.DecompressionBombWarning):
        raise ValidationError('Gambar tidak valid atau rusak.') from None
    data = output.getvalue()
    return data, 'image/png' if logo else 'image/jpeg', hashlib.sha256(data).hexdigest()

def read_upload(upload):
    if upload.size > MAX_UPLOAD:
        raise ValidationError('Ukuran gambar maksimal 5 MB.')
    return upload.read(MAX_UPLOAD + 1)
