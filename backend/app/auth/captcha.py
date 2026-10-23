import base64
import io
import os
import random
import secrets

from PIL import Image, ImageDraw, ImageFont

# No 0/O/1/I/L: easy to confuse.
ALPHABET = "ABCDEFGHJKMNPQRSTUVWXYZ23456789"
LENGTH = 4
WIDTH, HEIGHT = 120, 44

_FONT_CANDIDATES = (
    "/usr/share/fonts/truetype/wqy/wqy-microhei.ttc",
    "/usr/share/fonts/truetype/dejavu/DejaVuSans-Bold.ttf",
    "C:/Windows/Fonts/arialbd.ttf",
    "C:/Windows/Fonts/simhei.ttf",
)


def new_code() -> str:
    return "".join(secrets.choice(ALPHABET) for _ in range(LENGTH))


def _font(size: int):
    for path in _FONT_CANDIDATES:
        if os.path.exists(path):
            try:
                return ImageFont.truetype(path, size)
            except OSError:
                continue
    return ImageFont.load_default(size=size)


def render_png(code: str) -> bytes:
    rnd = random.SystemRandom()
    img = Image.new("RGB", (WIDTH, HEIGHT), (250, 246, 238))
    draw = ImageDraw.Draw(img)
    for _ in range(5):
        draw.line(
            [(rnd.randint(0, WIDTH), rnd.randint(0, HEIGHT)), (rnd.randint(0, WIDTH), rnd.randint(0, HEIGHT))],
            fill=(rnd.randint(120, 200),) * 3,
            width=rnd.randint(1, 2),
        )
    font = _font(30)
    slot = WIDTH // LENGTH
    for i, ch in enumerate(code):
        glyph = Image.new("RGBA", (slot, HEIGHT), (0, 0, 0, 0))
        ImageDraw.Draw(glyph).text(
            (slot // 2, HEIGHT // 2), ch, font=font, anchor="mm",
            fill=(rnd.randint(20, 110), rnd.randint(20, 110), rnd.randint(20, 110), 255),
        )
        glyph = glyph.rotate(rnd.randint(-18, 18), resample=Image.BICUBIC)
        img.paste(glyph, (i * slot, rnd.randint(-2, 2)), glyph)
    for _ in range(40):
        draw.point((rnd.randint(0, WIDTH), rnd.randint(0, HEIGHT)), fill=(rnd.randint(60, 180),) * 3)
    buf = io.BytesIO()
    img.save(buf, format="PNG")
    return buf.getvalue()


def render_base64(code: str) -> str:
    return base64.b64encode(render_png(code)).decode()
