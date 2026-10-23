"""Vermilion seal 「红笔君」: right column 红笔, left column 君 (read right to left), white carved text.

Writes: avatar (paper background, seal centred, survives WeChat's circular crop) and a transparent seal.
"""
import random
import sys
from pathlib import Path

from PIL import Image, ImageChops, ImageDraw, ImageFilter, ImageFont

FONT = r"C:\Windows\Fonts\Source Han Serif SC Heavy (TrueType).ttf"
VERMILION = (184, 38, 28)
PAPER = (250, 248, 243)
out = Path(sys.argv[1])
out.mkdir(parents=True, exist_ok=True)
random.seed(7)


def seal(size: int) -> Image.Image:
    """Transparent RGBA seal of `size` px with a slightly worn edge and texture."""
    s = size
    mask = Image.new("L", (s, s), 0)
    d = ImageDraw.Draw(mask)
    pad = int(s * 0.04)
    d.rounded_rectangle([pad, pad, s - pad, s - pad], radius=int(s * 0.06), fill=255)

    # carve the characters out of the block (white text = transparent holes)
    text = Image.new("L", (s, s), 0)
    td = ImageDraw.Draw(text)
    margin = int(s * 0.07)  # vermilion border kept around the characters
    pad += margin
    inner = s - 2 * pad
    col_w = inner * 0.45
    small = ImageFont.truetype(FONT, int(inner * 0.40))
    big = ImageFont.truetype(FONT, int(inner * 0.80))

    def draw_center(font, ch, cx, cy, sx=1.0):
        bbox = td.textbbox((0, 0), ch, font=font)
        w, h = bbox[2] - bbox[0], bbox[3] - bbox[1]
        layer = Image.new("L", (int(w * 1.3) + 4, int(h * 1.3) + 4), 0)
        ImageDraw.Draw(layer).text((-bbox[0] + 2, -bbox[1] + 2), ch, font=font, fill=255)
        layer = layer.crop(layer.getbbox())
        layer = layer.resize((max(1, int(layer.width * sx)), layer.height), Image.LANCZOS)
        text.paste(255, (int(cx - layer.width / 2), int(cy - layer.height / 2)), layer)

    right_cx = pad + inner - col_w / 2
    left_cx = pad + col_w / 2
    draw_center(small, "红", right_cx, pad + inner * 0.25)
    draw_center(small, "笔", right_cx, pad + inner * 0.75)
    draw_center(big, "君", left_cx, pad + inner * 0.5, sx=0.56)

    block = ImageChops.subtract(mask, text)

    # Stamp texture: ink that didn't take — fine speckles all over, bigger bites along the border.
    wear = Image.new("L", (s, s), 0)
    wd = ImageDraw.Draw(wear)
    for _ in range(int(s * 0.18)):
        x, y = random.uniform(0, s), random.uniform(0, s)
        r = random.uniform(s * 0.0006, s * 0.0018)
        wd.ellipse([x - r, y - r, x + r, y + r], fill=255)
    outer = int(s * 0.04)
    for _ in range(int(s * 0.05)):
        side = random.randrange(4)
        t = random.uniform(outer, s - outer)
        off = random.uniform(-s * 0.004, s * 0.012)
        x, y = [(t, outer + off), (t, s - outer - off), (outer + off, t), (s - outer - off, t)][side]
        r = random.uniform(s * 0.002, s * 0.009)
        wd.ellipse([x - r, y - r, x + r, y + r], fill=255)
    block = ImageChops.subtract(block, wear.filter(ImageFilter.GaussianBlur(s / 2500)))
    block = block.filter(ImageFilter.GaussianBlur(s / 1600))

    img = Image.new("RGBA", (s, s), VERMILION + (0,))
    img.putalpha(block)
    return img


big_seal = seal(2048)
# transparent seals for the web header / favicon
for px in (512, 128, 64):
    big_seal.resize((px, px), Image.LANCZOS).save(out / f"seal-{px}.png")

# avatar: paper square, seal at 62% so the circular crop never cuts it
avatar = Image.new("RGB", (1024, 1024), PAPER)
sz = int(1024 * 0.68)
avatar.paste(big_seal.resize((sz, sz), Image.LANCZOS), ((1024 - sz) // 2, (1024 - sz) // 2),
             big_seal.resize((sz, sz), Image.LANCZOS))
avatar.save(out / "avatar-1024.png")
print("ok")
