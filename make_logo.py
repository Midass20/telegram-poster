"""Генерирует логотип канала: градиентный фон + иконка нейросети."""
import math
from PIL import Image, ImageDraw

SIZE = 512
OUT = "logo.png"

# Градиент: глубокий индиго -> фиолетовый -> голубой (tech/AI палитра)
COLOR_TOP = (20, 20, 50)
COLOR_BOTTOM = (60, 30, 110)
ACCENT = (110, 210, 255)     # голубой для узлов/линий
ACCENT2 = (170, 130, 255)    # фиолетовый акцент

img = Image.new("RGB", (SIZE, SIZE), COLOR_TOP)
px = img.load()
for y in range(SIZE):
    t = y / (SIZE - 1)
    # диагональный градиент (учитываем и x тоже, слегка)
    r = int(COLOR_TOP[0] + (COLOR_BOTTOM[0] - COLOR_TOP[0]) * t)
    g = int(COLOR_TOP[1] + (COLOR_BOTTOM[1] - COLOR_TOP[1]) * t)
    b = int(COLOR_TOP[2] + (COLOR_BOTTOM[2] - COLOR_TOP[2]) * t)
    for x in range(SIZE):
        dx = (x - SIZE / 2) / SIZE
        shift = int(20 * dx)
        px[x, y] = (
            max(0, min(255, r + shift)),
            max(0, min(255, g + shift // 2)),
            max(0, min(255, b + shift)),
        )

draw = ImageDraw.Draw(img, "RGBA")

# Небольшое виньетирование по краям для глубины
vignette = Image.new("L", (SIZE, SIZE), 0)
vdraw = ImageDraw.Draw(vignette)
vdraw.ellipse([-SIZE * 0.3, -SIZE * 0.3, SIZE * 1.3, SIZE * 1.3], fill=60)
img = Image.composite(img, Image.new("RGB", (SIZE, SIZE), (0, 0, 0)), vignette.point(lambda p: 255 - p // 3))
draw = ImageDraw.Draw(img, "RGBA")

cx, cy = SIZE / 2, SIZE / 2
R = SIZE * 0.30

# Узлы нейросети по кругу + один центральный
nodes = [(cx, cy)]
n_outer = 6
for i in range(n_outer):
    angle = -math.pi / 2 + i * (2 * math.pi / n_outer)
    nodes.append((cx + R * math.cos(angle), cy + R * math.sin(angle)))

# Линии связи (центр -> все внешние + соседние внешние между собой)
for i in range(1, len(nodes)):
    draw.line([nodes[0], nodes[i]], fill=(*ACCENT, 160), width=5)
for i in range(1, len(nodes)):
    j = i + 1 if i + 1 < len(nodes) else 1
    draw.line([nodes[i], nodes[j]], fill=(*ACCENT2, 90), width=3)

# Узлы (кружки), центральный крупнее и ярче
for idx, (nx, ny) in enumerate(nodes):
    rad = SIZE * 0.052 if idx == 0 else SIZE * 0.034
    color = (255, 255, 255, 235) if idx == 0 else (*ACCENT, 230)
    glow_rad = rad * 1.9
    draw.ellipse([nx - glow_rad, ny - glow_rad, nx + glow_rad, ny + glow_rad],
                 fill=(*(ACCENT if idx else ACCENT2), 45))
    draw.ellipse([nx - rad, ny - rad, nx + rad, ny + rad], fill=color)

img.save(OUT, "PNG")
print(f"Saved {OUT} ({img.size[0]}x{img.size[1]})")
