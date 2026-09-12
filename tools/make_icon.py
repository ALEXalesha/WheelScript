"""Рисует assets/icon.ico (руль). Запуск: python tools/make_icon.py"""

from pathlib import Path

from PIL import Image, ImageDraw

S = 256
img = Image.new("RGBA", (S, S), (0, 0, 0, 0))
d = ImageDraw.Draw(img)
d.ellipse((8, 8, S - 8, S - 8), fill=(37, 99, 235, 255))
d.ellipse((34, 34, S - 34, S - 34), outline=(255, 255, 255, 255), width=22)
c = S / 2
d.ellipse((c - 30, c - 30, c + 30, c + 30), fill=(255, 255, 255, 255))
d.rectangle((44, c - 11, S - 44, c + 11), fill=(255, 255, 255, 255))
d.rectangle((c - 11, c, c + 11, S - 44), fill=(255, 255, 255, 255))
d.ellipse((c - 12, c - 12, c + 12, c + 12), fill=(37, 99, 235, 255))

out = Path(__file__).resolve().parent.parent / "assets" / "icon.ico"
out.parent.mkdir(exist_ok=True)
img.save(out, sizes=[(16, 16), (24, 24), (32, 32), (48, 48), (64, 64), (128, 128), (256, 256)])
print(out)
