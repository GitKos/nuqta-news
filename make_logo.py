"""Аватар канала: assets/logo.png (1024x1024, всё важное внутри круга)."""
from pathlib import Path

from PIL import Image, ImageDraw, ImageFont

S = 1024
F = "C:/Windows/Fonts/segoeuib.ttf"
ACCENT = (25, 194, 160)

img = Image.new("RGB", (S, S))
px = img.load()
a, b = (6, 24, 44), (12, 92, 104)
for y in range(S):
    for x in range(S):
        t = (x + y) / (2 * S - 2)
        px[x, y] = tuple(int(a[i] + (b[i] - a[i]) * t) for i in range(3))
d = ImageDraw.Draw(img)

big = ImageFont.truetype(F, 215)
l, t, r, btm = d.textbbox((0, 0), "NUQTA", font=big)
x, y = (S - (r - l)) // 2 - l - 36, 380 - t
d.text((x, y), "NUQTA", font=big, fill="white")

# «живая» точка справа сверху от букв
cx, cy = x + r + 50, 500
d.ellipse([cx - 46, cy - 46, cx + 46, cy + 46], outline=(25, 194, 160), width=8)
d.ellipse([cx - 24, cy - 24, cx + 24, cy + 24], fill=ACCENT)

# подпись с разрядкой
small = ImageFont.truetype(F, 46)
word, gap = "НОВОСТИ УЗБЕКИСТАНА", 12
w = sum(d.textlength(c, font=small) for c in word) + gap * (len(word) - 1)
cx = (S - w) / 2
for c in word:
    d.text((cx, 620), c, font=small, fill=ACCENT)
    cx += d.textlength(c, font=small) + gap

out = Path(__file__).parent / "assets"
out.mkdir(exist_ok=True)
img.save(out / "logo.png")
print(out / "logo.png")
