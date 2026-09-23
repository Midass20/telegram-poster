"""Генерирует несколько вариантов логотипа канала для выбора."""
import math
from PIL import Image, ImageDraw, ImageFont, ImageFilter

SIZE = 512
FONT_BOLD = "C:/Windows/Fonts/arialbd.ttf"


def gradient(size, top, bottom, diag=20):
    img = Image.new("RGB", (size, size), top)
    px = img.load()
    for y in range(size):
        t = y / (size - 1)
        r = int(top[0] + (bottom[0] - top[0]) * t)
        g = int(top[1] + (bottom[1] - top[1]) * t)
        b = int(top[2] + (bottom[2] - top[2]) * t)
        for x in range(size):
            dx = (x - size / 2) / size
            shift = int(diag * dx)
            px[x, y] = (
                max(0, min(255, r + shift)),
                max(0, min(255, g + shift // 2)),
                max(0, min(255, b + shift)),
            )
    return img


def vignette(img, strength=60):
    size = img.size[0]
    v = Image.new("L", (size, size), 0)
    vd = ImageDraw.Draw(v)
    vd.ellipse([-size * 0.3, -size * 0.3, size * 1.3, size * 1.3], fill=strength)
    return Image.composite(img, Image.new("RGB", (size, size), (0, 0, 0)), v.point(lambda p: 255 - p // 3))


# ---------- Вариант 1: нейросеть-гексагон (индиго/фиолетовый) ----------
def variant_1():
    img = vignette(gradient(SIZE, (20, 20, 50), (60, 30, 110)))
    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = SIZE / 2, SIZE / 2
    R = SIZE * 0.30
    ACCENT, ACCENT2 = (110, 210, 255), (170, 130, 255)
    nodes = [(cx, cy)]
    for i in range(6):
        a = -math.pi / 2 + i * (2 * math.pi / 6)
        nodes.append((cx + R * math.cos(a), cy + R * math.sin(a)))
    for i in range(1, len(nodes)):
        draw.line([nodes[0], nodes[i]], fill=(*ACCENT, 160), width=5)
    for i in range(1, len(nodes)):
        j = i + 1 if i + 1 < len(nodes) else 1
        draw.line([nodes[i], nodes[j]], fill=(*ACCENT2, 90), width=3)
    for idx, (nx, ny) in enumerate(nodes):
        rad = SIZE * 0.052 if idx == 0 else SIZE * 0.034
        color = (255, 255, 255, 235) if idx == 0 else (*ACCENT, 230)
        glow = rad * 1.9
        draw.ellipse([nx - glow, ny - glow, nx + glow, ny + glow], fill=(*(ACCENT if idx else ACCENT2), 45))
        draw.ellipse([nx - rad, ny - rad, nx + rad, ny + rad], fill=color)
    return img


# ---------- Вариант 2: чип/процессор (изумрудно-бирюзовый) ----------
def variant_2():
    img = vignette(gradient(SIZE, (6, 30, 28), (10, 70, 66)))
    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = SIZE / 2, SIZE / 2
    core = SIZE * 0.24
    ACCENT = (110, 255, 220)
    # ножки чипа
    n_pins = 5
    pin_len = SIZE * 0.09
    for i in range(n_pins):
        off = (i - (n_pins - 1) / 2) * (core * 1.7 / n_pins)
        for sx, sy, dx, dy in [(-1, 0, -1, 0), (1, 0, 1, 0), (0, -1, 0, -1), (0, 1, 0, 1)]:
            if sx != 0:
                x0 = cx + sx * core
                y0 = cy + off
                x1 = x0 + dx * pin_len
                draw.line([(x0, y0), (x1, y0)], fill=(*ACCENT, 200), width=6)
                draw.ellipse([x1 - 4, y0 - 4, x1 + 4, y0 + 4], fill=(*ACCENT, 220))
            else:
                x0 = cx + off
                y0 = cy + sy * core
                y1 = y0 + dy * pin_len
                draw.line([(x0, y0), (x0, y1)], fill=(*ACCENT, 200), width=6)
                draw.ellipse([x0 - 4, y1 - 4, x0 + 4, y1 + 4], fill=(*ACCENT, 220))
    # корпус чипа
    draw.rounded_rectangle([cx - core, cy - core, cx + core, cy + core], radius=SIZE * 0.03,
                            fill=(8, 46, 43, 255), outline=(*ACCENT, 255), width=4)
    # внутренняя сетка
    grid = 3
    step = (core * 2) / grid
    for i in range(1, grid):
        x = cx - core + i * step
        draw.line([(x, cy - core + 10), (x, cy + core - 10)], fill=(*ACCENT, 90), width=2)
        y = cy - core + i * step
        draw.line([(cx - core + 10, y), (cx + core - 10, y)], fill=(*ACCENT, 90), width=2)
    # центральная точка
    draw.ellipse([cx - 10, cy - 10, cx + 10, cy + 10], fill=(255, 255, 255, 255))
    return img


# ---------- Вариант 3: монограмма "AI" (закат: оранжево-розовый) ----------
def variant_3():
    img = vignette(gradient(SIZE, (60, 20, 60), (230, 90, 60), diag=10), strength=40)
    draw = ImageDraw.Draw(img, "RGBA")
    font = ImageFont.truetype(FONT_BOLD, int(SIZE * 0.40))
    text = "AI"
    bbox = draw.textbbox((0, 0), text, font=font)
    tw, th = bbox[2] - bbox[0], bbox[3] - bbox[1]
    tx = SIZE / 2 - tw / 2 - bbox[0]
    ty = SIZE / 2 - th / 2 - bbox[1]
    # тень/свечение
    glow = Image.new("RGBA", (SIZE, SIZE), (0, 0, 0, 0))
    gdraw = ImageDraw.Draw(glow)
    gdraw.text((tx, ty), text, font=font, fill=(255, 220, 180, 255))
    glow = glow.filter(ImageFilter.GaussianBlur(12))
    img = Image.alpha_composite(img.convert("RGBA"), glow).convert("RGB")
    draw = ImageDraw.Draw(img, "RGBA")
    draw.text((tx, ty), text, font=font, fill=(255, 255, 255, 255))
    # искра-акцент
    spark_x, spark_y = SIZE * 0.76, SIZE * 0.26
    for r, a in [(22, 60), (10, 255)]:
        draw.ellipse([spark_x - r, spark_y - r, spark_x + r, spark_y + r], fill=(255, 255, 255, a))
    return img


# ---------- Вариант 4: мозг из узлов (синий/электрик) ----------
def variant_4():
    img = vignette(gradient(SIZE, (8, 14, 40), (20, 60, 130)))
    draw = ImageDraw.Draw(img, "RGBA")
    cx, cy = SIZE / 2, SIZE / 2 + 6
    ACCENT = (120, 200, 255)
    # силуэт мозга через две перекрывающиеся дуги (упрощённо)
    w, h = SIZE * 0.34, SIZE * 0.30
    # набор точек, имитирующих контур мозга (полукруглые доли)
    import random
    random.seed(7)
    lobes = []
    for i in range(26):
        ang = random.uniform(0, 2 * math.pi)
        rad = random.uniform(0.55, 1.0)
        rx = w * rad * math.cos(ang)
        ry = h * rad * math.sin(ang) * (0.85 if math.sin(ang) > 0 else 1.05)
        lobes.append((cx + rx, cy + ry))
    # соединяем ближайшие точки линиями (создаёт "сетчатую" структуру)
    for i, p1 in enumerate(lobes):
        dists = sorted(range(len(lobes)), key=lambda j: (lobes[j][0]-p1[0])**2 + (lobes[j][1]-p1[1])**2)
        for j in dists[1:3]:
            draw.line([p1, lobes[j]], fill=(*ACCENT, 110), width=2)
    for (nx, ny) in lobes:
        rad = SIZE * 0.014
        draw.ellipse([nx - rad, ny - rad, nx + rad, ny + rad], fill=(*ACCENT, 230))
    # центральное ядро
    draw.ellipse([cx - 16, cy - 16, cx + 16, cy + 16], fill=(255, 255, 255, 255))
    glow = 34
    draw.ellipse([cx - glow, cy - glow, cx + glow, cy + glow], fill=(*ACCENT, 60))
    return img


for i, fn in enumerate([variant_1, variant_2, variant_3, variant_4], start=1):
    im = fn()
    path = f"logo_variant_{i}.png"
    im.save(path, "PNG")
    print("saved", path)
