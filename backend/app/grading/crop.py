import io
import math

from PIL import Image, ImageOps
from pillow_heif import register_heif_opener

register_heif_opener()

MAX_SIDE = 2048
JPEG_QUALITY = 90


def _jpeg(img: Image.Image) -> bytes:
    buf = io.BytesIO()
    img.save(buf, format="JPEG", quality=JPEG_QUALITY)
    return buf.getvalue()


def prepare_image(data: bytes) -> bytes:
    """Upright (EXIF), RGB, long side <= 2048 px (never upscaled), JPEG."""
    with Image.open(io.BytesIO(data)) as img:
        img = ImageOps.exif_transpose(img).convert("RGB")
        img.thumbnail((MAX_SIDE, MAX_SIDE))
        return _jpeg(img)


def _span(lo: float, hi: float, size: int) -> tuple[int, int]:
    """Relative [lo, hi] -> pixel [start, end), clamped and at least 1 px wide."""
    start = min(max(math.floor(lo * size), 0), size - 1)
    end = max(min(math.ceil(hi * size), size), start + 1)
    return start, end


def crop(image: bytes, bbox: tuple[float, float, float, float]) -> bytes:
    """Cut the relative bbox [x1, y1, x2, y2] out of `image`; returns JPEG."""
    x1, y1, x2, y2 = bbox
    with Image.open(io.BytesIO(image)) as img:
        left, right = _span(x1, x2, img.width)
        top, bottom = _span(y1, y2, img.height)
        return _jpeg(img.crop((left, top, right, bottom)).convert("RGB"))
